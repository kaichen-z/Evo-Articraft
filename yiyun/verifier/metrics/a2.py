"""A2 零件数量与类型。"""

from __future__ import annotations

from collections import Counter

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "A2"


def _required_counts(items: list[dict]) -> Counter:
    counts: Counter = Counter()
    for item in items:
        category = item.get("category") or item.get("id")
        if category and not ("count" in item and item["count"] is None):
            counts[str(category)] += int(item.get("count", 1))
    return counts


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    requirements = contract.get("required_parts") or []
    required = _required_counts(requirements)
    required_categories = {
        str(item.get("category") or item.get("id"))
        for item in requirements if item.get("category") or item.get("id")
    }
    if not required_categories:
        return C.not_applicable(METRIC, consts, "Prompt 未明确要求部件类别或数量")
    if signals.get("part_match_failed"):
        return C.tool_failure(METRIC, consts, "部件名称解析不完整，不能将缺失解释为资产错误")
    actual_raw = signals.get("actual_part_counts")
    type_score_raw = signals.get("type_match_score")
    if actual_raw is None or type_score_raw is None:
        return C.tool_failure(METRIC, consts, "缺少部件数量或类型匹配证据",
                              missing=[k for k, v in {
                                  "actual_part_counts": actual_raw,
                                  "type_match_score": type_score_raw,
                              }.items() if v is None])

    actual = Counter({str(k): int(v) for k, v in actual_raw.items()})
    # 只给 Prompt 明确要求的类别计分。未要求的附加部件不是自动错误；
    # 它们保留在 evidence，只有同一必需类别数量过多时才扣分。
    categories = set(required)
    denominator = sum(max(required[c], actual[c]) for c in categories)
    count_error = sum(abs(required[c] - actual[c]) for c in categories)
    count_score = 1.0 - count_error / denominator if denominator else None
    type_score = C.clip01(float(type_score_raw))
    if count_score is None:
        # Exact quantity is not applicable when the Prompt only states that a
        # category exists.  Do not silently convert that into "exactly one".
        value = type_score
    else:
        value = consts.a2_count_weight * count_score + consts.a2_type_weight * type_score
    differences = {
        c: {"required": required[c], "actual": actual[c]}
        for c in sorted(categories) if required[c] != actual[c]
    }

    sub_scores = {"S_type": type_score}
    if count_score is not None:
        sub_scores["S_count"] = count_score
    return C.build_result(
        METRIC, value, Coverage.FULL, consts,
        tools=["contract", "semantic-match", "part-count"],
        raw_measurements={"required_counts": dict(required), "actual_counts": dict(actual)},
        sub_scores=sub_scores,
        evidence={"count_differences": differences,
                  "count_unspecified_categories": sorted(required_categories - categories),
                  "unmatched_names": signals.get("unmatched_part_names", []),
                  "unrequested_categories": sorted(set(actual) - set(required))},
        failure_reason=None if value >= consts.tau_a2 else "部件数量或类型与 Prompt 明确要求不一致",
        repair_hint="新增、删除或重新匹配指定类别的部件",
        provisional_params=["A2_COUNT_TYPE_WEIGHTS", "Q_TOOL", "Q_CONTRACT"],
    )
