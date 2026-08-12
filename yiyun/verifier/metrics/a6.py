"""A6 初始状态完整性。

S_A6 = exp(-(p0/D)/0.002) * exp(-r_det/0.05)
       * exp(-(g_float/D)/0.01)

上游必须使用真实 mesh，并先排除经契约证明的合法 overlap/contact。
"""

from __future__ import annotations

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "A6"
NUMERIC = ("object_diagonal_m", "unexpected_penetration_m",
           "detached_volume_ratio", "unsupported_gap_m")


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    if signals.get("geometry_query_failed"):
        return C.tool_failure(METRIC, consts, "初始姿态几何查询失败")
    bad = C.non_finite(signals, NUMERIC)
    if bad:
        return C.tool_failure(METRIC, consts, "初始状态信号含非有限值", non_finite=bad)
    missing = [key for key in NUMERIC if signals.get(key) is None]
    if missing:
        return C.tool_failure(METRIC, consts, "缺少初始状态几何证据", missing=missing)

    diagonal = float(signals["object_diagonal_m"])
    if diagonal <= 0:
        return C.tool_failure(METRIC, consts, "物体尺度 D 必须为正", object_diagonal_m=diagonal)
    penetration = max(0.0, float(signals["unexpected_penetration_m"]))
    detached_ratio = C.clip01(float(signals["detached_volume_ratio"]))
    floating_gap = max(0.0, float(signals["unsupported_gap_m"]))
    p_norm = penetration / diagonal
    gap_norm = floating_gap / diagonal
    s_pen = C.exp_decay(p_norm, consts.a6_penetration_scale)
    s_det = C.exp_decay(detached_ratio, consts.a6_detached_ratio_scale)
    s_float = C.exp_decay(gap_norm, consts.a6_floating_gap_scale)
    value = s_pen * s_det * s_float

    notes = signals.get("a6_measurement_notes") or {}
    coverage = (
        Coverage.PARTIAL
        if notes.get("detached_ratio_is_part_count_proxy")
        or notes.get("unsupported_gap_available") is False
        else Coverage.FULL
    )
    return C.build_result(
        METRIC, value, coverage, consts,
        tools=["exact-mesh-collision", "connected-components", "support-query"],
        raw_measurements={
            "object_diagonal_m": diagonal,
            "unexpected_penetration_m": penetration,
            "penetration_over_D": p_norm,
            "detached_volume_ratio": detached_ratio,
            "unsupported_gap_m": floating_gap,
            "unsupported_gap_over_D": gap_norm,
        },
        sub_scores={"S_penetration": s_pen, "S_detached": s_det, "S_floating": s_float},
        evidence={
            "penetrating_pairs": signals.get("penetrating_pairs", []),
            "detached_parts": signals.get("detached_parts", []),
            "floating_parts": signals.get("floating_parts", []),
            "allowed_overlap_ids": signals.get("allowed_overlap_ids", []),
            "measurement_notes": notes,
        },
        failure_reason=_reason(s_pen, s_det, s_float, value, consts),
        repair_hint="消除非预期穿透、重新连接脱离部件，或让悬空部件落到预期支撑面",
        provisional_params=["A6_DECAY_SCALES", "Q_TOOL"],
    )


def _reason(s_pen: float, s_det: float, s_float: float,
            value: float, consts: Consts) -> str | None:
    if value >= consts.tau_a6:
        return None
    return min(
        (("初始姿态存在非预期实体穿透", s_pen),
         ("存在脱离的几何部件", s_det),
         ("存在缺乏支撑的悬空部件", s_float)),
        key=lambda pair: pair[1],
    )[0]
