"""打分辅助。所有 metrics 共用, 保持纯函数。"""

from __future__ import annotations

import functools
import math
from typing import Any, Callable, Iterable

from ..consts import PHYSICS_QUALITY, Consts
from ..types import Coverage, MetricResult, Prediction, ToolFailure


def exp_decay(value: float, scale: float) -> float:
    """exp(-value/scale), 对负 value 截断到 0 (不奖励"超好")。

    value 非有限时抛 ToolFailure。直接算的话:
      max(0.0, nan) == 0.0 -> exp(0) == 1.0  假通过
      exp(-inf/scale)      == 0.0            假失败
    两者都违反铁律 3 "工具故障 != 资产失败"。
    """
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be a positive finite number")
    if not math.isfinite(value):
        raise ToolFailure(f"exp_decay 收到非有限值 {value!r}")
    return math.exp(-max(0.0, value) / scale)


def clip01(x: float) -> float:
    """截断到 [0,1]。非有限值抛 ToolFailure —— clip01(nan) 会算出 1.0。"""
    if not math.isfinite(x):
        raise ToolFailure(f"clip01 收到非有限值 {x!r}")
    return max(0.0, min(1.0, x))


def non_finite(signals: dict, keys: Iterable[str]) -> list[str]:
    """返回存在但不是有限实数的键 (NaN / ±inf / 非数值)。

    仿真器发散往往不设 solver_failed, 而是直接吐 NaN/inf。铁律 3 点名
    "NaN / 发散" 必须走 tool-failure, 所以这类值要在进公式前拦下。
    缺失 (None) 不算, 由 require() 分开处理 —— 缺证据是覆盖不全, 不是故障。
    """
    bad = []
    for k in keys:
        v = signals.get(k)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            bad.append(k)
            continue
        if not math.isfinite(f):
            bad.append(k)
    return bad


def guards(metric: str) -> Callable:
    """装饰 score(): 把 ToolFailure 转成 tool-failure 结果, 绝不返回 0.0。

    每个 metric 已经用 non_finite() 显式拦了自己的数值信号; 这层是兜底 ——
    万一某个信号没被那份键清单覆盖, exp_decay/clip01 会抛 ToolFailure,
    在这里变成 coverage="tool-failure", 而不是静默算出 1.0 或 0.0。
    """
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(signals: dict, contract: dict, consts: Consts) -> MetricResult:
            try:
                return fn(signals, contract, consts)
            except ToolFailure as e:
                return tool_failure(metric, consts, f"数值守卫触发: {e}")
        return wrapper
    return deco


def equivalent_factor_threshold(tau: float, n_factors: int) -> float:
    """n 个乘性因子下, 每个因子平均需要达到多少才能让乘积过 tau。

    这是把"τ 统一 0.70"的实际严格度暴露出来的诊断量:
      B11/B13 (4 因子) -> 0.915
      B12     (8 因子) -> 0.956
    不影响分数, 只写进 diagnostics 让问题可见。
    """
    if n_factors <= 0:
        return tau
    return tau ** (1.0 / n_factors)


def physics_quality(provenance: str) -> float:
    return PHYSICS_QUALITY.get(provenance, PHYSICS_QUALITY["default"])


def coverage_for_physics(provenance: str, has_dynamic_evidence: bool) -> Coverage:
    """PRO-12 §04 的覆盖程度判定。"""
    if not has_dynamic_evidence:
        return Coverage.PARTIAL
    if provenance == "asset":
        return Coverage.FULL
    return Coverage.ESTIMATED_PHYSICS


def build_result(
    metric: str,
    score: float | None,
    coverage: Coverage,
    consts: Consts,
    *,
    physics_provenance: str = "default",
    tools: Iterable[str] = (),
    raw_measurements: dict[str, Any] | None = None,
    sub_scores: dict[str, float] | None = None,
    evidence: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    repair_hint: str | None = None,
    provisional_params: Iterable[str] = (),
    n_factors: int | None = None,
    extra_diagnostics: dict[str, Any] | None = None,
) -> MetricResult:
    """统一组装 MetricResult, 计算 prediction 与 confidence。

    confidence = q_tool * q_contract * q_physics * min(1, |score-tau|/band)
    (PRO-12 §04)

    注意: 规范 §09 的 JSON 示例里 A3 给出 score=0.675, tau=0.70, coverage=full,
    confidence=0.88; 但按上式应为 min(1, 0.025/0.20) = 0.125。示例与公式不一致,
    已列入待确认问题。本实现按公式算, 并把示例值差异记在 diagnostics 里。
    """
    tau = consts.tau(metric)

    if score is None:
        return MetricResult(
            metric=metric,
            score=None,
            threshold=tau,
            coverage=coverage,
            prediction=Prediction.NONE,
            confidence=None,
            tools=list(tools),
            raw_measurements=raw_measurements or {},
            sub_scores=sub_scores or {},
            evidence=evidence or {},
            failure_reason=failure_reason,
            repair_hint=repair_hint,
            provisional_params=sorted(set(provisional_params)),
        )

    q_phys = physics_quality(physics_provenance)
    band = clip01(abs(score - tau) / consts.confidence_band)
    confidence = consts.q_tool * consts.q_contract * q_phys * band

    # 部分覆盖下缺失的因子实际被当成 1.0, 所以分数只是完整分数的上界:
    #   上界 <  tau -> 完整分数必然 < tau, FAIL 可证
    #   上界 >= tau -> 完整分数未知, 不能凭不完整证据判 PASS
    upper_bound_only = coverage is Coverage.PARTIAL

    if confidence < consts.abstain_below:
        prediction = Prediction.ABSTAIN
    elif score >= tau:
        prediction = Prediction.ABSTAIN if upper_bound_only else Prediction.PASS
    else:
        prediction = Prediction.FAIL

    diagnostics: dict[str, Any] = {"physics_quality": q_phys}
    if upper_bound_only:
        diagnostics["score_is_upper_bound"] = True
    if n_factors:
        diagnostics["n_multiplicative_factors"] = n_factors
        diagnostics["equivalent_factor_threshold"] = round(
            equivalent_factor_threshold(tau, n_factors), 4
        )
    if extra_diagnostics:
        diagnostics.update(extra_diagnostics)

    return MetricResult(
        metric=metric,
        score=score,
        threshold=tau,
        coverage=coverage,
        prediction=prediction,
        confidence=confidence,
        tools=list(tools),
        raw_measurements=raw_measurements or {},
        sub_scores=sub_scores or {},
        evidence=evidence or {},
        failure_reason=failure_reason,
        repair_hint=repair_hint,
        provisional_params=sorted(set(provisional_params)),
        diagnostics=diagnostics,
    )


def not_applicable(metric: str, consts: Consts, reason: str) -> MetricResult:
    return build_result(
        metric,
        None,
        Coverage.NOT_APPLICABLE,
        consts,
        failure_reason=None,
        evidence={"na_reason": reason},
    )


def tool_failure(metric: str, consts: Consts, reason: str, **kw) -> MetricResult:
    """工具故障绝不返回 0.0。"""
    return build_result(
        metric,
        None,
        Coverage.TOOL_FAILURE,
        consts,
        failure_reason=reason,
        evidence=kw,
    )


def require(signals: dict, keys: Iterable[str]) -> list[str]:
    """返回缺失的键名。调用方据此决定 partial 还是继续。"""
    return [k for k in keys if signals.get(k) is None]
