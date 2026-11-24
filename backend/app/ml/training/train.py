"""Train, evaluate and publish TrustLens AI fraud-detection artifacts.

Data flow
---------
1. Load the real EMSCAD corpus (CC0-origin, University of the Aegean / Kaggle
   mirror) when available. Labels in this mirror are the strings ``'f'``/``'t'``;
   both that form and conventional 0/1 booleans are accepted.
2. Normalise and de-duplicate text *before* splitting so that near-identical
   postings cannot appear in both training and test sets (a common leakage bug
   in job-fraud benchmarks).
3. Stratify into 60% train / 20% validation / 20% test. Thresholds are chosen on
   validation only; all reported metrics come from the untouched test split.
4. Train text models (TF-IDF + LogisticRegression and TF-IDF + LinearSVC for
   EMSCAD job posts; TF-IDF + LogisticRegression for the optional real-world
   DIFrauD message and job families) and anomaly models (IsolationForest plus
   XGBoost, or RandomForest when XGBoost is unavailable).
5. Reject anything with unusable metrics. Rejected artifacts are still written
   for audit, but are marked ``approved: false`` and are ignored by inference.

If EMSCAD cannot be parsed, a documented curated synthetic corpus is used
instead. Every artifact and returned summary then carries
``provenance.real_world_data = False`` and cannot be auto-approved.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.ml.datasets.difraud import JOB_DOMAINS as DIFRAUD_JOB_DOMAINS
from app.ml.datasets.difraud import MESSAGE_DOMAINS as DIFRAUD_MESSAGE_DOMAINS
from app.ml.datasets.difraud import difraud_limitations, load_difraud_dataset
from app.ml.datasets.synthetic_messages import (
    DATASET_PROVENANCE as SYNTHETIC_PROVENANCE,
)
from app.ml.datasets.synthetic_messages import load_synthetic_messages
from app.ml.evaluation.metrics import binary_metrics, select_threshold
from app.ml.features import (
    ANOMALY_FEATURE_NAMES,
    build_anomaly_vector,
    normalize_text,
    text_signal_counts,
)

logger = logging.getLogger(__name__)

RANDOM_SEED = 42
MIN_CLASS_ROWS = 20
EMSCAD_FILENAME = "emscad_v1.csv"
MANIFEST_FILENAME = "model_manifest.json"

_FAMILY_JOB_LOGREG = "job_tfidf_logreg"
_FAMILY_JOB_SVC = "job_tfidf_linearsvc"
_FAMILY_MESSAGE = "message_tfidf_logreg"
_FAMILY_DIFRAUD_JOB = "job_difraud_logreg"
_FAMILY_DIFRAUD_MESSAGE = "message_difraud_logreg"
_FAMILY_IFOREST = "anomaly_iforest"
_FAMILY_SUPERVISED = "anomaly_supervised"

_REQUIRED_TEXT_COLUMNS = ("title", "company_profile", "description", "requirements", "benefits")


# --------------------------------------------------------------------------- io
def _resolve_data_path(data_dir: str) -> Path:
    """Resolve a possibly relative data directory from several plausible roots."""
    given = Path(data_dir).expanduser()
    here = Path(__file__).resolve()
    backend_root = here.parents[3]  # backend/
    candidates = [
        given / "raw" / EMSCAD_FILENAME,
        given / EMSCAD_FILENAME,
        Path.cwd() / given / "raw" / EMSCAD_FILENAME,
        backend_root / given / "raw" / EMSCAD_FILENAME,
        backend_root / "data" / "raw" / EMSCAD_FILENAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def _parse_label(value: Any) -> int | None:
    """Map EMSCAD's ``'t'``/``'f'`` (and common variants) to 1/0."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        number = float(value)
        if number == 1.0:
            return 1
        if number == 0.0:
            return 0
        return None
    token = str(value or "").strip().lower()
    if token in {"t", "true", "1", "1.0", "yes", "y", "fraudulent", "fraud"}:
        return 1
    if token in {"f", "false", "0", "0.0", "no", "n", "legitimate", "safe"}:
        return 0
    return None


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"t", "true", "1", "yes", "y"}


