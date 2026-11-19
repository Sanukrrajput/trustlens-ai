"""Isolation Forest, Random Forest and optional DBSCAN detection with versioned models.

All outputs are scores/flags, explicitly not calibrated probabilities. Models are
only used once trained and registered; untrained models produce no detections.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

from app.detection.features import FEATURE_NAMES, build_feature_vectors
from app.utils import make_id, utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


def _matrix(vectors: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([[float(v["features"][name]) for name in FEATURE_NAMES] for v in vectors], dtype=float)


class MLDetector:
    def __init__(self, settings: "Settings", repos: "Repositories"):
        self.settings = settings
        self.repos = repos
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def ensure_registry(self) -> None:
        for name, model_type in (("isolation_forest", "unsupervised_anomaly"), ("random_forest", "supervised_classifier")):
            if not self.repos.models.find_one({"name": name}):
                self.repos.models.register(
                    {
                        "name": name,
                        "version": "untrained",
                        "model_type": model_type,
                        "status": "untrained",
                        "is_active": False,
                        "features": FEATURE_NAMES,
                        "metrics": {},
                        "created_at": utcnow(),
                        "note": "No validated labeled training data available yet",
                    }
                )

    def status(self) -> list[dict[str, Any]]:
        return [doc for doc in self.repos.models.find({}, sort_field="created_at", limit=100)]

    def _load(self, name: str) -> dict[str, Any] | None:
        active = self.repos.models.active(name)
        if not active or active.get("status") != "trained":
            return None
        path = Path(str(active.get("artifact_path") or ""))
        if not path.is_file():
            logger.warning("Model artifact missing name=%s path=%s", name, path)
            return None
        stat = path.stat()
        cached = self._cache.get(name)
        if cached and cached[0] == stat.st_mtime:
            return cached[1]
        artifact = joblib.load(path)
        self._cache[name] = (stat.st_mtime, artifact)
        return artifact

    def score(
        self,
        vectors: list[dict[str, Any]],
        indicators_map: dict[str, dict] | None = None,
    ) -> list[dict[str, Any]]:
        indicators_map = indicators_map or {}
        if not vectors:
            return []
        results: list[dict[str, Any]] = []
        matrix = _matrix(vectors)

        iso = self._load("isolation_forest")
        if iso:
            scaler: StandardScaler = iso["scaler"]
            model: IsolationForest = iso["model"]
            transformed = scaler.transform(matrix)
            decisions = np.asarray(model.decision_function(transformed), dtype=float)
            clusters = self._clusters(iso, transformed)
            for index, vector in enumerate(vectors):
                anomaly_score = float(100.0 / (1.0 + math.exp(3.0 * float(decisions[index]))))
                if anomaly_score < 60:
                    continue
                severity = "high" if anomaly_score >= 85 else "medium" if anomaly_score >= 70 else "low"
                signals = {
                    "anomaly_score": round(anomaly_score, 2),
                    "decision_value": round(float(decisions[index]), 4),
                    "cluster_id": clusters[index] if clusters is not None else None,
                    "feature_values": vector["features"],
                }
                results.append(
                    self._candidate(
                        vector=vector,
                        rule_id="ML_IF",
                        title="Behavioral anomaly detected by Isolation Forest",
                        severity=severity,
                        confidence=min(0.8, anomaly_score / 100.0),
                        reasons=[
                            f"unsupervised anomaly score {anomaly_score:.1f}/100 exceeds the alerting band",
                            "score is a relative ranking signal, not a calibrated probability",
                        ],
                        signals=signals,
                        model_version=str(iso.get("version") or "unknown"),
                        indicators_map=indicators_map,
                    )
                )

        forest = self._load("random_forest")
        if forest:
            scaler = forest["scaler"]
            classifier: RandomForestClassifier = forest["model"]
            probabilities = classifier.predict_proba(scaler.transform(matrix))
            labels = list(classifier.classes_)
            if "malicious" in labels:
                index = labels.index("malicious")
                for vector, row in zip(vectors, probabilities):
                    malicious_probability = float(row[index])
                    if malicious_probability < float(forest.get("threshold", 0.60)):
                        continue
                    results.append(
                        self._candidate(
                            vector=vector,
                            rule_id="ML_RF",
                            title="Labeled classifier flagged suspicious behavior",
                            severity="high" if malicious_probability >= 0.8 else "medium",
                            confidence=round(malicious_probability, 3),
                            reasons=[
                                "supervised model trained on analyst-verified labels matched this feature vector",
                                "model output requires analyst confirmation and is not proof of compromise",
                            ],
                            signals={"malicious_class_score": round(malicious_probability, 4), "feature_values": vector["features"]},
                            model_version=str(forest.get("version") or "unknown"),
                            indicators_map=indicators_map,
                        )
                    )
        return results

    @staticmethod
    def _clusters(artifact: dict[str, Any], transformed: np.ndarray) -> list[int] | None:
        params = artifact.get("dbscan")
        if not params:
            return None
        try:
            labels = DBSCAN(eps=float(params["eps"]), min_samples=int(params["min_samples"])).fit_predict(transformed)
            return [int(label) for label in labels]
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _candidate(
        *,
        vector: dict[str, Any],
        rule_id: str,
        title: str,
        severity: str,
        confidence: float,
        reasons: list[str],
        signals: dict[str, Any],
        model_version: str,
        indicators_map: dict[str, dict],
    ) -> dict[str, Any]:
        start = vector["window_start"]
        return {
            "type": "ml",
            "rule_id": rule_id,
            "title": title,
            "severity": severity,
            "base_score": {"low": 25, "medium": 45, "high": 70, "critical": 90}.get(severity, 25),
            "confidence": confidence,
            "reasons": reasons,
            "signals": signals,
            "event_ids": vector["event_ids"],
            "entity_key": vector["entity_key"],
            "source_ip": vector.get("source_ip"),
            "actor_user": vector.get("actor_user"),
            "asset_ids": vector.get("asset_ids", []),
            "indicator_ids": [],
            "ti_confidence": max(
                (float(indicators_map.get(f"ip:{vector.get('source_ip')}", {}).get("confidence") or 0),),
                default=0.0,
            ),
            "asset_criticality": float(vector["features"].get("asset_criticality") or 0),
            "correlation_evidence": min(1.0, 0.15 * len(vector["event_ids"])),
            "window_start": start,
            "model_version": model_version,
            "calibrated": False,
            "detection_key": make_id("det", rule_id, vector["entity_key"], start.isoformat()),
        }


def _metrics(y_true: list[str], y_pred: list[str], positive: str = "malicious") -> dict[str, float]:
    if not y_true:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "false_positive_rate": 0.0}
    labels = sorted(set(y_true + y_pred))
    y_binary = [1 if value == positive else 0 for value in y_true]
    pred_binary = [1 if value == positive else 0 for value in y_pred]
    matrix = confusion_matrix(y_binary, pred_binary, labels=[0, 1])
    tn, fp = (int(matrix[0][0]), int(matrix[0][1])) if matrix.size == 4 else (0, 0)
    return {
        "precision": round(float(precision_score(y_binary, pred_binary, zero_division=0)), 4),
        "recall": round(float(recall_score(y_binary, pred_binary, zero_division=0)), 4),
        "f1": round(float(f1_score(y_binary, pred_binary, zero_division=0)), 4),
        "false_positive_rate": round(fp / max(1, fp + tn), 4),
        "labels": labels,
    }


def train_models(settings: "Settings", repos: "Repositories") -> dict[str, Any]:
    """Train, evaluate and register versioned models from verified labeled events.

    Splitting is performed by entity key so events from the same user/host never
    appear in both training and test sets (no group leakage).
    """
    events = repos.events.labeled(limit=20000)
    if len(events) < int(settings.ml_min_train_samples):
        return {
            "status": "insufficient_data",
            "available_events": len(events),
            "required_events": settings.ml_min_train_samples,
            "message": "Rule-based detection remains active; ML model stays untrained.",
        }
    indicators_map = repos.indicators.malicious_map()
    vectors = build_feature_vectors(events, indicators_map)
    by_id = {str(event["event_id"]): event for event in events}
    labeled_vectors: list[dict[str, Any]] = []
    for vector in vectors:
        labels = {by_id[eid]["label"] for eid in vector["event_ids"] if eid in by_id and by_id[eid].get("label")}
        if len(labels) == 1:
            vector["label"] = next(iter(labels))
            labeled_vectors.append(vector)
    if len(labeled_vectors) < 10:
        return {"status": "insufficient_data", "available_groups": len(labeled_vectors), "required_groups": 10}

    rng = np.random.default_rng(42)
    entities = sorted({vector["entity_key"] for vector in labeled_vectors})
    rng.shuffle(entities)
    test_entities = set(entities[: max(1, int(len(entities) * 0.2))])
    train = [v for v in labeled_vectors if v["entity_key"] not in test_entities]
    test = [v for v in labeled_vectors if v["entity_key"] in test_entities]
    if not train or not test:
        return {"status": "insufficient_data", "message": "Need at least two independent entities for a grouped split."}

    x_train_raw, x_test_raw = _matrix(train), _matrix(test)
    scaler = StandardScaler().fit(x_train_raw)
    x_train, x_test = scaler.transform(x_train_raw), scaler.transform(x_test_raw)
    y_train = [str(v["label"]) for v in train]
    y_test = [str(v["label"]) for v in test]

    iso = IsolationForest(
        n_estimators=200,
        contamination=float(settings.if_contamination),
        random_state=42,
        n_jobs=-1,
    ).fit(x_train)
    iso_pred = ["malicious" if int(p) == -1 else "benign" for p in iso.predict(x_test)]
    iso_metrics = _metrics(y_test, iso_pred)

    classifier = RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    ).fit(x_train, y_train)
    rf_pred = [str(p) for p in classifier.predict(x_test)]
    rf_metrics = _metrics(y_test, rf_pred)

    dbscan = DBSCAN(eps=1.5, min_samples=3).fit(x_train)
    cluster_count = len(set(int(c) for c in dbscan.labels_) - {-1})

    version = utcnow().strftime("%Y%m%d%H%M%S")
    model_dir = Path(settings.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "isolation_forest": {
            "model": iso,
            "scaler": scaler,
            "features": FEATURE_NAMES,
            "version": version,
            "dbscan": {"eps": 1.5, "min_samples": 3, "clusters": cluster_count},
        },
        "random_forest": {
            "model": classifier,
            "scaler": scaler,
            "features": FEATURE_NAMES,
            "version": version,
            "threshold": 0.60,
        },
    }
    registered = []
    for name, artifact in artifacts.items():
        path = model_dir / f"{name}_{version}.joblib"
        joblib.dump(artifact, path)
        metrics = iso_metrics if name == "isolation_forest" else rf_metrics
        doc = {
            "name": name,
            "version": version,
            "model_type": "unsupervised_anomaly" if name == "isolation_forest" else "supervised_classifier",
            "status": "trained",
            "is_active": True,
            "artifact_path": str(path.resolve()),
            "features": FEATURE_NAMES,
            "metrics": metrics,
            "trained_at": utcnow(),
            "train_groups": len(train),
            "test_groups": len(test),
            "split": "grouped_by_entity_no_leakage",
            "calibrated": False,
            "note": "Scores are relative/an uncalibrated class score; analyst verification required.",
        }
        repos.models.register(doc)
        registered.append(doc)
    return {
        "status": "trained",
        "version": version,
        "train_groups": len(train),
        "test_groups": len(test),
        "isolation_forest": iso_metrics,
        "random_forest": rf_metrics,
        "dbscan_clusters": cluster_count,
        "models": registered,
    }
