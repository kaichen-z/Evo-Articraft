"""把扫掠产物与动态试验产物合成 metrics 吃的 signals dict。

metrics 用 require() 各取所需, 所以合成一份共用 dict 就够 —— 两边同名的键
(d_bbox / joint_name) 指的是同一个量, 由扫掠侧为准。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..consts import ACTUATE_S, Consts

if TYPE_CHECKING:                       # primitives.sweep 依赖 sim.loader, 直接
    from ..primitives.sweep import SweepResult   # import 会成环 —— 只要类型注解


def merge(sweep: "SweepResult", dynamic: dict[str, Any] | None,
          consts: Consts, *, s_payload: float | None = None) -> dict[str, Any]:
    """扫掠 + 动态 -> 一份 signals。dynamic 为 None 即"只有几何证据"。"""
    out: dict[str, Any] = dict(sweep.as_signals())
    if dynamic:
        merged = dict(dynamic)
        # 扫掠侧的归一化基准更可靠: 它是在无重力形变的姿态上量的
        merged.pop("d_bbox", None)
        merged.pop("joint_name", None)
        out.update(merged)
        # b13 会拿它和冻结的 ACTUATE_S 比对, 不一致就记 protocol_deviation
        out["t_act"] = ACTUATE_S
    if s_payload is not None:
        out["s_payload"] = s_payload
    if sweep.truncated:
        out["distmax_truncated"] = sweep.truncated
    return out


def provisional_from_signals(signals: dict[str, Any]) -> list[str]:
    """这份 signals 依赖了哪些未定参数 —— 供报告层合并进 provisional_params。"""
    out = ["MJ_SOLREF", "MJ_SOLIMP", "MJ_GEOM_DISTMAX",
           "SWEEP_BLOCK_THRESHOLD", "S_CLEARANCE_DEF"]
    if signals.get("p_dyn") is not None:
        out += ["MJ_ACTUATOR_GAINS", "MJ_DEFAULT_DAMPING", "STALL_DEF",
                "E_CONSTRAINT_DEF", "D_GRAVITY_DEF"]
    if signals.get("physics_provenance") == "inferred":
        out.append("MJ_DEFAULT_DENSITY")
    return sorted(set(out))
