"""按 §06 协议跑一次动态试验, 产出 signals。

两点实现选择:

1. **不注入 <actuator>**。ArtiCraft 的 URDF 没有执行器 (nu=0), 而 MjModel 编译
   后结构不可变。这里每步直接往 qfrc_applied 写 PD 力并按 ACTUATOR_MAX_FORCE
   限幅 —— 与 position 执行器等价, 且不用改写资产 XML。

2. **三次试验只扰动"推断/默认"的参数** (§06 原文)。质量只在 provenance
   为 inferred 时缩放 (asset 级的质量是资产写的, 扰动它等于篡改资产);
   摩擦与关节阻尼这批资产从不声明, 一律视为默认值并缩放。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from ..consts import DT, TRIALS, Consts
from ..types import ToolFailure
from . import protocol
from .loader import (
    LoadedModel,
    body_name,
    geom_name,
    joint_name,
    load_urdf,
    movable_joints,
)


def _whitelist(contract: dict | None) -> set[frozenset[str]]:
    pairs = (contract or {}).get("expected_contacts") or []
    return {frozenset(str(x) for x in pair) for pair in pairs if len(pair) == 2}


def _pair_labels(m: Any, g1: int, g2: int) -> set[frozenset[str]]:
    """一对接触几何的所有可能命名组合。

    契约的 expected_contacts 用连杆名, 而 MuJoCo 会把焊到世界的 body 融进
    world —— 只按 body 名匹配的话, ["drawer","rail"] 永远匹配不上
    ("drawer","world")。所以 geom 名和 body 名都参与匹配。
    """
    a = {geom_name(m, int(g1)), body_name(m, int(m.geom_bodyid[g1]))}
    b = {geom_name(m, int(g2)), body_name(m, int(m.geom_bodyid[g2]))}
    return {frozenset((x, y)) for x in a for y in b}


def _target_range(loaded: LoadedModel, joint_id: int, contract: dict | None):
    """(q_start, q_target, delta_q)。契约声明了预期行程就用契约的。"""
    m = loaded.model
    lo, hi = (float(x) for x in m.jnt_range[joint_id])
    name = joint_name(m, joint_id)
    declared = ((contract or {}).get("expected_range") or {}).get(name)
    if declared and declared.get("min") is not None and declared.get("max") is not None:
        lo_c, hi_c = float(declared["min"]), float(declared["max"])
        return lo_c, hi_c, abs(hi_c - lo_c)
    return lo, hi, abs(hi - lo)


def _perturb(loaded: LoadedModel, scale: float, consts: Consts) -> dict[str, Any]:
    """按试验缩放推断/默认参数。返回这次实际动了什么, 供 evidence 追溯。"""
    m = loaded.model
    touched: dict[str, Any] = {"scale": scale}

    if loaded.provenance != "asset":
        m.body_mass[:] = m.body_mass * scale
        m.body_inertia[:] = m.body_inertia * scale
        touched["mass"] = True
    else:
        touched["mass"] = False        # 资产自带惯量, 不篡改

    m.geom_friction[:] = m.geom_friction * scale
    touched["friction"] = True

    if float(np.max(np.abs(m.dof_damping))) <= 0.0:
        m.dof_damping[:] = consts.mj_default_joint_damping * scale
        touched["damping"] = "default"
    else:
        touched["damping"] = "asset"   # 资产声明了 <dynamics damping>, 不动
    return touched


def run_trial(urdf_path: str | Path, joint_id: int, consts: Consts,
              scale: float = 1.0, contract: dict | None = None) -> dict[str, Any]:
    """跑一次完整协议, 返回该次试验的 signals dict。"""
    loaded = load_urdf(urdf_path, consts)
    m, d = loaded.model, loaded.data
    if joint_id >= m.njnt:
        raise ToolFailure(f"关节 id {joint_id} 超出范围 (njnt={m.njnt})")

    touched = _perturb(loaded, scale, consts)
    ph = protocol.phases(DT)
    qadr = int(m.jnt_qposadr[joint_id])
    dadr = int(m.jnt_dofadr[joint_id])

    q_start, q_target, delta_q = _target_range(loaded, joint_id, contract)
    d.qpos[qadr] = q_start
    mujoco.mj_forward(m, d)

    kp, kv, m_jj = _pd_gains(m, d, dadr, consts)
    touched.update({"joint_inertia": m_jj, "kp": kp, "kv": kv})

    # 非目标关节: 放任自由的话, 多关节资产会在重力下整体崩塌, 测到的是自由
    # 摆动而不是目标关节 —— 42 键的键盘实测 rmse 2.64 rad。默认全部保持。
    held: list[tuple[int, int, float, float, float]] = []
    if consts.other_joints_policy == "hold":
        for jj in movable_joints(m):
            if jj == joint_id:
                continue
            h_q, h_d = int(m.jnt_qposadr[jj]), int(m.jnt_dofadr[jj])
            try:
                hkp, hkv, _ = _pd_gains(m, d, h_d, consts)
            except ToolFailure:
                continue
            held.append((h_q, h_d, float(d.qpos[h_q]), hkp, hkv))
    elif consts.other_joints_policy != "free":
        raise ValueError(f"未知的 other_joints_policy: {consts.other_joints_policy!r}")
    touched["held_joints"] = len(held)

    body_pos0 = d.xpos.copy()
    body_quat0 = d.xquat.copy()
    white = _whitelist(contract)
    baseline_pairs: set[frozenset[str]] = set()
    direction = 1.0 if q_target >= q_start else -1.0
    nominal_speed = delta_q / max(consts.qref_duration_s, DT)
    stall_v = consts.stall_velocity_frac * nominal_speed

    err_sq: list[float] = []
    overshoot = 0.0
    impulse_unexpected = 0.0
    t_stall = 0.0
    p_dyn = 0.0
    settle_pen = 0.0
    d_gravity = 0.0
    theta_drift = 0.0
    e_constraint = 0.0
    stall_from: int | None = None
    stall_interval: list[float] | None = None
    force6 = np.zeros(6, dtype=np.float64)

    for step in range(ph.total):
        phase = ph.phase_at(step)
        target = protocol.q_ref(step, ph, q_start, q_target, consts, DT)

        if phase == "settle":
            d.qfrc_applied[dadr] = 0.0
        else:
            err = target - float(d.qpos[qadr])
            f = kp * err - kv * float(d.qvel[dadr])
            d.qfrc_applied[dadr] = float(np.clip(f, -consts.actuator_max_force,
                                                 consts.actuator_max_force))

        # 非目标关节全程保持初始位姿 (含静置段, 否则它们先塌了)
        for h_q, h_d, q_hold, hkp, hkv in held:
            fh = hkp * (q_hold - float(d.qpos[h_q])) - hkv * float(d.qvel[h_d])
            d.qfrc_applied[h_d] = float(np.clip(fh, -consts.actuator_max_force,
                                                consts.actuator_max_force))

        mujoco.mj_step(m, d)

        if not np.all(np.isfinite(d.qpos)) or not np.all(np.isfinite(d.qvel)):
            raise ToolFailure(f"仿真发散: step={step} phase={phase}")

        pen = max((-float(d.contact[i].dist) for i in range(d.ncon)), default=0.0)
        pen = max(0.0, pen)
        if phase == "settle":
            settle_pen = max(settle_pen, pen)
            d_gravity = max(d_gravity, float(np.linalg.norm(d.xpos - body_pos0, axis=1).max()))
            theta_drift = max(theta_drift, _max_quat_angle_deg(body_quat0, d.xquat))
        else:
            p_dyn = max(p_dyn, pen)

        if d.nefc:
            e_constraint = max(e_constraint, float(np.abs(d.efc_pos[:d.nefc]).max()))

        # 静置段的接触是资产自重支撑, 属预期基线; 冲量只在驱动+保持段累计。
        if phase == "settle":
            if consts.baseline_contacts_expected and step == ph.settle - 1:
                for i in range(d.ncon):
                    baseline_pairs |= _pair_labels(m, d.contact[i].geom1,
                                                   d.contact[i].geom2)
        else:
            for i in range(d.ncon):
                c = d.contact[i]
                labels = _pair_labels(m, c.geom1, c.geom2)
                if labels & white or labels & baseline_pairs:
                    continue
                mujoco.mj_contactForce(m, d, i, force6)
                impulse_unexpected += abs(float(force6[0])) * DT

        if phase == "actuate":
            moving_commanded = abs(target - q_start) > 1e-9 and abs(target - q_target) > 1e-9
            if moving_commanded and abs(float(d.qvel[dadr])) < stall_v:
                t_stall += DT
                if stall_from is None:
                    stall_from = step
            elif stall_from is not None:
                stall_interval = stall_interval or [
                    (stall_from - ph.settle) * DT, (step - ph.settle) * DT]
                stall_from = None
            err_sq.append((float(d.qpos[qadr]) - target) ** 2)

        travel_beyond = direction * (float(d.qpos[qadr]) - q_target)
        overshoot = max(overshoot, travel_beyond)

    if stall_from is not None:
        stall_interval = stall_interval or [
            (stall_from - ph.settle) * DT, protocol.ACTUATE_S]

    return {
        "q_start": q_start,
        "q_target": q_target,
        "q_end": float(d.qpos[qadr]),
        "delta_q": delta_q,
        "rmse": float(np.sqrt(np.mean(err_sq))) if err_sq else 0.0,
        "overshoot": float(max(0.0, overshoot)),
        "d_gravity": float(d_gravity),
        "e_constraint": float(e_constraint),
        "theta_drift_deg": float(theta_drift),
        "impulse_unexpected": float(impulse_unexpected),
        "total_mass": loaded.total_mass,
        "t_stall": float(t_stall),
        "p_dyn": float(p_dyn),
        "d_bbox": loaded.d_bbox,
        "physics_provenance": loaded.provenance,
        "joint_name": joint_name(m, joint_id),
        "stall_interval": stall_interval,
        "trial": touched,
        "settle_penetration": float(settle_pen),
    }


def _full_mass_matrix(m: Any, d: Any) -> np.ndarray:
    """稠密质量矩阵。跨 MuJoCo 版本: 3.11 起 d.qM 改叫 d.M, mj_fullM 也换了签名。"""
    dense = np.zeros((m.nv, m.nv), dtype=np.float64)
    try:
        mujoco.mj_fullM(m, d, dense)              # >= 3.11
    except TypeError:
        mujoco.mj_fullM(m, dense, getattr(d, "qM", None))   # 旧签名
    return dense


def _pd_gains(m: Any, d: Any, dof: int, consts: Consts) -> tuple[float, float, float]:
    """按关节有效惯量定 PD 增益, 使闭环带宽与阻尼比在所有资产上一致。

        kp = M_jj * omega^2      kv = 2 * zeta * omega * M_jj

    M_jj 取质量矩阵对角元 —— 一个 0.043kg 的琴键和一个 21kg 的靠背拿到的是
    同一个 omega, 而不是同一个 kp。绝对增益会让前者数值发散。
    """
    dense = _full_mass_matrix(m, d)
    m_jj = float(dense[dof, dof])
    if not np.isfinite(m_jj) or m_jj <= 0.0:
        raise ToolFailure(f"关节有效惯量无效: M[{dof},{dof}]={m_jj!r}")
    # 退化自由度: 有效惯量比模型里最大的小若干量级时, 任何接触力都能主导它,
    # 结果测的是数值噪声而非资产。实测键盘旋钮 M_jj=3.8e-07 就是这种。
    biggest = float(np.max(np.diag(dense)))
    if biggest > 0 and m_jj / biggest < consts.min_joint_inertia_ratio:
        raise ToolFailure(
            f"关节有效惯量退化: M_jj={m_jj:.3g}, 仅为模型最大值 {biggest:.3g} 的 "
            f"{m_jj / biggest:.2e} 倍, 动力学结果不可信"
        )
    w, z = consts.mj_actuator_omega, consts.mj_actuator_zeta
    return m_jj * w * w, 2.0 * z * w * m_jj, m_jj


def _max_quat_angle_deg(q0: np.ndarray, q1: np.ndarray) -> float:
    """两组四元数逐体夹角的最大值(度)。"""
    dots = np.abs(np.einsum("ij,ij->i", q0, q1)).clip(0.0, 1.0)
    return float(np.degrees(2.0 * np.arccos(dots)).max())


def run_trials(urdf_path: str | Path, joint_id: int, consts: Consts,
               contract: dict | None = None) -> list[dict[str, Any]]:
    """§06 的三次物理鲁棒性试验。分数侧的取最低由 report.aggregate_trials 负责。"""
    return [run_trial(urdf_path, joint_id, consts, scale, contract) for scale in TRIALS]