def load_emscad_dataset(data_dir: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load, validate, clean and de-duplicate the real EMSCAD corpus.

    Raises:
        FileNotFoundError: the CSV is absent.
        ValueError: labels are unusable, a class is missing/too small, or text
            columns cannot be assembled. Callers fall back to synthetic data.
    """
    path = _resolve_data_path(data_dir)
    if not path.is_file():
        raise FileNotFoundError(f"EMS CAD corpus not found at {path}")

    frame = pd.read_csv(
        path,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
        encoding_errors="replace",
    )
    raw_rows = len(frame)
    if "fraudulent" not in frame.columns:
        raise ValueError("EMS CAD CSV has no 'fraudulent' label column")

    parsed = frame["fraudulent"].map(_parse_label)
    invalid_labels = int(parsed.isna().sum())
    frame = frame.loc[parsed.notna()].copy()
    frame["label"] = parsed.loc[parsed.notna()].astype(int)

    available_columns = [name for name in _REQUIRED_TEXT_COLUMNS if name in frame.columns]
    if "description" not in available_columns and "title" not in available_columns:
        raise ValueError("no usable text columns in EMS CAD corpus")
    parts = [frame[name].fillna("").astype(str) for name in available_columns]
    combined = parts[0]
    for part in parts[1:]:
        combined = combined + "\n" + part
    frame["text"] = combined.map(normalize_text)

    before = len(frame)
    frame = frame[frame["text"].str.len() >= 20].copy()
    short_removed = before - len(frame)
    before = len(frame)
    frame = frame.drop_duplicates(subset=["text"], keep="first").reset_index(drop=True)
    duplicates_removed = before - len(frame)

    counts = frame["label"].value_counts().to_dict()
    if len(counts) < 2:
        raise ValueError("only one label class survived validation")
    if min(counts.get(0, 0), counts.get(1, 0)) < MIN_CLASS_ROWS:
        raise ValueError(f"each class needs at least {MIN_CLASS_ROWS} rows; got {counts}")

    provenance: dict[str, Any] = {
        "name": "emscad_v1",
        "real_world_data": True,
        "production_grade": True,
        "source_file": str(path),
        "origin": "University of the Aegean EMSCAD corpus, CC0-origin Kaggle mirror.",
        "license": "CC0-origin; redistribution and modification permitted.",
        "raw_rows": raw_rows,
        "invalid_labels_dropped": invalid_labels,
        "short_text_dropped": int(short_removed),
        "duplicates_removed": int(duplicates_removed),
        "class_counts": {str(key): int(value) for key, value in counts.items()},
    }
    return frame, provenance


def _load_synthetic_job_fallback() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Documented fallback used only when EMSCAD cannot be parsed.

    The curated synthetic message corpus is reused as short job-description
    proxies. It is explicitly marked non-real and can never be auto-approved.
    """
    rows = [row for row in load_synthetic_messages() if row["trainable"]]
    if len(rows) < 2 * MIN_CLASS_ROWS:
        raise ValueError("synthetic fallback corpus is too small to train on")
    frame = pd.DataFrame(
        {
            "text": [normalize_text(str(row["text"])) for row in rows],
            "label": [1 if row["label"] == "fraudulent" else 0 for row in rows],
            "salary_range": [""] * len(rows),
            "telecommuting": ["f"] * len(rows),
            "has_company_logo": ["t"] * len(rows),
            "has_questions": ["t"] * len(rows),
        }
    )
    frame = frame.drop_duplicates(subset=["text"]).reset_index(drop=True)
    provenance = dict(SYNTHETIC_PROVENANCE)
    provenance["used_as_job_fallback"] = True
    provenance["class_counts"] = {str(k): int(v) for k, v in frame["label"].value_counts().to_dict().items()}
    provenance["raw_rows"] = len(frame)
    return frame, provenance


def load_job_dataset(data_dir: str) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    """Try real data first; fall back with an explicit provenance warning."""
    notes: list[str] = []
    try:
        frame, provenance = load_emscad_dataset(data_dir)
        return frame, provenance, notes
    except Exception as exc:  # noqa: BLE001 - fallback is a documented requirement
        message = f"EMS CAD load/validation failed ({type(exc).__name__}: {exc}); using curated synthetic fallback."
        logger.warning(message)
        notes.append(message)
        frame, provenance = _load_synthetic_job_fallback()
        return frame, provenance, notes


# ----------------------------------------------------------------------- splits
def stratified_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return train/validation/test frames with 60/20/20 stratified proportions."""
    labels = frame["label"].to_numpy()
    indices = np.arange(len(frame))
    train_idx, temp_idx = train_test_split(
        indices, test_size=0.4, stratify=labels, random_state=RANDOM_SEED
    )
    val_idx, test_idx = train_test_split(
        temp_idx, test_size=0.5, stratify=labels[temp_idx], random_state=RANDOM_SEED
    )
    return (
        frame.iloc[train_idx].reset_index(drop=True),
        frame.iloc[val_idx].reset_index(drop=True),
        frame.iloc[test_idx].reset_index(drop=True),
    )


# ------------------------------------------------------------------ text models
def _text_pipeline(min_df: int) -> Pipeline:
    """TF-IDF -> linear classifier. Vectorizer is fit on train data only."""
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=min_df,
                    max_df=0.95,
                    max_features=30_000,
                    sublinear_tf=True,
                    strip_accents="unicode",
                    lowercase=True,
                ),
            ),
            ("clf", LogisticRegression(max_iter=2_000, class_weight="balanced", C=1.0)),
        ]
    )


def _scores(pipeline: Pipeline, texts: pd.Series) -> np.ndarray:
    """Return fraud-oriented scores in [0, 1] for a fitted text pipeline."""
    classifier = pipeline.named_steps["clf"]
    matrix = pipeline.named_steps["tfidf"].transform(texts.tolist())
    if hasattr(classifier, "predict_proba"):
        return classifier.predict_proba(matrix)[:, 1]
    decision = np.ravel(classifier.decision_function(matrix))
    return 1.0 / (1.0 + np.exp(-np.clip(decision, -30.0, 30.0)))


def _fit_text_model(
    *,
    family: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    provenance: dict[str, Any],
    limitations: list[str],
    min_df: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    pipeline = _text_pipeline(min_df)
    if family == _FAMILY_JOB_SVC:
        # ``named_steps`` is a copy in recent scikit-learn versions; mutate
        # ``steps`` directly so the LinearSVC actually replaces the classifier.
        pipeline.steps[-1] = ("clf", LinearSVC(C=0.5, class_weight="balanced", max_iter=5_000))

    pipeline.fit(train["text"].tolist(), train["label"].to_numpy())
    val_scores = _scores(pipeline, validation["text"])
    threshold = select_threshold(validation["label"].to_numpy(), val_scores)
    test_scores = _scores(pipeline, test["text"])
    metrics = binary_metrics(
        test["label"].to_numpy(),
        (test_scores >= threshold).astype(int),
        test_scores,
        threshold=threshold,
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "model_name": family,
        "model_version": "",  # filled by train_all
        "kind": "text",
        "pipeline": pipeline,
        "fraud_class_index": 1,
        "threshold": float(threshold),
        "feature_names": list(pipeline.named_steps["tfidf"].get_feature_names_out()),
        "provenance": dict(provenance),
        "limitations": list(limitations),
        "approved": False,
    }
    return payload, metrics


# --------------------------------------------------------------- anomaly models
def _anomaly_matrix(frame: pd.DataFrame) -> np.ndarray:
    """Build the fixed anomaly feature matrix from EMSCAD metadata columns."""
    vectors: list[np.ndarray] = []
    for _, row in frame.iterrows():
        mapping: dict[str, float] = dict(text_signal_counts(row["text"]))
        salary = str(row.get("salary_range", "") or "")
        mapping["salary_missing"] = 1.0 if not salary.strip() else 0.0
        mapping["company_logo_missing"] = 0.0 if _is_true(row.get("has_company_logo")) else 1.0
        mapping["has_questions_missing"] = 0.0 if _is_true(row.get("has_questions")) else 1.0
        mapping["telecommuting"] = 1.0 if _is_true(row.get("telecommuting")) else 0.0
        # Contextual lookups are not present in EMSCAD; leave them neutral.
        for name in ANOMALY_FEATURE_NAMES:
            mapping.setdefault(name, 0.0)
        vectors.append(build_anomaly_vector(mapping))
    return np.vstack(vectors)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=float), -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _signed_coefficients(importance: np.ndarray, correlation: np.ndarray) -> list[float]:
    """Give feature importances a direction from their label correlation."""
    signs = np.where(correlation >= 0, 1.0, -1.0)
    coeffs = np.asarray(importance, dtype=float) * signs
    norm = float(np.max(np.abs(coeffs))) or 1.0
    return [float(value / norm) for value in coeffs]


def _fit_iforest(
    train_x: np.ndarray,
    val_x: np.ndarray,
    test_x: np.ndarray,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    provenance: dict[str, Any],
    limitations: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    prevalence = float(train["label"].mean())
    model = IsolationForest(
        n_estimators=250,
        contamination=float(min(0.5, max(0.01, prevalence))),
        random_state=RANDOM_SEED,
        n_jobs=2,
    )
    model.fit(train_x)
    train_oriented = -model.score_samples(train_x)
    val_scores = _sigmoid(-model.score_samples(val_x))
    threshold = select_threshold(validation["label"].to_numpy(), val_scores)
    test_scores = _sigmoid(-model.score_samples(test_x))
    metrics = binary_metrics(
        test["label"].to_numpy(),
        (test_scores >= threshold).astype(int),
        test_scores,
        threshold=threshold,
    )
    correlations = []
    for index in range(train_x.shape[1]):
        column = train_x[:, index]
        if float(np.std(column)) == 0.0:
            correlations.append(0.0)
        else:
            value = float(np.corrcoef(column, train_oriented)[0, 1])
            correlations.append(value if math.isfinite(value) else 0.0)
    payload = {
        "schema_version": "1.0",
        "model_name": _FAMILY_IFOREST,
        "model_version": "",
        "kind": "anomaly",
        "model": model,
        "threshold": float(threshold),
        "feature_names": list(ANOMALY_FEATURE_NAMES),
        "coefficients": [float(value) for value in correlations],
        "implementation": "sklearn.IsolationForest",
        "provenance": dict(provenance),
        "limitations": list(limitations),
        "approved": False,
    }
    return payload, metrics


def _fit_supervised_anomaly(
    train_x: np.ndarray,
    val_x: np.ndarray,
    test_x: np.ndarray,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    provenance: dict[str, Any],
    limitations: list[str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    labels = train["label"].to_numpy()
    positives = max(int(labels.sum()), 1)
    negatives = max(int((1 - labels).sum()), 1)
    implementation = "sklearn.RandomForestClassifier"
    try:
        from xgboost import XGBClassifier  # optional dependency

        model: Any = XGBClassifier(
            n_estimators=250,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            scale_pos_weight=float(negatives / positives),
            eval_metric="logloss",
            tree_method="hist",
            n_jobs=2,
            random_state=RANDOM_SEED,
        )
        implementation = "xgboost.XGBClassifier"
    except Exception as exc:  # noqa: BLE001 - graceful optional-dependency fallback
        logger.warning("XGBoost unavailable (%s); using RandomForest", exc)
        model = RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=RANDOM_SEED,
            n_jobs=2,
        )

    model.fit(train_x, labels)
    val_scores = model.predict_proba(val_x)[:, 1]
    threshold = select_threshold(validation["label"].to_numpy(), val_scores)
    test_scores = model.predict_proba(test_x)[:, 1]
    metrics = binary_metrics(
        test["label"].to_numpy(),
        (test_scores >= threshold).astype(int),
        test_scores,
        threshold=threshold,
    )
    importance = np.asarray(getattr(model, "feature_importances_", np.ones(train_x.shape[1])), dtype=float)
    correlations = []
    for index in range(train_x.shape[1]):
        column = train_x[:, index]
        if float(np.std(column)) == 0.0:
            correlations.append(0.0)
        else:
            value = float(np.corrcoef(column, labels)[0, 1])
            correlations.append(value if math.isfinite(value) else 0.0)
    payload = {
        "schema_version": "1.0",
        "model_name": _FAMILY_SUPERVISED,
        "model_version": "",
        "kind": "anomaly",
        "model": model,
        "threshold": float(threshold),
        "feature_names": list(ANOMALY_FEATURE_NAMES),
        "coefficients": _signed_coefficients(importance, np.asarray(correlations)),
        "implementation": implementation,
        "provenance": dict(provenance),
        "limitations": list(limitations),
        "approved": False,
    }
    return payload, metrics, implementation


# --------------------------------------------------------------------- approval
def _approval(
    metrics: dict[str, Any],
    provenance: dict[str, Any],
    *,
    min_auc: float,
    min_recall: float,
    max_fnr: float,
    min_precision: float = 0.15,
    max_fpr: float = 0.40,
) -> tuple[bool, list[str]]:
    """Decide whether a model may be promoted to approved status.

    Deliberately strict: no real data, no promotion. Poor ranking, poor recall,
    poor precision, an excessive false-positive rate, or a tiny test split are
    all hard blockers. Emphasising false negatives is reflected in both
    ``min_recall`` and ``max_fnr``; ``min_precision``/``max_fpr`` prevent a model
    from gaming recall by flagging every candidate.
    """
    reasons: list[str] = []
    if not provenance.get("real_world_data", False):
        reasons.append("trained only on curated synthetic data; not production-grade")
    auc = metrics.get("roc_auc")
    if auc is None or float(auc) < min_auc:
        reasons.append(f"ROC-AUC below {min_auc:.2f} (got {auc})")
    if float(metrics.get("recall", 0.0)) < min_recall:
        reasons.append(f"recall below {min_recall:.2f} (got {metrics.get('recall'):.2f})")
    if float(metrics.get("fnr", 1.0)) > max_fnr:
        reasons.append(f"false-negative rate above {max_fnr:.2f} (got {metrics.get('fnr'):.2f})")
    if float(metrics.get("precision", 0.0)) < min_precision:
        reasons.append(f"precision below {min_precision:.2f} (got {metrics.get('precision'):.2f})")
    if float(metrics.get("fpr", 1.0)) > max_fpr:
        reasons.append(f"false-positive rate above {max_fpr:.2f} (got {metrics.get('fpr'):.2f})")
    if int(metrics.get("support", 0)) < 100:
        reasons.append("test split smaller than 100 examples")
    if metrics.get("degenerate"):
        reasons.append("degenerate single-class evaluation split")
    return (not reasons), reasons


# ------------------------------------------------------------------ persistence
def save_model_bundle(
    model_dir: str | Path,
    *,
    family: str,
    version: str,
    payload: dict[str, Any],
    approved: bool,
    metrics: dict[str, Any],
    provenance: dict[str, Any],
    limitations: list[str],
    implementation: str = "",
) -> dict[str, Any]:
    """Write a joblib artifact plus JSON metadata and return the manifest entry."""
    directory = Path(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{family}_{version}.joblib"
    metadata_name = f"{family}_{version}.meta.json"
    payload = dict(payload)
    payload["model_version"] = version
    payload["approved"] = bool(approved)
    payload["limitations"] = list(limitations)
    joblib.dump(payload, directory / artifact_name, compress=3)

    entry = {
        "model_name": str(payload["model_name"]),
        "model_version": version,
        "family": family,
        "kind": payload.get("kind", "unknown"),
        "implementation": implementation,
        "approved": bool(approved),
        "active": bool(approved),
        "artifact": artifact_name,
        "metadata": metadata_name,
        "metrics": metrics,
        "provenance": dict(provenance),
        "limitations": list(limitations),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (directory / metadata_name).write_text(
        json.dumps(entry, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    return entry


def write_manifest(model_dir: str | Path, entries: list[dict[str, Any]], version: str) -> Path:
    """Write the single manifest that inference uses to find approved artifacts."""
    directory = Path(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    models: dict[str, Any] = {}
    for entry in entries:
        models.setdefault(entry["family"], {"versions": []})["versions"].append(entry)
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "training_version": version,
        "models": models,
    }
    path = directory / MANIFEST_FILENAME
    path.write_text(json.dumps(manifest, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return path


# -------------------------------------------------------------------------- main
def train_all(
    data_dir: str,
    model_dir: str,
    repos: Any = None,
    *,
    difraud_domains: dict[str, tuple[str, ...]] | None = None,
    include_difraud: bool = True,
) -> dict[str, Any]:
    """Train all model families and publish approved versions.

    Args:
        data_dir: Directory containing ``raw/emscad_v1.csv`` and optionally
            ``datasets/difraud/<domain>/*.jsonl``. Relative paths are resolved
            against the current directory and the backend root.
        model_dir: Destination for joblib artifacts, JSON metadata and manifest.
        repos: Optional ``Repositories`` instance. Approved models are registered
            through ``repos.models.register(...)`` when supplied.
        difraud_domains: Optional mapping of family to domain tuples. Defaults to
            message=(phishing, sms) and job=(job_scams,).
        include_difraud: Set False to train the legacy families only.

    Returns:
        A JSON-serialisable summary including provenance, split sizes, every
        model version and its held-out metrics.
    """
    frame, provenance, notes = load_job_dataset(data_dir)
    train, validation, test = stratified_split(frame)
    min_df = 1 if len(train) < 200 else 2
    fingerprint = hashlib.sha1(
        f"{provenance.get('source_file', provenance['name'])}|{len(frame)}|{RANDOM_SEED}".encode("utf-8")
    ).hexdigest()[:6]
    version = "v" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + fingerprint

    limitations = [
        "Text-only model: no independent verification of employer, domain or sender is performed.",
        "English-language EMSCAD corpus; performance on other languages is unvalidated.",
    ]
    trained: list[tuple[str, dict[str, Any], dict[str, Any], str, dict[str, Any], list[str]]] = []

    for family in (_FAMILY_JOB_LOGREG, _FAMILY_JOB_SVC):
        payload, metrics = _fit_text_model(
            family=family,
            train=train,
            validation=validation,
            test=test,
            provenance=provenance,
            limitations=limitations,
            min_df=min_df,
        )
        approved, reasons = _approval(
            metrics, provenance, min_auc=0.70, min_recall=0.35, max_fnr=0.70
        )
        if reasons:
            notes.append(f"{family} not approved: " + "; ".join(reasons))
        trained.append((family, payload, metrics, "sklearn.linear_model", provenance, reasons))

    # Message model: real labelled recruitment-message data is not available.
    # It is trained and evaluated for transparency, but can never be promoted.
    synthetic_rows = load_synthetic_messages()
    message_frame = pd.DataFrame(
        {
            "text": [normalize_text(str(row["text"])) for row in synthetic_rows],
            "label": [1 if row["label"] == "fraudulent" else 0 for row in synthetic_rows],
        }
    )
    if min(message_frame["label"].value_counts()) >= 2:
        msg_train, msg_val, msg_test = stratified_split(message_frame)
        msg_payload, msg_metrics = _fit_text_model(
            family=_FAMILY_MESSAGE,
            train=msg_train,
            validation=msg_val,
            test=msg_test,
            provenance=SYNTHETIC_PROVENANCE,
            limitations=[
                "Curated synthetic messages only; not real-world data and not production-grade.",
                "Small corpus: metrics are optimistic and must not be used as performance claims.",
            ],
            min_df=1,
        )
        _, reasons = _approval(
            msg_metrics, SYNTHETIC_PROVENANCE, min_auc=0.70, min_recall=0.35, max_fnr=0.70
        )
        notes.append(
            "message_tfidf_logreg not approved: trained only on curated synthetic data; "
            "kept for audit while the approved DIFrauD message family is preferred at runtime."
        )
        trained.append((_FAMILY_MESSAGE, msg_payload, msg_metrics, "sklearn.linear_model", dict(SYNTHETIC_PROVENANCE), reasons))

    # DIFrauD: real labelled deception text. Each family uses the benchmark's
    # own train/validation/test splits, so thresholds are chosen on validation
    # and metrics come from untouched held-out data. These families are skipped
    # (with a note) when the optional corpus is not present under data_dir.
    difraud_families = {
        _FAMILY_DIFRAUD_MESSAGE: tuple(difraud_domains.get("message", DIFRAUD_MESSAGE_DOMAINS))
        if difraud_domains
        else DIFRAUD_MESSAGE_DOMAINS,
        _FAMILY_DIFRAUD_JOB: tuple(difraud_domains.get("job", DIFRAUD_JOB_DOMAINS))
        if difraud_domains
        else DIFRAUD_JOB_DOMAINS,
    }
    difraud_provenance: dict[str, Any] | None = None
    if include_difraud:
        for family, domains in difraud_families.items():
            try:
                loaded = load_difraud_dataset(data_dir, domains)
            except Exception as exc:  # noqa: BLE001 - optional corpus must not break training
                note = f"{family} skipped: DIFrauD load failed ({type(exc).__name__}: {exc})."
                logger.warning(note)
                notes.append(note)
                continue
            if loaded is None:
                notes.append(
                    f"{family} skipped: DIFrauD corpus not found under {data_dir}; "
                    "runtime keeps its current fallback."
                )
                continue
            d_train, d_val, d_test, d_provenance = loaded
            difraud_provenance = d_provenance
            family_provenance = dict(d_provenance)
            family_provenance["model_family_domains"] = list(domains)
            payload, metrics = _fit_text_model(
                family=family,
                train=d_train,
                validation=d_val,
                test=d_test,
                provenance=family_provenance,
                limitations=difraud_limitations(domains),
                min_df=2,
            )
            approved, reasons = _approval(
                metrics, family_provenance, min_auc=0.70, min_recall=0.35, max_fnr=0.70
            )
            if reasons:
                notes.append(f"{family} not approved: " + "; ".join(reasons))
            trained.append(
                (family, payload, metrics, "sklearn.linear_model", family_provenance, reasons)
            )

    anomaly_limitations = [
        *limitations,
        "Contextual anomaly features (domain age, reputation, company age, scam reports) are absent from EMSCAD "
        "and are treated as neutral zeroes during training; runtime values from upstream lookups are unvalidated.",
    ]
    train_x = _anomaly_matrix(train)
    val_x = _anomaly_matrix(validation)
    test_x = _anomaly_matrix(test)

    iforest_payload, iforest_metrics = _fit_iforest(
        train_x, val_x, test_x, train, validation, test, provenance, anomaly_limitations
    )
    _, iforest_reasons = _approval(
        iforest_metrics, provenance, min_auc=0.60, min_recall=0.20, max_fnr=0.85
    )
    if iforest_reasons:
        notes.append("anomaly_iforest not approved: " + "; ".join(iforest_reasons))
    trained.append((_FAMILY_IFOREST, iforest_payload, iforest_metrics, "sklearn.IsolationForest", provenance, iforest_reasons))

    supervised_payload, supervised_metrics, implementation = _fit_supervised_anomaly(
        train_x, val_x, test_x, train, validation, test, provenance, anomaly_limitations
    )
    _, supervised_reasons = _approval(
        supervised_metrics, provenance, min_auc=0.75, min_recall=0.40, max_fnr=0.70
    )
    if supervised_reasons:
        notes.append(f"{implementation} not approved: " + "; ".join(supervised_reasons))
    trained.append((_FAMILY_SUPERVISED, supervised_payload, supervised_metrics, implementation, provenance, supervised_reasons))

    entries: list[dict[str, Any]] = []
    model_summaries: list[dict[str, Any]] = []
    for family, payload, metrics, implementation, model_provenance, reasons in trained:
        approved = not reasons
        entry = save_model_bundle(
            model_dir,
            family=family,
            version=version,
            payload=payload,
            approved=approved,
            metrics=metrics,
            provenance=model_provenance,
            limitations=payload.get("limitations", []),
            implementation=implementation,
        )
        entries.append(entry)
        model_summaries.append(
            {
                "model_name": entry["model_name"],
                "family": family,
                "model_version": version,
                "approved": approved,
                "implementation": implementation,
                "metrics": metrics,
                "rejection_reasons": reasons,
            }
        )
        if approved and repos is not None:
            try:
                repos.models.register(
                    {
                        "model_name": entry["model_name"],
                        "model_version": version,
                        "family": family,
                        "implementation": implementation,
                        "approved": True,
                        "metrics": metrics,
                        "provenance": model_provenance,
                        "artifact": entry["artifact"],
                    }
                )
            except Exception as exc:  # noqa: BLE001 - training must survive DB outages
                message = f"Could not register {family} in model registry: {type(exc).__name__}: {exc}"
                logger.warning(message)
                notes.append(message)

    manifest_path = write_manifest(model_dir, entries, version)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "training_version": version,
        "data": {
            "provenance": provenance,
            "difraud_provenance": difraud_provenance,
            "rows_after_cleaning": len(frame),
            "split_sizes": {
                "train": len(train),
                "validation": len(validation),
                "test": len(test),
            },
        },
        "models": model_summaries,
        "approved_models": [row["model_name"] for row in model_summaries if row["approved"]],
        "manifest": str(manifest_path),
        "model_dir": str(Path(model_dir).resolve()),
        "notes": notes,
    }
