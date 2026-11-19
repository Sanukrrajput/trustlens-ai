"""Runtime prediction for job descriptions, recruitment messages and anomalies.

Integrity rules
---------------
1. Only artifacts with ``approved: true`` in the model manifest are ever loaded.
   Training writes rejected/unusable models to disk for audit, but this class
   deliberately ignores them.
2. If no approved artifact is available (or an artifact fails to load), prediction
   transparently falls back to a deterministic rule scorer. Fallback model names
   always end in ``_rule_fallback`` and the output states that no trained model
   was used.
3. ``confidence`` is a decision-margin/evidence-strength indicator. It is NEVER a
   calibrated probability of fraud and the risk engine does not use it as the
   risk score; ``fraud_probability`` (where available) is used with model trust
   weighting instead.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.ml.features import (
    ANOMALY_FEATURE_NAMES,
    build_anomaly_vector,
    normalize_text,
    text_signal_counts,
)
from app.schemas import ModelPrediction

MANIFEST_FILENAME = "model_manifest.json"

FAMILY_JOB = "job_tfidf_logreg"
FAMILY_JOB_SVC = "job_tfidf_linearsvc"
FAMILY_MESSAGE = "message_tfidf_logreg"
FAMILY_ANOMALY_IFOREST = "anomaly_iforest"
FAMILY_ANOMALY_BOOSTED = "anomaly_supervised"

# Fallback lexicon additions. These are deliberately explicit so that a reviewer
# can understand exactly why a fallback produced a given score.
_FALLBACK_TERMS: tuple[tuple[str, float], ...] = (
    ("otp", 2.2),
    ("one time password", 2.2),
    ("verification code", 1.4),
    ("pin to", 1.0),
    ("bit.ly", 1.1),
    ("tinyurl", 1.1),
    ("short url", 1.1),
    ("no interview", 1.6),
    ("without interview", 1.6),
    ("call only", 0.9),
    ("do not call", 1.2),
    ("reimburs", 0.7),
    ("appointment letter", 0.6),
    ("joining allowance", 0.9),
    ("guarantee", 0.8),
    ("registration charges", 1.6),
)

_STANDARD_TEXT_LIMITATIONS = (
    "Text-only signal; no independent verification of the employer or domain was performed.",
    "Lexical patterns vary by language and region; non-English or heavily obfuscated text may be misclassified.",
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(min(max(float(value), low), high))


def _prediction(
    *,
    model_name: str,
    model_version: str,
    prediction: str,
    fraud_probability: float,
    confidence: float,
    contributing_features: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Build a contract-compliant prediction dictionary via the shared schema."""
    return ModelPrediction(
        model_name=model_name,
        model_version=model_version,
        prediction=prediction,
        fraud_probability=_clamp(fraud_probability),
        confidence=_clamp(confidence),
        contributing_features=contributing_features or [],
        limitations=limitations or [],
    ).model_dump()


def _fallback_prediction(
    *,
    model_name: str,
    fraud_probability: float,
    confidence: float,
    contributions: list[dict[str, Any]],
    limitations: list[str],
    suspicious: bool,
    enough_signal: bool = True,
) -> dict[str, Any]:
    if not enough_signal:
        label = "inconclusive"
    elif suspicious:
        label = "fraudulent"
    else:
        label = "legitimate"
    return _prediction(
        model_name=model_name,
        model_version="rule-fallback-1.0",
        prediction=label,
        fraud_probability=fraud_probability,
        confidence=confidence,
        contributing_features=contributions,
        limitations=[
            "No approved trained artifact was available; this is a transparent rule-based fallback, not a trained model.",
            "Rule scores are heuristics, are not calibrated probabilities and have not been validated on production data.",
            *limitations,
        ],
    )


