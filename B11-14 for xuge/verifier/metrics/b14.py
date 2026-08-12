"""B14 多部件机构耦合。

S_sync  = exp(-RMSE_sync / 0.05)
S_ratio = exp(-|r_obs - r_exp| / 0.10)
S_loop  = exp(-(e_loop/D) / 0.005)
S_time  = 1 - t_violation / t_total
S_B14 = PI(适用项) * S_task

"适用项"是关键: 只有契约里声明了的耦合/比例/闭环才进乘积。
无预期耦合且无闭环 -> N/A (不补 0, 不进聚合分母)。

signals:
  sync_rmse_norm     同步误差, 已按各 delta_q 归一
  r_obs, r_exp       观测/预期传动比
  e_loop, d_bbox     闭环残差
  t_violation, t_total
  s_task             任务完成度 [0,1]
  solver_failed
"""

from __future__ import annotations

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "B14"
_NUMERIC_KEYS = ("sync_rmse_norm", "r_obs", "r_exp", "e_loop", "d_bbox",
                 "t_violation", "t_total", "s_task")


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    has_coupling = bool(contract.get("coupling"))
    has_loop = bool(contract.get("closed_loop"))
    if not has_coupling and not has_loop:
        return C.not_applicable(METRIC, consts, "契约中没有预期耦合或闭环")

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

    factors: dict[str, float] = {}
    raw: dict[str, float] = {}
    dropped: list[str] = []       # 契约声明了、却没有证据可算的项
    provisional = ["CONTACT_MODEL"]

    # --- 同步 ---
    if has_coupling:
        if signals.get("sync_rmse_norm") is not None:
            v = float(signals["sync_rmse_norm"])
            factors["S_sync"] = C.exp_decay(v, consts.b14_sync_scale)
            raw["sync_rmse_norm"] = v
        else:
            dropped.append("S_sync")

    # --- 传动比 ---
    if has_coupling:
        if signals.get("r_obs") is not None and signals.get("r_exp") is not None:
            r_obs, r_exp = float(signals["r_obs"]), float(signals["r_exp"])
            factors["S_ratio"] = C.exp_decay(abs(r_obs - r_exp), consts.b14_ratio_scale)
            raw.update({"r_obs": r_obs, "r_exp": r_exp, "ratio_error": abs(r_obs - r_exp)})
        else:
            dropped.append("S_ratio")

    # --- 闭环 ---
    # 这里必须用 is not None: d_bbox = 0.0 是假值, 用真值判断会短路掉下面的
    # 合法性检查, 让 S_loop 被静默丢弃 —— 实测那条路径下 score 变成 1.0。
    if has_loop:
        e_loop_raw, d_bbox_raw = signals.get("e_loop"), signals.get("d_bbox")
        if e_loop_raw is not None and d_bbox_raw is not None:
            e_loop, d_bbox = float(e_loop_raw), float(d_bbox_raw)
            if d_bbox <= 0:
                return C.tool_failure(METRIC, consts, "包围盒对角线无效", d_bbox=d_bbox)
            factors["S_loop"] = C.exp_decay(e_loop / d_bbox, consts.b14_loop_scale)
            raw.update({"e_loop": e_loop, "e_loop_norm": e_loop / d_bbox})
        else:
            dropped.append("S_loop")

    # --- 违规时长 --- 不由契约声明, 有证据才算, 缺了不记 dropped
    t_v_raw, t_t_raw = signals.get("t_violation"), signals.get("t_total")
    if t_v_raw is not None and t_t_raw is not None:
        t_v, t_t = float(t_v_raw), float(t_t_raw)
        if t_t <= 0:
            return C.tool_failure(METRIC, consts, "测试总时长无效", t_total=t_t)
        factors["S_time"] = C.clip01(1.0 - t_v / t_t)
        raw.update({"t_violation": t_v, "t_total": t_t})

    if not factors:
        return C.build_result(
            METRIC, None, Coverage.PARTIAL, consts,
            failure_reason="契约声明了耦合/闭环, 但没有任何可用的动态证据",
            evidence={"expected_coupling": has_coupling, "expected_loop": has_loop},
            provisional_params=provisional,
        )

    # --- 任务完成度 ---
    s_task = signals.get("s_task")
    s_task = C.clip01(float(s_task)) if s_task is not None else 1.0
    factors["S_task"] = s_task
    raw["s_task"] = s_task

    s = 1.0
    for v in factors.values():
        s *= v

    provenance = signals.get("physics_provenance", "default")
    has_dynamic = signals.get("t_total") is not None
    # 声明了却算不出的项等于被当成 1.0, 分数只是上界 -> partial。
    coverage = (Coverage.PARTIAL if dropped
                else C.coverage_for_physics(provenance, has_dynamic))

    return C.build_result(
        METRIC, s, coverage, consts,
        physics_provenance=provenance,
        tools=["coupling_contract", "simulator"],
        raw_measurements=raw,
        sub_scores=dict(factors),
        evidence=_evidence(signals, list(factors), dropped),
        failure_reason=_reason(factors, s, consts),
        repair_hint="增加耦合/约束、校准比例/相位或修正闭环几何",
        provisional_params=provisional,
        n_factors=len(factors),
    )


def _evidence(signals: dict, applied: list[str], dropped: list[str] | None = None) -> dict:
    ev: dict = {"applied_terms": applied}
    if dropped:
        ev["declared_but_unmeasured"] = dropped
    for k in ("phase_drift", "violation_frames", "coupling_pairs", "loop_name"):
        if signals.get(k) is not None:
            ev[k] = signals[k]
    return ev


_LABEL = {
    "S_sync": "耦合关节相位不同步",
    "S_ratio": "传动比偏离预期",
    "S_loop": "闭环约束残差过大",
    "S_time": "违规状态持续时间过长",
    "S_task": "任务未完成",
}


def _reason(factors: dict, s: float, consts) -> str | None:
    if s >= consts.tau_b14:
        return None
    worst = min(factors.items(), key=lambda kv: kv[1])
    return _LABEL.get(worst[0], worst[0])
