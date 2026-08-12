from __future__ import annotations

import json
from typing import Any

from ..types import Coverage, MetricResult, Prediction

VERIFIER_VERSION = "articraft-a1-a6-v0.1"


def build_report(results: dict[str, MetricResult]) -> dict[str, Any]:
    counted = [result for result in results.values() if result.counts_in_aggregate]
    provisional = sorted({
        name for result in results.values() for name in result.provisional_params
    })
    failures = [
        result.failure_reason for result in results.values()
        if result.coverage is Coverage.TOOL_FAILURE and result.failure_reason
    ]
    repair_queue: list[str] = []
    for result in results.values():
        if (result.prediction is Prediction.FAIL and result.repair_hint
                and result.repair_hint not in repair_queue):
            repair_queue.append(result.repair_hint)
    return {
        "verifier_version": VERIFIER_VERSION,
        "human_metrics": {name: result.to_dict() for name, result in results.items()},
        "coverage": {
            "scored_metrics": len(counted),
            "total_metrics": len(results),
            "rate": round(len(counted) / len(results), 4) if results else 0.0,
        },
        "tool_failures": failures,
        "provisional_params": provisional,
        "repair_queue": repair_queue,
    }


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
