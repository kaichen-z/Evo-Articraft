"""§06 冻结的试验协议: 2s 静置 -> 3s 驱动 -> 1s 保持, dt = 1/240。

q_ref(t) 的形状规范没冻结 (QUESTIONS.md 第 1 条) —— 当前占位梯形。
换轨迹只改这里和 consts 里的 QREF_*, 打分函数一行不动。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..consts import ACTUATE_S, DT, HOLD_S, SETTLE_S, Consts


@dataclass(frozen=True)
class Phases:
    """按冻结时长展开的步数。"""

    settle: int
    actuate: int
    hold: int

    @property
    def total(self) -> int:
        return self.settle + self.actuate + self.hold

    def phase_at(self, step: int) -> str:
        if step < self.settle:
            return "settle"
        if step < self.settle + self.actuate:
            return "actuate"
        return "hold"


def phases(dt: float = DT) -> Phases:
    return Phases(
        settle=round(SETTLE_S / dt),
        actuate=round(ACTUATE_S / dt),
        hold=round(HOLD_S / dt),
    )


def trapezoid_fraction(u: float, accel_frac: float) -> float:
    """梯形速度曲线的归一化位置, u = t/T ∈ [0,1] -> s ∈ [0,1]。

    加速段与减速段各占 accel_frac, 中间匀速。accel_frac <= 0 退化成线性斜坡。
    """
    u = min(1.0, max(0.0, u))
    a = accel_frac
    if a <= 0.0:
        return u
    if a >= 0.5:
        a = 0.5
    v = 1.0 / (1.0 - a)          # 归一化巡航速度
    if u < a:
        return 0.5 * (v / a) * u * u
    if u < 1.0 - a:
        return 0.5 * v * a + v * (u - a)
    return 1.0 - 0.5 * (v / a) * (1.0 - u) * (1.0 - u)


def q_ref(step: int, ph: Phases, q_start: float, q_target: float,
          consts: Consts, dt: float = DT) -> float:
    """第 step 步的目标关节位置。

    静置段保持 q_start; 驱动段按 QREF_PROFILE 走完全程; 保持段停在 q_target。
    """
    if step < ph.settle:
        return q_start
    if step >= ph.settle + ph.actuate:
        return q_target

    t = (step - ph.settle) * dt
    duration = consts.qref_duration_s if consts.qref_duration_s > 0 else ACTUATE_S
    u = t / duration
    if consts.qref_profile == "trapezoid":
        s = trapezoid_fraction(u, consts.qref_accel_frac)
    elif consts.qref_profile == "ramp":
        s = min(1.0, max(0.0, u))
    else:
        raise ValueError(f"未知的 QREF_PROFILE: {consts.qref_profile!r}")
    return q_start + s * (q_target - q_start)