class TextPredictor:
    """Load approved artifacts from ``model_dir`` and expose three predict APIs.

    Artifacts are loaded lazily and cached for the lifetime of the instance. A
    missing or corrupt artifact never raises to the caller: it produces a rule
    fallback with explicit limitations instead.
    """

    def __init__(self, model_dir: str) -> None:
        self.model_dir = Path(model_dir)
        self._manifest: dict[str, Any] = {}
        self._artifacts: dict[str, dict[str, Any]] = {}
        self._load_errors: dict[str, str] = {}
        self._read_manifest()

    # ------------------------------------------------------------------ loading
    def _read_manifest(self) -> None:
        path = self.model_dir / MANIFEST_FILENAME
        if not path.is_file():
            return
        try:
            self._manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._load_errors["manifest"] = str(exc)
            self._manifest = {}

    def _candidate_entry(self, family: str) -> dict[str, Any] | None:
        models = self._manifest.get("models", {}) if isinstance(self._manifest, dict) else {}
        family_info = models.get(family, {}) if isinstance(models, dict) else {}
        versions = family_info.get("versions", []) if isinstance(family_info, dict) else []
        approved = [row for row in versions if isinstance(row, dict) and row.get("approved") is True]
        if not approved:
            return None
        active = [row for row in approved if row.get("active") is True]
        pool = active or approved
        # Versions are ISO-8601-ish; lexical max is chronological.
        return max(pool, key=lambda row: str(row.get("version", "")))

    def _load(self, family: str) -> dict[str, Any] | None:
        if family in self._artifacts:
            return self._artifacts[family]
        entry = self._candidate_entry(family)
        if not entry:
            return None
        try:
            artifact_name = str(entry["artifact"])
            payload = joblib.load(self.model_dir / artifact_name)
            if not isinstance(payload, dict) or payload.get("approved") is not True:
                raise ValueError("artifact is not an approved model bundle")
            self._artifacts[family] = payload
            return payload
        except Exception as exc:  # noqa: BLE001 - graceful degradation is intentional
            self._load_errors[family] = f"{type(exc).__name__}: {exc}"
            return None

    def available_models(self) -> dict[str, dict[str, Any]]:
        """Return a summary of approved model families (useful for health checks)."""
        summary: dict[str, dict[str, Any]] = {}
        models = self._manifest.get("models", {}) if isinstance(self._manifest, dict) else {}
        for family in models:
            entry = self._candidate_entry(family)
            if entry:
                summary[family] = {
                    "version": entry.get("model_version"),
                    "approved": True,
                    "loaded": self._load(family) is not None,
                }
        return summary

    # ------------------------------------------------------------------- helpers
    @staticmethod
    def _fraud_probability(
        payload: dict[str, Any], normalised_text: str
    ) -> tuple[float, list[str]]:
        pipeline = payload["pipeline"]
        notes: list[str] = []
        fraud_index = int(payload.get("fraud_class_index", 1))
        matrix = pipeline.named_steps["tfidf"].transform([normalised_text])
        classifier = pipeline.named_steps["clf"]
        if hasattr(classifier, "predict_proba"):
            probability = float(classifier.predict_proba(matrix)[0, fraud_index])
        elif hasattr(classifier, "decision_function"):
            decision = float(np.ravel(classifier.decision_function(matrix))[0])
            probability = float(1.0 / (1.0 + math.exp(-np.clip(decision, -30.0, 30.0))))
            notes.append(
                "The LinearSVC has no native probability estimate; a sigmoid was applied to its decision margin. "
                "This value is a ranking score, not a calibrated probability."
            )
        else:
            raise ValueError("classifier exposes neither predict_proba nor decision_function")
        return _clamp(probability), notes

    @staticmethod
    def _text_contributions(
        payload: dict[str, Any], normalised_text: str, top_n: int = 5
    ) -> list[dict[str, Any]]:
        """Explain a text prediction using signed TF-IDF x linear coefficient terms."""
        try:
            pipeline = payload["pipeline"]
            vectorizer = pipeline.named_steps["tfidf"]
            classifier = pipeline.named_steps["clf"]
            coefficients = np.asarray(classifier.coef_)
            fraud_index = int(payload.get("fraud_class_index", 1))
            if coefficients.ndim == 2:
                # Binary linear models expose shape (1, n_features); multiclass
                # models expose (n_classes, n_features).
                row = fraud_index if coefficients.shape[0] > fraud_index else 0
                weights = coefficients[row]
            else:
                weights = coefficients
            matrix = vectorizer.transform([normalised_text])
            names = list(vectorizer.get_feature_names_out())
            values = matrix.tocoo()
            present = {names[col]: float(val) for row, col, val in zip(values.row, values.col, values.data) if row == 0}
            padded = f" {normalised_text} "
            scored: list[tuple[float, str, float]] = []
            for term, weight in zip(names, weights):
                if " " in term:
                    if f" {term} " not in padded:
                        continue
                    tfidf_value = present.get(term, 1.0)
                else:
                    if term not in present:
                        continue
                    tfidf_value = present[term]
                contribution = float(weight) * tfidf_value
                scored.append((abs(contribution), term, contribution))
            scored.sort(reverse=True)
            result: list[dict[str, Any]] = []
            for _, term, contribution in scored[:top_n]:
                increases = contribution > 0
                result.append(
                    {
                        "feature": term,
                        "value": round(float(contribution), 5),
                        "direction": "increases_risk" if increases else "decreases_risk",
                        "description": (
                            f"The phrase '{term}' contributed to a {'higher' if increases else 'lower'} "
                            "fraud score in this model's training corpus."
                        ),
                    }
                )
            return result
        except Exception:  # noqa: BLE001 - explanations must never break prediction
            return []

    @staticmethod
    def _rule_text_signals(text: str) -> tuple[float, list[dict[str, Any]]]:
        counts = text_signal_counts(text)
        normalised = normalize_text(text)
        contributions: list[dict[str, Any]] = []
        raw = 0.0
        for name, multiplier in (
            ("payment_terms", 1.9),
            ("urgency_terms", 1.0),
            ("personal_data_terms", 1.7),
            ("work_from_home_terms", 0.7),
            ("exclamation_count", 0.25),
        ):
            value = counts.get(name, 0.0)
            if value <= 0:
                continue
            contribution = min(value, 8.0) * multiplier
            raw += contribution
            contributions.append(
                {
                    "feature": name,
                    "value": round(value, 3),
                    "direction": "increases_risk",
                    "description": f"Rule fallback detected {int(value)} '{name}' signal(s) in the text.",
                }
            )
        for term, weight in _FALLBACK_TERMS:
            hits = min(normalised.count(term), 3)
            if hits:
                raw += hits * weight
                contributions.append(
                    {
                        "feature": term,
                        "value": hits,
                        "direction": "increases_risk",
                        "description": f"Rule fallback matched high-risk phrase '{term}'.",
                    }
                )
        caps = counts.get("caps_ratio", 0.0)
        if caps > 0.5 and counts.get("word_count", 0) > 5:
            raw += 0.6
            contributions.append(
                {
                    "feature": "caps_ratio",
                    "value": round(caps, 3),
                    "direction": "increases_risk",
                    "description": "Unusually high capital-letter ratio.",
                }
            )
        contributions.sort(key=lambda row: float(row["value"]), reverse=True)
        return raw, contributions[:6]

    # ------------------------------------------------------------------ predict
    def _predict_text(self, family: str, text: str, *, is_message: bool) -> dict[str, Any]:
        payload = self._load(family)
        normalised = normalize_text(text)
        if payload is None:
            raw, contributions = self._rule_text_signals(text)
            probability = _clamp(1.0 - math.exp(-raw / 3.5), 0.0, 0.88)
            confidence = _clamp(0.12 + min(raw, 10.0) * 0.03, 0.0, 0.42)
            suffices = len(normalised.split()) >= 4
            return _fallback_prediction(
                model_name=f"{'message' if is_message else 'job'}_text_rule_fallback",
                fraud_probability=probability,
                confidence=confidence,
                contributions=contributions,
                limitations=[f"Artifact family '{family}' was unavailable; see model manifest/load errors."],
                suspicious=probability >= 0.55,
                enough_signal=suffices,
            )

        if len(normalised.split()) < 3:
            return _prediction(
                model_name=str(payload["model_name"]),
                model_version=str(payload["model_version"]),
                prediction="inconclusive",
                fraud_probability=0.5,
                confidence=0.0,
                contributing_features=[],
                limitations=[
                    "Input text was too short for reliable text classification.",
                    *list(payload.get("limitations", [])),
                ],
            )

        try:
            probability, notes = self._fraud_probability(payload, normalised)
            threshold = float(payload.get("threshold", 0.5))
            contributions = self._text_contributions(payload, normalised)
            confidence = _clamp(
                0.25 + 0.5 * abs(probability - 0.5) * 2.0, 0.0, 0.95
            )
            return _prediction(
                model_name=str(payload["model_name"]),
                model_version=str(payload["model_version"]),
                prediction="fraudulent" if probability >= threshold else "legitimate",
                fraud_probability=probability,
                confidence=confidence,
                contributing_features=contributions,
                limitations=[
                    *notes,
                    *list(payload.get("limitations", [])),
                    *_STANDARD_TEXT_LIMITATIONS,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raw, contributions = self._rule_text_signals(text)
            probability = _clamp(1.0 - math.exp(-raw / 3.5), 0.0, 0.88)
            return _fallback_prediction(
                model_name=f"{'message' if is_message else 'job'}_text_rule_fallback",
                fraud_probability=probability,
                confidence=_clamp(0.12 + min(raw, 10.0) * 0.03, 0.0, 0.42),
                contributions=contributions,
                limitations=[
                    f"The approved artifact failed at inference time ({type(exc).__name__}); the trained model was not used."
                ],
                suspicious=probability >= 0.55,
                enough_signal=len(normalised.split()) >= 4,
            )

    def predict_job(self, text: str) -> dict[str, Any]:
        """Score a job description. See module docstring for output contract."""
        return self._predict_text(FAMILY_JOB, text, is_message=False)

    def predict_message(self, text: str, channel: str = "unknown") -> dict[str, Any]:
        """Score a recruitment message; ``channel`` is recorded as a limitation note."""
        result = self._predict_text(FAMILY_MESSAGE, text, is_message=True)
        if channel and channel != "unknown":
            result["limitations"].append(
                f"Message channel '{channel}' was supplied but the model was not conditioned on channel."
            )
        return result

    def predict_anomaly(self, feature_vector: dict[str, float]) -> dict[str, Any]:
        """Score a structured feature mapping for anomaly-like fraud patterns."""
        payload = self._load(FAMILY_ANOMALY_IFOREST) or self._load(FAMILY_ANOMALY_BOOSTED)
        vector = build_anomaly_vector(feature_vector or {})
        canonical = {name: float(value) for name, value in zip(ANOMALY_FEATURE_NAMES, vector)}

        if payload is None:
            raw = 0.0
            contributions: list[dict[str, Any]] = []
            for name, multiplier in (
                ("payment_terms", 0.35),
                ("urgency_terms", 0.20),
                ("personal_data_terms", 0.35),
                ("reported_scam_count", 0.25),
                ("duplicate_post_count", 0.20),
                ("link_shortener_count", 0.30),
                ("sender_domain_mismatch", 1.2),
                ("message_hour_oddity", 0.6),
            ):
                value = canonical[name]
                if value <= 0:
                    continue
                raw += min(value, 20.0) * multiplier
                contributions.append(
                    {
                        "feature": name,
                        "value": round(value, 3),
                        "direction": "increases_risk",
                        "description": f"Rule fallback treats elevated '{name}' as a risk signal.",
                    }
                )
            reputation = canonical["domain_reputation_score"]
            if 0.0 < reputation < 0.4:
                raw += (0.4 - reputation) * 2.5
                contributions.append(
                    {
                        "feature": "domain_reputation_score",
                        "value": round(reputation, 3),
                        "direction": "increases_risk",
                        "description": "Poor domain reputation reported by an upstream lookup.",
                    }
                )
            probability = _clamp(1.0 - math.exp(-raw / 3.0), 0.0, 0.85)
            return _fallback_prediction(
                model_name="anomaly_rule_fallback",
                fraud_probability=probability,
                confidence=_clamp(0.12 + min(raw, 10.0) * 0.03, 0.0, 0.42),
                contributions=contributions[:6],
                limitations=[
                    "Contextual fields were absent from the input and treated as neutral zeroes where not supplied."
                ],
                suspicious=probability >= 0.55,
                enough_signal=bool(contributions),
            )

        try:
            model = payload["model"]
            matrix = vector.reshape(1, -1)
            threshold = float(payload.get("threshold", 0.5))
            if hasattr(model, "decision_function"):
                oriented = float(np.ravel(model.decision_function(matrix))[0])
                probability = _clamp(1.0 / (1.0 + math.exp(-np.clip(oriented, -30.0, 30.0))))
            elif hasattr(model, "score_samples"):
                oriented = -float(np.ravel(model.score_samples(matrix))[0])  # higher = more anomalous
                probability = _clamp(1.0 / (1.0 + math.exp(-np.clip(oriented, -30.0, 30.0))))
            elif hasattr(model, "predict_proba"):
                probability = float(model.predict_proba(matrix)[0, int(payload.get("fraud_class_index", 1))])
            else:
                raise ValueError("anomaly model exposes no scoring API")
            contributors = sorted(
                (
                    (abs(canonical[name] * float(weight)), name, float(canonical[name]), float(weight))
                    for name, weight in zip(payload.get("feature_names", ANOMALY_FEATURE_NAMES), payload.get("coefficients", []))
                ),
                reverse=True,
            )[:5]
            features = [
                {
                    "feature": name,
                    "value": round(value, 3),
                    "direction": "increases_risk" if (value * weight) > 0 else "decreases_risk",
                    "description": f"Feature '{name}' has model weight {weight:+.3f} for anomaly risk.",
                }
                for _, name, value, weight in contributors
            ]
            return _prediction(
                model_name=str(payload["model_name"]),
                model_version=str(payload["model_version"]),
                prediction="fraudulent" if probability >= threshold else "legitimate",
                fraud_probability=probability,
                confidence=_clamp(0.25 + 0.5 * abs(probability - 0.5) * 2.0, 0.0, 0.95),
                contributing_features=features,
                limitations=[
                    *list(payload.get("limitations", [])),
                    "Anomaly scores are model-relative; missing contextual features are treated as neutral zeroes.",
                    "Decision scores mapped through a sigmoid are not calibrated probabilities.",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raw, contributions = self._rule_text_signals("")
            return _fallback_prediction(
                model_name="anomaly_rule_fallback",
                fraud_probability=_clamp(1.0 - math.exp(-raw / 3.0), 0.0, 0.85),
                confidence=0.15,
                contributions=contributions,
                limitations=[f"The approved anomaly artifact failed at inference time ({type(exc).__name__})."],
                suspicious=False,
                enough_signal=False,
            )
