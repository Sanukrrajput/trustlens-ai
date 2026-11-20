"""Tests for TrustLens AI ML training, inference, evaluation and risk scoring.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_ml.py -q --tb=short
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.risk_engine import _categorise, score_risk  # noqa: E402
from app.ml.datasets.synthetic_messages import (  # noqa: E402
    DATASET_PROVENANCE as SYNTHETIC_PROVENANCE,
)
from app.ml.datasets.synthetic_messages import load_synthetic_messages  # noqa: E402
from app.ml.evaluation.metrics import (  # noqa: E402
    anomaly_metrics,
    binary_metrics,
    select_threshold,
)
from app.ml.features import (  # noqa: E402
    ANOMALY_FEATURE_NAMES,
    build_anomaly_vector,
    normalize_text,
)
from app.ml.inference.predictor import TextPredictor  # noqa: E402
from app.ml.training.train import (  # noqa: E402
    _approval,
    _parse_label,
    _text_pipeline,
    load_emscad_dataset,
    save_model_bundle,
    train_all,
    write_manifest,
)
from app.schemas import ModelPrediction, RiskAssessment  # noqa: E402

REQUIRED_PREDICTION_KEYS = {
    "model_name",
    "model_version",
    "prediction",
    "fraud_probability",
    "confidence",
    "contributing_features",
    "limitations",
}


# ------------------------------------------------------------------- data tests
def test_label_parsing_accepts_emscad_t_f_and_conventional_values() -> None:
    assert _parse_label("t") == 1
    assert _parse_label("T") == 1
    assert _parse_label("true") == 1
    assert _parse_label(1) == 1
    assert _parse_label("f") == 0
    assert _parse_label("FALSE") == 0
    assert _parse_label(0.0) == 0
    assert _parse_label("maybe") is None
    assert _parse_label(None) is None


def test_data_validation_drops_invalid_labels_and_duplicates(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    rows: list[dict[str, str]] = []
    # Use alphabetic markers: digit sequences are normalised to a single sentinel,
    # so numeric-only differences would correctly be treated as duplicates.
    markers = "abcdefghijklmnopqrst"
    for marker in markers:
        rows.append(
            {
                "title": f"Engineer role {marker}",
                "description": f"We are hiring a careful engineer for team {marker} with a clear salary and interview process.",
                "fraudulent": "f",
            }
        )
        rows.append(
            {
                "title": f"Work from home vacancy {marker}",
                "description": f"Urgent work from home role {marker} pay a processing fee by wire transfer immediately.",
                "fraudulent": "t",
            }
        )
    # Five exact duplicates after normalisation: they must be removed before split.
    rows.extend(dict(row) for row in rows[:5])
    # Three unusable labels.
    rows.extend({"title": "Bad row", "description": "Some description text that is long enough to survive cleaning.", "fraudulent": value} for value in ("maybe", "", "unknown"))

    pd.DataFrame(rows).to_csv(raw_dir / "emscad_v1.csv", index=False)
    frame, provenance = load_emscad_dataset(str(tmp_path))

    assert len(frame) == 40
    assert provenance["invalid_labels_dropped"] == 3
    assert provenance["duplicates_removed"] == 5
    assert provenance["class_counts"] == {"0": 20, "1": 20}
    assert frame["text"].is_unique
    assert set(frame["label"].unique()) == {0, 1}


def test_synthetic_dataset_is_explicitly_non_production() -> None:
    rows = load_synthetic_messages(include_ambiguous=True, include_incomplete=True)
    labels = {row["label"] for row in rows}
    assert {"legitimate", "fraudulent", "ambiguous", "incomplete"}.issubset(labels)
    assert all(row["provenance"] == SYNTHETIC_PROVENANCE["name"] for row in rows)
    assert SYNTHETIC_PROVENANCE["real_world_data"] is False
    assert SYNTHETIC_PROVENANCE["production_grade"] is False
    assert sum(1 for row in rows if row["trainable"]) >= 30
    # Ambiguous and incomplete rows are excluded from supervised training by default.
    default_labels = {row["label"] for row in load_synthetic_messages()}
    assert "ambiguous" not in default_labels
    assert "incomplete" not in default_labels


# ---------------------------------------------------------------- feature tests
def test_anomaly_vector_is_bounded_canonical_and_leak_free() -> None:
    vector = build_anomaly_vector(
        {
            "payment_terms": 999.0,
            "domain_age": 10.0,  # alias -> domain_age_days
            "unrecognised_field": 42.0,
            "caps_ratio": "not-a-number",
            "text_length": float("nan"),
        }
    )
    assert vector.shape == (len(ANOMALY_FEATURE_NAMES),)
    assert vector[ANOMALY_FEATURE_NAMES.index("payment_terms")] == 50.0
    assert vector[ANOMALY_FEATURE_NAMES.index("domain_age_days")] == 10.0
    assert vector[ANOMALY_FEATURE_NAMES.index("caps_ratio")] == 0.0
    assert vector[ANOMALY_FEATURE_NAMES.index("text_length")] == 0.0
    assert normalize_text("<p>URGENT!! Apply at http://x.io now</p>") == (
        "urgent apply at urltoken now"
    )


# ---------------------------------------------------------------- metric tests
def test_binary_metrics_known_values() -> None:
    y_true = [0, 0, 1, 1]
    y_pred = [0, 1, 1, 1]
    y_score = [0.1, 0.4, 0.35, 0.9]
    metrics = binary_metrics(y_true, y_pred, y_score, threshold=0.5)

    assert metrics["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 0, "tp": 2}
    assert metrics["precision"] == pytest.approx(2 / 3)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["f1"] == pytest.approx(0.8)
    assert metrics["fpr"] == pytest.approx(0.5)
    assert metrics["fnr"] == pytest.approx(0.0)
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["roc_auc"] == pytest.approx(0.75)
    assert metrics["pr_auc"] == pytest.approx(0.8333, abs=0.001)
    assert metrics["degenerate"] is False


def test_binary_metrics_handles_single_class_without_lying() -> None:
    metrics = binary_metrics([1, 1, 1], [1, 0, 1], [0.9, 0.2, 0.8])
    assert metrics["degenerate"] is True
    assert metrics["roc_auc"] is None
    assert metrics["fnr"] == pytest.approx(1 / 3)


def test_threshold_selection_emphasises_false_negatives() -> None:
    y_true = [1, 1, 0, 0, 1, 0]
    y_score = [0.9, 0.8, 0.7, 0.6, 0.45, 0.4]
    threshold = select_threshold(y_true, y_score, min_precision=0.35, max_fnr=0.30)
    metrics = binary_metrics(y_true, [int(score >= threshold) for score in y_score], y_score)
    assert threshold < 0.5
    assert metrics["fnr"] <= 0.30
    assert metrics["recall"] >= 0.9


def test_anomaly_metrics_orientation() -> None:
    truth = [0, 0, 1, 1]
    scores = [0.1, 0.2, 0.8, 0.9]
    metrics = anomaly_metrics(truth, scores, threshold=0.5)
    assert metrics["confusion_matrix"] == {"tn": 2, "fp": 0, "fn": 0, "tp": 2}
    assert metrics["roc_auc"] == pytest.approx(1.0)


# ------------------------------------------------------------- inference tests
def _assert_prediction_contract(result: dict) -> None:
    assert REQUIRED_PREDICTION_KEYS.issubset(result)
    ModelPrediction(**result)
    assert 0.0 <= result["fraud_probability"] <= 1.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["contributing_features"], list)
    assert isinstance(result["limitations"], list)


def test_inference_fallback_is_honest_when_no_artifacts_exist(tmp_path: Path) -> None:
    predictor = TextPredictor(str(tmp_path / "missing_models"))
    fraud_text = "URGENT! Pay a processing fee by wire transfer now, no interview, send your bank details."
    for result in (
        predictor.predict_job(fraud_text),
        predictor.predict_message(fraud_text, channel="sms"),
    ):
        _assert_prediction_contract(result)
        assert result["model_name"].endswith("_rule_fallback")
        assert result["prediction"] == "fraudulent"
        assert result["fraud_probability"] > 0.5
        assert any("rule-based fallback" in item for item in result["limitations"])
        assert any("not a trained model" in item for item in result["limitations"])

    anomaly = predictor.predict_anomaly({"payment_terms": 4, "domain_reputation_score": 0.1})
    _assert_prediction_contract(anomaly)
    assert anomaly["model_name"].endswith("_rule_fallback")

    short = predictor.predict_job("Apply now")
    assert short["prediction"] == "inconclusive"


def test_manifest_only_loads_approved_artifacts(tmp_path: Path) -> None:
    pipeline = _text_pipeline(min_df=1)
    pipeline.fit(
        ["urgent gift card payment fee now", "thank you for applying to our interview portal salary"],
        [1, 0],
    )
    payload = {
        "schema_version": "1.0",
        "model_name": "job_tfidf_logreg",
        "model_version": "",
        "kind": "text",
        "pipeline": pipeline,
        "fraud_class_index": 1,
        "threshold": 0.5,
        "feature_names": list(pipeline.named_steps["tfidf"].get_feature_names_out()),
        "provenance": {"name": "test", "real_world_data": True},
        "limitations": ["test limitations"],
        "approved": False,
    }

    rejected = save_model_bundle(
        tmp_path,
        family="job_tfidf_logreg",
        version="vtest-rejected",
        payload=payload,
        approved=False,
        metrics={},
        provenance={"name": "test"},
        limitations=[],
    )
    write_manifest(tmp_path, [rejected], "vtest-rejected")
    fallback_result = TextPredictor(str(tmp_path)).predict_job("urgent gift card payment fee now")
    assert fallback_result["model_name"].endswith("_rule_fallback")

    approved = save_model_bundle(
        tmp_path,
        family="job_tfidf_logreg",
        version="vtest-approved",
        payload=payload,
        approved=True,
        metrics={},
        provenance={"name": "test"},
        limitations=[],
    )
    write_manifest(tmp_path, [approved], "vtest-approved")
    trained = TextPredictor(str(tmp_path)).predict_job("urgent gift card payment fee now")
    _assert_prediction_contract(trained)
    assert trained["model_name"] == "job_tfidf_logreg"
    assert trained["model_version"] == "vtest-approved"
    assert trained["contributing_features"]
    assert all(
        set(item) == {"feature", "value", "direction", "description"}
        for item in trained["contributing_features"]
    )


# ----------------------------------------------------------------- risk tests
def _settings() -> Settings:
    return Settings()


def test_risk_category_boundaries() -> None:
    expected = {
        0: "Low observed risk",
        19: "Low observed risk",
        20: "Limited warning signals",
        39: "Limited warning signals",
        40: "Moderate risk",
        59: "Moderate risk",
        60: "High risk",
        79: "High risk",
        80: "Critical risk indicators",
        100: "Critical risk indicators",
    }
    for score, category in expected.items():
        assert _categorise(score) == category


def test_risk_inconclusive_with_no_evidence() -> None:
    result = score_risk(
        ml_predictions=[],
        indicators=[],
        domain=None,
        company=None,
        historical=None,
        message=None,
        settings=_settings(),
    )
    RiskAssessment(**result)
    assert result["inconclusive"] is True
    assert result["data_coverage"] == 0.0
    assert 0 <= result["score"] <= 100
    assert result["evidence_summary"]
    assert result["recommended_actions"]
    assert "reassurance" in result["summary"]
    assert set(result["component_scores"]) == {"content", "url", "brand", "threat", "community"}
    assert result["signal_weights"] == pytest.approx(
        {"content": 0.3, "url": 0.25, "brand": 0.25, "threat": 0.1, "community": 0.1}
    )
    assert result["unavailable_signals"] == ["content", "url", "brand", "threat", "community"]
    assert result["uncertainty"] == pytest.approx(1.0 - result["confidence"])


def test_verified_evidence_outweighs_unverified_evidence() -> None:
    unverified = {
        "name": "unverified claim",
        "status": "suspicious",
        "severity": 0.5,
        "confidence": 0.5,
        "weight": 1.0,
        "independently_verified": False,
    }
    verified = {
        "name": "domain blacklist",
        "status": "confirmed_malicious",
        "severity": 1.0,
        "confidence": 1.0,
        "weight": 1.0,
        "independently_verified": True,
    }

    def score(indicator: dict) -> int:
        return score_risk(
            ml_predictions=[],
            indicators=[indicator],
            domain=None,
            company=None,
            historical=None,
            message=None,
            settings=_settings(),
        )["score"]

    assert score(verified) >= score(unverified) + 20

    malicious_domain = score_risk(
        ml_predictions=[],
        indicators=[],
        domain={"reputation": "malicious"},
        company=None,
        historical=None,
        message=None,
        settings=_settings(),
    )["score"]
    clean_domain = score_risk(
        ml_predictions=[],
        indicators=[],
        domain={"reputation": "clean"},
        company=None,
        historical=None,
        message=None,
        settings=_settings(),
    )["score"]
    assert malicious_domain > clean_domain + 15


def test_model_confidence_is_not_used_as_risk_score() -> None:
    base = {
        "model_name": "job_tfidf_logreg",
        "model_version": "v1",
        "prediction": "legitimate",
        "fraud_probability": 0.2,
        "contributing_features": [],
        "limitations": [],
    }
    low_confidence = score_risk(
        ml_predictions=[{**base, "confidence": 0.05}],
        indicators=[],
        domain=None,
        company=None,
        historical=None,
        message=None,
        settings=_settings(),
    )
    high_confidence = score_risk(
        ml_predictions=[{**base, "confidence": 0.99}],
        indicators=[],
        domain=None,
        company=None,
        historical=None,
        message=None,
        settings=_settings(),
    )
    assert low_confidence["score"] == high_confidence["score"]


def test_high_risk_generates_actionable_guidance() -> None:
    result = score_risk(
        ml_predictions=[],
        indicators=[
            {
                "name": "confirmed scam report",
                "status": "confirmed_malicious",
                "severity": 1.0,
                "confidence": 1.0,
                "weight": 1.0,
                "independently_verified": True,
            }
        ],
        domain={"reputation": "malicious"},
        company={"blacklisted": True},
        historical={"repeat_offender": True},
        message={"payment_demand": True},
        settings=_settings(),
    )
    RiskAssessment(**result)
    assert result["score"] >= 80
    assert result["category"] == "Critical risk indicators"
    assert result["inconclusive"] is False
    assert any("human fraud reviewer" in action for action in result["recommended_actions"])
    assert any("gift cards" in action for action in result["recommended_actions"])


def test_risk_uses_specification_signal_split_and_renormalises() -> None:
    result = score_risk(
        ml_predictions=[],
        indicators=[],
        domain=None,
        company=None,
        historical=None,
        message={"payment_demand": True},
        settings=_settings(),
    )
    assert result["signal_weights"] == pytest.approx(
        {"content": 0.3, "url": 0.25, "brand": 0.25, "threat": 0.1, "community": 0.1}
    )
    assert result["data_coverage"] == pytest.approx(0.3)
    assert result["component_scores"]["content"] > 0
    assert result["component_scores"]["url"] == 0
    assert result["unavailable_signals"] == ["url", "brand", "threat", "community"]

    custom = Settings(
        risk_weight_content=0.6,
        risk_weight_url=0.2,
        risk_weight_brand=0.1,
        risk_weight_threat=0.05,
        risk_weight_community=0.05,
    )
    adjusted = score_risk(
        ml_predictions=[],
        indicators=[],
        domain={"domain_age_days": 10},
        company=None,
        historical=None,
        message={"payment_demand": True},
        settings=custom,
    )
    assert adjusted["signal_weights"]["content"] == pytest.approx(0.6)
    assert adjusted["data_coverage"] == pytest.approx(0.8)
    assert adjusted["weights_version"] != result["weights_version"]


def test_empty_threat_lookup_is_recorded_but_never_treated_as_clean() -> None:
    result = score_risk(
        ml_predictions=[],
        indicators=[],
        domain=None,
        company=None,
        historical=None,
        message=None,
        settings=_settings(),
        threat={"status": "no_match"},
    )
    assert "threat" in result["unavailable_signals"]
    assert result["component_scores"]["threat"] == 0.0
    assert any("absence of a match" in line.lower() for line in result["evidence_summary"])


def test_score_bands_are_configurable_and_validated() -> None:
    settings = Settings(
        risk_band_low_max=9,
        risk_band_limited_max=29,
        risk_band_moderate_max=49,
        risk_band_high_max=69,
    )
    assert _categorise(15, settings) == "Limited warning signals"
    assert _categorise(70, settings) == "Critical risk indicators"
    with pytest.raises(ValueError):
        Settings(
            risk_band_low_max=50,
            risk_band_limited_max=40,
            risk_band_moderate_max=60,
            risk_band_high_max=80,
        )


# ------------------------------------------------------------- training tests
def test_approval_rejects_flag_everything_model() -> None:
    metrics = {
        "roc_auc": 0.95,
        "recall": 1.0,
        "fnr": 0.0,
        "precision": 0.04,
        "fpr": 1.0,
        "support": 1000,
        "degenerate": False,
    }
    approved, reasons = _approval(
        metrics,
        {"real_world_data": True},
        min_auc=0.70,
        min_recall=0.30,
        max_fnr=0.70,
        min_precision=0.15,
        max_fpr=0.40,
    )
    assert approved is False
    assert any("precision" in reason for reason in reasons)
    assert any("false-positive rate" in reason for reason in reasons)


def test_training_fallback_never_approves_synthetic_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the documented synthetic fallback even though the real corpus exists.
    monkeypatch.setattr(
        "app.ml.training.train._resolve_data_path",
        lambda data_dir: tmp_path / "no_such_file.csv",
    )
    summary = train_all(
        data_dir=str(tmp_path / "empty_data"),
        model_dir=str(tmp_path / "models"),
    )
    assert summary["data"]["provenance"]["real_world_data"] is False
    assert summary["approved_models"] == []
    assert all(row["approved"] is False for row in summary["models"])
    assert len(summary["models"]) >= 4
    assert (tmp_path / "models" / "model_manifest.json").is_file()

    predictor = TextPredictor(summary["model_dir"])
    result = predictor.predict_job("URGENT pay a wire transfer processing fee now")
    assert result["model_name"].endswith("_rule_fallback")
