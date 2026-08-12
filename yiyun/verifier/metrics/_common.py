from __future__ import annotations

import functools
import math
from collections.abc import Callable, Iterable
from typing import Any

from ..consts import Consts
from ..types import Coverage, MetricResult, Prediction, ToolFailure


def clip01(value: float) -> float:
    if not math.isfinite(value):
        raise ToolFailure(f"收到非有限值 {value!r}")
    return max(0.0, min(1.0, value))


def exp_decay(value: float, scale: float) -> float:
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be a positive finite number")
    if not math.isfinite(value):
        raise ToolFailure(f"收到非有限值 {value!r}")
    return math.exp(-max(0.0, value) / scale)


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        raise ToolFailure(f"分母必须为正数，得到 {denominator!r}")
    return clip01(numerator / denominator)


def harmonic_mean(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def guards(metric: str) -> Callable:
    def decorate(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(signals: dict, contract: dict, consts: Consts) -> MetricResult:
            try:
                return fn(signals, contract, consts)
            except ToolFailure as exc:
                return tool_failure(metric, consts, f"输入/数值守卫触发: {exc}")
        return wrapped
    return decorate


def non_finite(signals: dict, keys: Iterable[str]) -> list[str]:
    bad: list[str] = []
    for key in keys:
        value = signals.get(key)
        if value is None:
            continue
        try:
            finite = math.isfinite(float(value))
        except (TypeError, ValueError):
            finite = False
        if not finite:
            bad.append(key)
    return bad


def build_result(
    metric: str,
    score: float | None,
    coverage: Coverage,
    consts: Consts,
    *,
    tools: Iterable[str] = (),
    raw_measurements: dict[str, Any] | None = None,
    sub_scores: dict[str, float] | None = None,
    evidence: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    repair_hint: str | None = None,
    provisional_params: Iterable[str] = (),
    extra_diagnostics: dict[str, Any] | None = None,
) -> MetricResult:
    tau = consts.tau(metric)
    if score is None:
        return MetricResult(
            metric=metric, score=None, threshold=tau, coverage=coverage,
            tools=list(tools), raw_measurements=raw_measurements or {},
            sub_scores=sub_scores or {}, evidence=evidence or {},
            failure_reason=failure_reason, repair_hint=repair_hint,
            provisional_params=sorted(set(provisional_params)),
            diagnostics=extra_diagnostics or {},
        )

    score = clip01(float(score))
    confidence = (
        consts.q_tool * consts.q_contract
        * min(1.0, abs(score - tau) / consts.confidence_band)
    )
    if confidence < consts.abstain_below:
        prediction = Prediction.ABSTAIN
    elif score < tau:
        prediction = Prediction.FAIL
    elif coverage is Coverage.PARTIAL:
        prediction = Prediction.ABSTAIN
    else:
        prediction = Prediction.PASS

    diagnostics = {"score_is_upper_bound": coverage is Coverage.PARTIAL}
    if extra_diagnostics:
        diagnostics.update(extra_diagnostics)
    return MetricResult(
        metric=metric, score=score, threshold=tau, coverage=coverage,
        prediction=prediction, confidence=confidence, tools=list(tools),
        raw_measurements=raw_measurements or {}, sub_scores=sub_scores or {},
        evidence=evidence or {}, failure_reason=failure_reason,
        repair_hint=repair_hint,
        provisional_params=sorted(set(provisional_params)),
        diagnostics=diagnostics,
    )


def not_applicable(metric: str, consts: Consts, reason: str) -> MetricResult:
    return build_result(metric, None, Coverage.NOT_APPLICABLE, consts,
                        evidence={"na_reason": reason})


def unsupported(metric: str, consts: Consts, reason: str) -> MetricResult:
    return build_result(metric, None, Coverage.UNSUPPORTED, consts,
                        evidence={"unsupported_reason": reason})


def tool_failure(metric: str, consts: Consts, reason: str, **evidence: Any) -> MetricResult:
    return build_result(metric, None, Coverage.TOOL_FAILURE, consts,
                        failure_reason=reason, evidence=evidence)


def contract_ids(items: list[dict], *, key: str = "id") -> list[str]:
    return [str(item[key]) for item in items if item.get(key)]
