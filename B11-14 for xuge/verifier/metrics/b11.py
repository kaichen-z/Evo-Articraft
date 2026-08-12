"""B11 可用关节运动范围。

S_B11 = R_geom * C * T * L
  C = clip(|q_end - q_start| / |q_target - q_start|, 0, 1)
  T = exp(-RMSE / (0.05 * dq))
  L = exp(-overshoot / (0.02 * dq))

signals:
  r_geom            扫掠中无阻塞可达的行程比例 [0,1]
  q_start/q_target/q_end
  delta_q           |q_max - q_min|
  rmse              跟踪 RMSE (与 q 同单位)
  overshoot         超调量 (与 q 同单位)
  first_blocked_step, blocking_pair  (证据, 可选)
  solver_failed     bool
contract:
  expected_range    没有预期活动范围 -> N/A
"""

from __future__ import annotations

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "B11"
_STATIC_KEYS = ("r_geom",)
_DYNAMIC_KEYS = ("q_start", "q_target", "q_end", "delta_q", "rmse", "overshoot")
_NUMERIC_KEYS = _STATIC_KEYS + _DYNAMIC_KEYS


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    if not contract.get("expected_range"):
        return C.not_applicable(METRIC, consts, "契约中没有预期活动范围")

    if signals.get("solver_failed"):
        return C.tool_failure(
            METRIC, consts, "仿真器求解失败",
            solver_status=signals.get("solver_status"),
        )

    bad = C.non_finite(signals, _NUMERIC_KEYS)
    if bad:
        return C.tool_failure(
            METRIC, consts, "信号含 NaN/inf, 疑似仿真发散", non_finite=bad
        )

    missing_static = C.require(signals, _STATIC_KEYS)
    if missing_static:
        return C.tool_failure(METRIC, consts, "缺少几何扫掠证据", missing=missing_static)

    r_geom = C.clip01(float(signals["r_geom"]))
    provenance = signals.get("physics_provenance", "default")
    missing_dyn = C.require(signals, _DYNAMIC_KEYS)
    has_dynamic = not missing_dyn

    provisional = ["QREF_PROFILE", "SWEEP_SUBDIV"]

    if not has_dynamic:
        # 仅几何 -> 部分覆盖。分数只保留 R_geom, 不用 1.0 补齐缺失因子。
        return C.build_result(
            METRIC, r_geom, Coverage.PARTIAL, consts,
            physics_provenance=provenance,
            tools=["sweep"],
            raw_measurements={"r_geom": r_geom},
            sub_scores={"R_geom": r_geom},
            evidence=_evidence(signals, missing=missing_dyn),
            failure_reason=None if r_geom >= consts.tau_b11 else "几何可达行程不足",
            repair_hint="清理运动走廊、调整合理范围或补充足够执行器",
            provisional_params=provisional,
            n_factors=1,
        )

    dq = float(signals["delta_q"])
    if dq <= 0:
        return C.tool_failure(METRIC, consts, "delta_q <= 0, 关节行程无效", delta_q=dq)

    q_start = float(signals["q_start"])
    q_target = float(signals["q_target"])
    q_end = float(signals["q_end"])
    target_travel = abs(q_target - q_start)
    if target_travel <= 0:
        return C.tool_failure(METRIC, consts, "目标行程为 0", q_start=q_start, q_target=q_target)

    completion = C.clip01(abs(q_end - q_start) / target_travel)
    rmse = float(signals["rmse"])
    overshoot = float(signals["overshoot"])
    tracking = C.exp_decay(rmse, consts.b11_rmse_scale * dq)
    limit = C.exp_decay(overshoot, consts.b11_overshoot_scale * dq)

    s = r_geom * completion * tracking * limit

    provisional += [
        "QREF_ACCEL_FRAC", "QREF_DURATION_S",
        "ACTUATOR_MODE", "ACTUATOR_MAX_FORCE", "ACTUATOR_KP", "ACTUATOR_KD",
    ]

    return C.build_result(
        METRIC, s,
        C.coverage_for_physics(provenance, True), consts,
        physics_provenance=provenance,
        tools=["sweep", "simulator"],
        raw_measurements={
            "r_geom": r_geom,
            "q_start": q_start, "q_target": q_target, "q_end": q_end,
            "delta_q": dq, "rmse": rmse, "overshoot": overshoot,
            "rmse_norm": rmse / dq, "overshoot_norm": overshoot / dq,
        },
        sub_scores={"R_geom": r_geom, "C": completion, "T": tracking, "L": limit},
        evidence=_evidence(signals),
        failure_reason=_reason(r_geom, completion, tracking, limit, consts),
        repair_hint="清理运动走廊、调整合理范围或补充足够执行器",
        provisional_params=provisional,
        n_factors=4,
    )


def _evidence(signals: dict, missing: list[str] | None = None) -> dict:
    ev = {}
    for k in ("first_blocked_step", "blocking_pair", "joint_name"):
        if signals.get(k) is not None:
            ev[k] = signals[k]
    if missing:
        ev["missing_signals"] = missing
    return ev


def _reason(r_geom, completion, tracking, limit, consts: Consts) -> str | None:
    if r_geom * completion * tracking * limit >= consts.tau_b11:
        return None
    worst = min(
        [("几何行程受阻", r_geom), ("动态完成度不足", completion),
         ("轨迹跟踪误差过大", tracking), ("超调量过大", limit)],
        key=lambda p: p[1],
    )
    return worst[0]
