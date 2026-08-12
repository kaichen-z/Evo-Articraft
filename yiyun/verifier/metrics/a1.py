"""A1 零件拆分与活动属性。

S_A1 = F1(movable precision, movable recall) * exp(-N_spurious/max(1,E))

signals 由语义匹配前端产生：
  matched_required_movables: 已匹配的契约活动件 ID
  actual_movable_ids: 实际非 fixed 活动件 ID
  spurious_movable_ids: 无法匹配到契约的多余活动件 ID
"""

from __future__ import annotations

import math

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "A1"


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    requirements = contract.get("required_movables") or []
    required = C.contract_ids(requirements)
    if not requirements:
        return C.not_applicable(METRIC, consts, "Prompt 未明确要求活动件")
    if signals.get("semantic_match_failed"):
        return C.tool_failure(METRIC, consts, "活动件语义匹配工具失败")

    needed = ("matched_required_movables", "actual_movable_ids", "spurious_movable_ids")
    missing = [key for key in needed if signals.get(key) is None]
    if missing:
        return C.tool_failure(METRIC, consts, "缺少活动件匹配证据", missing=missing)

    matched = set(map(str, signals["matched_required_movables"])) & set(required)
    actual = set(map(str, signals["actual_movable_ids"]))
    spurious = set(map(str, signals["spurious_movable_ids"]))
    matched_counts_raw = signals.get("matched_required_movable_counts")
    if matched_counts_raw is None:
        # Backward-compatible path for hand-authored unit-test signals.
        matched_counts = {name: int(name in matched) for name in required}
    else:
        matched_counts = {str(k): int(v) for k, v in matched_counts_raw.items()}

    expected_count = 0
    matched_count = 0
    missing_required: list[str] = []
    for item in requirements:
        name = str(item.get("id") or item.get("category"))
        declared = item.get("count")
        wanted = int(declared) if declared is not None else 1
        found = matched_counts.get(name, 0)
        expected_count += wanted
        matched_count += min(found, wanted)
        if found < wanted:
            missing_required.extend(
                name if wanted == 1 else f"{name}[{index + 1}]"
                for index in range(found, wanted)
            )

    # When the Prompt leaves a plural count unspecified, all matched instances
    # of that category are legitimate.  They therefore do not depress P_move;
    # only unmatched movable categories are spurious.
    actual_evaluable_count = matched_count + len(spurious)
    recall = matched_count / expected_count
    precision = matched_count / actual_evaluable_count if actual_evaluable_count else 0.0
    f1 = C.harmonic_mean(precision, recall)
    penalty = math.exp(-len(spurious) / max(1, expected_count))
    value = f1 * penalty

    return C.build_result(
        METRIC, value, Coverage.FULL, consts,
        tools=["contract", "semantic-match", "joint-graph"],
        raw_measurements={
            "expected_count": expected_count,
            "actual_movable_count": len(actual),
            "actual_evaluable_count": actual_evaluable_count,
            "matched_count": matched_count,
            "spurious_count": len(spurious),
        },
        sub_scores={"precision": precision, "recall": recall, "F1": f1,
                    "spurious_penalty": penalty},
        evidence={"missing_required_movables": sorted(missing_required),
                  "spurious_movables": sorted(spurious)},
        failure_reason=None if value >= consts.tau_a1 else "活动件拆分、覆盖或多余活动件不符合契约",
        repair_hint="拆分缺失活动件、合并多余活动件，或修正 fixed/活动属性",
        provisional_params=["A1_SPURIOUS_PENALTY", "Q_TOOL", "Q_CONTRACT"],
    )
