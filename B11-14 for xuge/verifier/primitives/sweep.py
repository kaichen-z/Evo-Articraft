"""32 步几何扫掠 —— 不跑动力学, 只查距离。

用 mj_geomDistance 而不是 mj_forward 后读 d.contact:
  - 它是纯几何查询, 不受 contype/conaffinity 和父子碰撞过滤影响
  - 同一姿态给同一个数, 与求解器状态无关, 满足 §06 的可复现要求
  - 穿透时返回负距离, 正好是 g0 需要的符号约定

**distmax 陷阱**: 超出量程时 mj_geomDistance 返回 distmax 本身, 而不是哨兵值。
把它当测量值用就会把"隔了 2 米"记成"隔了 1 米", 喂进 exp(-g0/(0.02L)) 就是
静默高估分数。下面每处查询都判 dist >= distmax 并标记截断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import mujoco
import numpy as np

from ..consts import SWEEP_STEPS, Consts
from ..sim.loader import (
    LoadedModel,
    bbox_diagonal,
    body_subtree_geoms,
    joint_name,
    part_label,
)

_TRUNCATED = object()


@dataclass
class SweepResult:
    """单个关节的扫掠产物。字段名对齐 metrics 期望的 signals 键。"""

    joint_name: str
    r_geom: float
    penetration_max: float
    l_j: float
    d_bbox: float
    g0: float
    g_drift: float
    d_anchor: float
    s_clearance: float
    first_blocked_step: int | None = None
    blocking_pair: list[str] | None = None
    interface_pair: list[str] | None = None
    gap_curve_summary: dict[str, Any] = field(default_factory=dict)
    truncated: list[str] = field(default_factory=list)

    def as_signals(self) -> dict[str, Any]:
        d = {
            "r_geom": self.r_geom,
            "penetration_max": self.penetration_max,
            "r_j": self.r_geom,           # PROVISIONAL R_J_DEF: 无阻塞可达行程比例
            "l_j": self.l_j,
            "d_bbox": self.d_bbox,
            "g0": self.g0,
            "g_drift": self.g_drift,
            "d_anchor": self.d_anchor,
            "s_clearance": self.s_clearance,
            "joint_name": self.joint_name,
            "gap_curve_summary": self.gap_curve_summary,
        }
        if self.first_blocked_step is not None:
            d["first_blocked_step"] = self.first_blocked_step
        if self.blocking_pair:
            d["blocking_pair"] = self.blocking_pair
            d["link_pair"] = self.blocking_pair
        if self.interface_pair:
            d["interface_pair"] = self.interface_pair
        return d


def _distance(model, data, g1: int, g2: int, distmax: float):
    """返回 (距离, fromto) 或 (_TRUNCATED, None)。截断绝不当测量值。"""
    fromto = np.zeros(6, dtype=np.float64)
    dist = mujoco.mj_geomDistance(model, data, int(g1), int(g2), float(distmax), fromto)
    if dist >= distmax:
        return _TRUNCATED, None
    return float(dist), fromto


def _closest(model, data, group_a: list[int], group_b: list[int], distmax: float):
    """两组几何间最近的一对。全部超量程时返回 (None, None, None, True)。"""
    best, best_pair, best_ft = None, None, None
    for a in group_a:
        for b in group_b:
            dist, ft = _distance(model, data, a, b, distmax)
            if dist is _TRUNCATED:
                continue
            if best is None or dist < best:
                best, best_pair, best_ft = dist, (a, b), ft
    return best, best_pair, best_ft, best is None


def sweep_joint(loaded: LoadedModel, joint_id: int, consts: Consts) -> SweepResult:
    """把关节 j 在其行程上均匀走 SWEEP_STEPS 步, 沿途查距离。"""
    m, d = loaded.model, loaded.data
    distmax = consts.mj_geom_distmax
    truncated: list[str] = []

    child_body = int(m.jnt_bodyid[joint_id])
    parent_body = int(m.body_parentid[child_body])
    moving = body_subtree_geoms(m, child_body)
    interface = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) == parent_body]
    moving_set = set(moving)
    third_party = [g for g in range(m.ngeom)
                   if g not in moving_set and int(m.geom_bodyid[g]) != parent_body]
    static = [g for g in range(m.ngeom) if g not in moving_set]

    lo, hi = (float(x) for x in m.jnt_range[joint_id])
    if not bool(m.jnt_limited[joint_id]) or hi <= lo:
        lo, hi = 0.0, 0.0
    qs = np.linspace(lo, hi, SWEEP_STEPS)

    qadr = int(m.jnt_qposadr[joint_id])
    q_saved = float(d.qpos[qadr])

    baseline_pen = None
    gaps: list[float] = []
    pens: list[float] = []
    clearances: list[float] = []
    first_blocked: int | None = None
    blocking_pair: list[str] | None = None
    interface_pair: list[str] | None = None
    d_anchor = 0.0
    block_thresh = consts.sweep_block_penetration_frac * loaded.d_bbox

    try:
        for i, q in enumerate(qs):
            d.qpos[qadr] = float(q)
            mujoco.mj_forward(m, d)

            # --- 接口间隙 (活动连杆 vs 父连杆) ---
            if interface:
                g, pair, ft, trunc = _closest(m, d, moving, interface, distmax)
                if trunc:
                    truncated.append(f"interface@step{i}")
                    g = distmax
                else:
                    if i == 0:
                        interface_pair = [part_label(m, pair[0]), part_label(m, pair[1])]
                        centre = (ft[:3] + ft[3:]) / 2.0
                        d_anchor = float(np.linalg.norm(centre - d.xanchor[joint_id]))
                gaps.append(float(g))

            # --- 与所有非活动几何的穿透 ---
            if static:
                nearest, pair, _ft, trunc = _closest(m, d, moving, static, distmax)
                pen = max(0.0, -nearest) if not trunc else 0.0
                if baseline_pen is None:
                    baseline_pen = pen
                new_pen = max(0.0, pen - baseline_pen)
                pens.append(new_pen)
                if first_blocked is None and new_pen > block_thresh:
                    first_blocked = i
                    if pair:
                        blocking_pair = [part_label(m, pair[0]), part_label(m, pair[1])]

            # --- 第三方净空 ---
            if third_party:
                c, _p, _f, trunc = _closest(m, d, moving, third_party, distmax)
                clearances.append(distmax if trunc else max(0.0, float(c)))
    finally:
        d.qpos[qadr] = q_saved
        mujoco.mj_forward(m, d)

    l_j = bbox_diagonal(m, d, moving)

    # r_geom: 首个阻塞步之前能走到的行程比例。均匀采样下第 i 步 = i/(N-1)。
    n = len(qs)
    r_geom = 1.0 if first_blocked is None else float(first_blocked) / max(1, n - 1)

    g0 = gaps[0] if gaps else 0.0
    g_drift = float(max(gaps) - min(gaps)) if len(gaps) > 1 else 0.0

    # s_clearance PROVISIONAL: 活动连杆到第三方几何的最小净空, 按 L_j 归一。
    if clearances and l_j > 0:
        s_clearance = float(np.clip(min(clearances) / (consts.clearance_scale * l_j), 0.0, 1.0))
    else:
        s_clearance = 1.0

    return SweepResult(
        joint_name=joint_name(m, joint_id),
        r_geom=float(np.clip(r_geom, 0.0, 1.0)),
        penetration_max=float(max(pens)) if pens else 0.0,
        l_j=l_j,
        d_bbox=loaded.d_bbox,
        g0=g0,
        g_drift=g_drift,
        d_anchor=d_anchor,
        s_clearance=s_clearance,
        first_blocked_step=first_blocked,
        blocking_pair=blocking_pair,
        interface_pair=interface_pair,
        gap_curve_summary={
            "steps": n,
            "gap_min": min(gaps) if gaps else None,
            "gap_max": max(gaps) if gaps else None,
            "gap_argmax_step": int(np.argmax(gaps)) if gaps else None,
            "penetration_argmax_step": int(np.argmax(pens)) if pens else None,
            "q_range": [lo, hi],
        },
        truncated=truncated,
    )
