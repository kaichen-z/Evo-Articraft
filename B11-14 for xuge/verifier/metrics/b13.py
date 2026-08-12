"""B13 运动干涉与动态阻塞。

S_sweep   = 0.5*exp(-P_j/(0.002*D)) + 0.5*R_j
S_contact = exp(-I_unexpected/(0.10*mgT))
S_stall   = 1 - t_stall/t_act
S_dyn     = exp(-p_dyn/(0.002*D))
S_B13 = S_sweep * S_contact * S_stall * S_dyn

signals:
  penetration_max (P_j), d_bbox (D), r_j
  impulse_unexpected, total_mass, t_act
  t_stall, p_dyn
  solver_failed
"""

from __future__ import annotations

from ..consts import Consts, GRAVITY
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "B13"
_SWEEP_KEYS = ("penetration_max", "d_bbox", "r_j")
_DYNAMIC_KEYS = ("impulse_unexpected", "total_mass", "t_stall", "p_dyn")
_NUMERIC_KEYS = _SWEEP_KEYS + _DYNAMIC_KEYS + ("t_act",)


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    if not contract.get("expected_movables"):
        return C.not_applicable(METRIC, consts, "契约中没有预期活动件")

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

    missing_sweep = C.require(signals, _SWEEP_KEYS)
    if missing_sweep:
        return C.tool_failure(METRIC, consts, "缺少扫掠碰撞证据", missing=missing_sweep)

    d_bbox = float(signals["d_bbox"])
    if d_bbox <= 0:
        return C.tool_failure(METRIC, consts, "包围盒对角线无效", d_bbox=d_bbox)

    p_j = float(signals["penetration_max"])
    r_j = C.clip01(float(signals["r_j"]))
    f_pen = C.exp_decay(p_j, consts.b13_penetration_scale * d_bbox)
    s_sweep = (consts.b13_sweep_penetration_weight * f_pen
               + consts.b13_sweep_reach_weight * r_j)

    provenance = signals.get("physics_provenance", "default")
    missing_dyn = C.require(signals, _DYNAMIC_KEYS)
    provisional = ["R_J_DEF", "SWEEP_SUBDIV", "CONTACT_MODEL"]

    raw = {
        "penetration_max": p_j, "d_bbox": d_bbox,
        "penetration_norm": p_j / d_bbox, "r_j": r_j,
    }
    subs = {"f_penetration": f_pen, "R_j": r_j, "S_sweep": s_sweep}

    if missing_dyn:
        return C.build_result(
            METRIC, s_sweep, Coverage.PARTIAL, consts,
            physics_provenance=provenance,
            tools=["sweep"],
            raw_measurements=raw,
            sub_scores=subs,
            evidence=_evidence(signals, missing=missing_dyn),
            failure_reason=None if s_sweep >= consts.tau_b13 else "扫掠中检出穿透或行程受阻",
            repair_hint="挖腔/增加净空、移动轴线、缩短到仍满足功能的有效范围",
            provisional_params=provisional,
            n_factors=1,
        )

    total_mass = float(signals["total_mass"])
    # 归一化基准只认 consts (铁律 2)。ACTUATE_S 是 §06 冻结量, 让 signals
    # 覆盖它等于把 S_stall 和 mgT 的分母交给信号生产方 —— 实测把 t_act
    # 从 3.0 改成 100 能让 B13 从 0.0117 变 0.0816。
    t_act = float(consts.t_act_definition)
    if total_mass <= 0 or t_act <= 0:
        return C.tool_failure(
            METRIC, consts, "冲量归一化基准无效", total_mass=total_mass, t_act=t_act
        )

    # 仿真器报了不一样的驱动段时长 = 没按 §06 协议跑, 结果不可比。
    # 不静默采用, 也不静默丢弃, 写进 diagnostics 让问题可见。
    reported_t_act = signals.get("t_act")
    protocol_deviation = (
        None if reported_t_act is None or abs(float(reported_t_act) - t_act) < 1e-9
        else {"t_act_reported": float(reported_t_act), "t_act_used": t_act}
    )

    mgt = total_mass * GRAVITY * t_act
    impulse = float(signals["impulse_unexpected"])
    t_stall = float(signals["t_stall"])
    p_dyn = float(signals["p_dyn"])

    s_contact = C.exp_decay(impulse, consts.b13_impulse_scale * mgt)
    s_stall = C.clip01(1.0 - t_stall / t_act)
    s_dyn = C.exp_decay(p_dyn, consts.b13_dyn_penetration_scale * d_bbox)

    s = s_sweep * s_contact * s_stall * s_dyn

    provisional.append("T_ACT_DEF")
    raw.update({
        "impulse_unexpected": impulse, "total_mass": total_mass,
        "t_act": t_act, "mgT": mgt, "impulse_norm": impulse / mgt,
        "t_stall": t_stall, "p_dyn": p_dyn, "p_dyn_norm": p_dyn / d_bbox,
    })
    subs.update({"S_contact": s_contact, "S_stall": s_stall, "S_dyn": s_dyn})

    return C.build_result(
        METRIC, s,
        C.coverage_for_physics(provenance, True), consts,
        physics_provenance=provenance,
        tools=["sweep", "simulator"],
        raw_measurements=raw,
        sub_scores=subs,
        evidence=_evidence(signals),
        failure_reason=_reason(s_sweep, s_contact, s_stall, s_dyn, consts),
        repair_hint="挖腔/增加净空、移动轴线、缩短到仍满足功能的有效范围",
        provisional_params=provisional,
        n_factors=4,
        extra_diagnostics=(
            {"protocol_deviation": protocol_deviation} if protocol_deviation else None
        ),
    )


def _evidence(signals: dict, missing: list[str] | None = None) -> dict:
    ev = {}
    for k in ("link_pair", "first_blocked_step", "stall_interval",
              "unexpected_contacts", "joint_name"):
        if signals.get(k) is not None:
            ev[k] = signals[k]
    if missing:
        ev["missing_signals"] = missing
    return ev


def _reason(s_sweep, s_contact, s_stall, s_dyn, consts) -> str | None:
    if s_sweep * s_contact * s_stall * s_dyn >= consts.tau_b13:
        return None
    worst = min(
        [("扫掠穿透或行程受阻", s_sweep),
         ("非预期接触冲量过大", s_contact),
         ("驱动过程中发生停滞", s_stall),
         ("动态穿透超限", s_dyn)],
        key=lambda p: p[1],
    )
    return worst[0]
