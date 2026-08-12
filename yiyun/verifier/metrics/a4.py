"""A4 形状、尺寸与比例真实感。

VLM 信号必须来自与人工 A4 标签校准过的外部模型；评分头本身不调用 VLM。
缺失某项证据时将该项按 1.0 形成“最好情况下上界”，coverage=partial，不能 PASS。
"""

from __future__ import annotations

import math

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "A4"


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    scale_contract = contract.get("category_scale") or {}
    claims = contract.get("appearance_claims") or []
    if not claims and not scale_contract:
        return C.not_applicable(METRIC, consts, "没有明确外观要求或可用类别尺度先验")

    supplied: dict[str, float] = {}
    if signals.get("vlm_realism_probability") is not None:
        supplied["p_real"] = C.clip01(float(signals["vlm_realism_probability"]))
    if signals.get("cross_view_consistency") is not None:
        supplied["C_view"] = C.clip01(float(signals["cross_view_consistency"]))

    scale_score = None
    actual_scale = signals.get("actual_scale_m")
    median_scale = scale_contract.get("median_m")
    if actual_scale is not None and median_scale is not None:
        actual_scale, median_scale = float(actual_scale), float(median_scale)
        if actual_scale <= 0 or median_scale <= 0:
            return C.tool_failure(METRIC, consts, "尺度必须为正数",
                                  actual_scale_m=actual_scale, median_scale_m=median_scale)
        scale_score = math.exp(-abs(math.log(actual_scale / median_scale)) / math.log(2.0))
        supplied["S_scale"] = scale_score

    if not supplied:
        return C.unsupported(METRIC, consts, "缺少校准 VLM 输出和类别尺度测量")

    weights = {"p_real": consts.a4_realism_weight,
               "C_view": consts.a4_view_weight}
    # 类别尺度是 HTML 中的可选输入；只有 Contract 真正提供真实产品尺度
    # 先验时，才把 S_scale 加入分母和评分。
    if scale_contract:
        weights["S_scale"] = consts.a4_scale_weight
    available_weight = sum(weights[name] for name in supplied if name in weights)
    value = sum(weights[name] * supplied[name] for name in supplied if name in weights) / available_weight
    full = all(name in supplied for name in weights) and bool(signals.get("vlm_calibrated"))
    coverage = Coverage.FULL if full else Coverage.PARTIAL
    missing = sorted(set(weights) - set(supplied))

    return C.build_result(
        METRIC, value, coverage, consts,
        tools=["renderer", "calibrated-vlm", "scale-prior"],
        raw_measurements={"actual_scale_m": actual_scale, "median_scale_m": median_scale},
        sub_scores=supplied,
        evidence={"missing_evidence": missing,
                  "vlm_calibrated": bool(signals.get("vlm_calibrated")),
                  "vlm_evidence": signals.get("a4_vlm_evidence", []),
                  "low_scoring_views": signals.get("low_scoring_views", [])},
        failure_reason=None if value >= consts.tau_a4 else "形状、比例或尺度证据不符合要求",
        repair_hint="调整异常形状、尺度或比例；低置信结果交由人工复核",
        provisional_params=["A4_VLM_WEIGHTS", "A4_SCALE_PRIOR", "Q_TOOL", "Q_CONTRACT"],
    )
