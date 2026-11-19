"""Deterministic metric computation and recall-oriented threshold selection.

Design notes
------------
* Fraud screening is asymmetric: a false negative (missed scam) harms a candidate
  far more than a false positive (extra review). Threshold selection therefore
  minimises false-negative rate subject to a minimum precision floor, instead of
  blindly using 0.5 or maximising accuracy.
* ROC-AUC and PR-AUC are reported together. PR-AUC (average precision) is the
  more informative ranking metric for the heavily imbalanced EMSCAD corpus.
* Degenerate evaluation splits (single class) are reported explicitly rather
  than raising or silently returning a flattering score.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score


def _as_float_array(values: Sequence[Any] | Iterable[Any] | np.ndarray) -> np.ndarray:
    return np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=np.float64)


def binary_metrics(
    y_true: Sequence[int] | np.ndarray,
    y_pred: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray | None = None,
    *,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Compute classification and ranking metrics for a binary fraud task.

    ``1`` always means the positive (fraudulent) class. All returned numbers are
    plain Python types so the result can be serialised directly to JSON.
    """
    truth = _as_float_array(y_true).astype(int)
    predicted = _as_float_array(y_pred).astype(int)
    if truth.shape != predicted.shape:
        raise ValueError("y_true and y_pred must have the same length")
    if truth.size == 0:
        raise ValueError("cannot compute metrics on an empty evaluation set")

    matrix = confusion_matrix(truth, predicted, labels=[0, 1])
    tn, fp, fn, tp = (int(value) for value in matrix.ravel())
    positives = tp + fn
    negatives = tn + fp

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / positives if positives else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / negatives if negatives else 0.0
    fnr = fn / positives if positives else 0.0
    accuracy = (tp + tn) / truth.size

    roc_auc: float | None = None
    pr_auc: float | None = None
    degenerate = bool(len(np.unique(truth)) < 2)
    if y_score is not None and not degenerate:
        scores = _as_float_array(y_score)
        if scores.shape != truth.shape:
            raise ValueError("y_score must have the same length as y_true")
        roc_auc = float(roc_auc_score(truth, scores))
        pr_auc = float(average_precision_score(truth, scores))
    elif not degenerate:
        # Without scores we can still report prevalence as the trivial baseline.
        pr_auc = float(positives / truth.size)

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "accuracy": float(accuracy),
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "fpr": float(fpr),
        "fnr": float(fnr),
        "support": int(truth.size),
        "positives": int(positives),
        "negatives": int(negatives),
        "threshold": float(threshold) if threshold is not None else None,
        "degenerate": degenerate,
    }


def threshold_sweep(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    thresholds: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate a fixed grid of thresholds. Useful for audit trails."""
    truth = _as_float_array(y_true).astype(int)
    scores = _as_float_array(y_score)
    if truth.shape != scores.shape:
        raise ValueError("y_true and y_score must have the same length")
    grid = list(thresholds) if thresholds is not None else list(np.linspace(0.05, 0.95, 19))
    results: list[dict[str, Any]] = []
    seen: set[float] = set()
    for candidate in sorted(float(value) for value in grid):
        if candidate in seen:
            continue
        seen.add(candidate)
        predicted = (scores >= candidate).astype(int)
        metrics = binary_metrics(truth, predicted, scores, threshold=candidate)
        results.append(metrics)
    return results


def select_threshold(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    *,
    min_precision: float = 0.35,
    max_fnr: float = 0.30,
) -> float:
    """Pick a decision threshold on validation data, favouring recall.

    Procedure:
      1. Consider observed scores plus a regular grid in [0.05, 0.95].
      2. Keep candidates meeting ``precision >= min_precision``.
      3. Among those, minimise FNR; break ties with the highest F1.
      4. If nothing qualifies, maximise F1 with FNR as the tiebreak.
      5. If the split is degenerate, return 0.5.

    The floor prevents the recall preference from degenerating into "flag
    everything", which would make the risk score useless.
    """
    truth = _as_float_array(y_true).astype(int)
    scores = _as_float_array(y_score)
    if truth.shape != scores.shape:
        raise ValueError("y_true and y_score must have the same length")
    if truth.size == 0 or len(np.unique(truth)) < 2:
        return 0.5

    observed = [float(value) for value in np.unique(scores) if 0.0 <= float(value) <= 1.0]
    grid = [float(value) for value in np.linspace(0.05, 0.95, 19)]
    candidates = sorted(set(observed + grid))
    evaluated = threshold_sweep(truth, scores, candidates)

    feasible = [
        row for row in evaluated
        if row["precision"] >= min_precision and row["fnr"] <= max_fnr
    ]
    if not evaluated:
        return 0.5
    if feasible:
        # Recall is the primary objective once the precision floor is met.
        best = min(feasible, key=lambda row: (row["fnr"], -row["f1"], row["threshold"]))
    else:
        # Never degrade to "flag everything" just because the precision floor
        # was unreachable: fall back to the best balanced F1 instead.
        best = min(evaluated, key=lambda row: (-row["f1"], row["fnr"], row["threshold"]))
    return float(best["threshold"])


def anomaly_metrics(
    y_true: Sequence[int] | np.ndarray,
    anomaly_scores: Sequence[float] | np.ndarray,
    *,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Evaluate an unsupervised/novelty anomaly scorer.

    ``anomaly_scores`` must be oriented so that *higher means more anomalous*.
    For scikit-learn ``IsolationForest.score_samples`` this requires negating the
    output; training code does that explicitly.
    """
    scores = _as_float_array(anomaly_scores)
    truth = _as_float_array(y_true).astype(int)
    if scores.shape != truth.shape:
        raise ValueError("y_true and anomaly_scores must have the same length")
    effective = threshold if threshold is not None else float(np.median(scores)) if scores.size else 0.5
    predicted = (scores >= effective).astype(int)
    return binary_metrics(truth, predicted, scores, threshold=effective)
