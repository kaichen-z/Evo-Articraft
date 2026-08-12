"""Dependency-free binary evaluation. Positive means human FAIL."""

from __future__ import annotations

from typing import Any


def auc(failure_scores: list[float], pass_scores: list[float]) -> float | None:
    if not failure_scores or not pass_scores:
        return None
    correct = ties = 0
    for bad in failure_scores:
        for good in pass_scores:
            if bad < good:
                correct += 1
            elif bad == good:
                ties += 1
    return (correct + 0.5 * ties) / (len(failure_scores) * len(pass_scores))


def evaluate_item(rows: list[dict[str, Any]], item: str) -> dict[str, Any]:
    human_labeled = [r for r in rows if r.get("human") in {"满足", "不满足"}]
    decided = [r for r in human_labeled if r.get("score") is not None]
    predicted = [r for r in decided if r.get("prediction") in {"pass", "fail"}]
    tp = sum(r["human"] == "不满足" and r["prediction"] == "fail" for r in predicted)
    fp = sum(r["human"] == "满足" and r["prediction"] == "fail" for r in predicted)
    fn = sum(r["human"] == "不满足" and r["prediction"] == "pass" for r in predicted)
    tn = sum(r["human"] == "满足" and r["prediction"] == "pass" for r in predicted)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    tpr = recall
    tnr = tn / (tn + fp) if tn + fp else None
    balanced = (tpr + tnr) / 2 if tpr is not None and tnr is not None else None
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total else None
    if total:
        human_fail = (tp + fn) / total
        predicted_fail = (tp + fp) / total
        expected_agreement = (
            human_fail * predicted_fail
            + (1.0 - human_fail) * (1.0 - predicted_fail)
        )
        kappa = (
            (accuracy - expected_agreement) / (1.0 - expected_agreement)
            if expected_agreement < 1.0
            else None
        )
    else:
        kappa = None
    bad = [float(r["score"]) for r in decided if r["human"] == "不满足"]
    good = [float(r["score"]) for r in decided if r["human"] == "满足"]
    return {
        "item": item,
        "human_labeled": len(human_labeled),
        "scored": len(decided),
        "decided": len(predicted),
        "coverage": len(decided) / len(human_labeled) if human_labeled else 0.0,
        "decision_coverage": len(predicted) / len(decided) if decided else 0.0,
        "human_failures_scored": len(bad),
        "human_passes_scored": len(good),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "balanced_accuracy": balanced,
        "accuracy": accuracy,
        "kappa": kappa,
        "auc": auc(bad, good),
        "false_positive_ids": [r["record_id"] for r in predicted if r["human"] == "满足" and r["prediction"] == "fail"],
        "false_negative_ids": [r["record_id"] for r in predicted if r["human"] == "不满足" and r["prediction"] == "pass"],
    }
