from __future__ import annotations

from dataclasses import dataclass


PROVISIONAL_NOTES = {
    "A1_SPURIOUS_PENALTY": "A1 多余活动件的指数惩罚尚未由人工标签校准",
    "A2_COUNT_TYPE_WEIGHTS": "A2 数量与类型各 0.5 的权重来自 PRO-12 草案",
    "A3_PART_INTERFACE_WEIGHTS": "A3 部件/接口 0.7/0.3 权重来自 PRO-12 草案",
    "A4_VLM_WEIGHTS": "A4 VLM、跨视角、尺度权重尚未校准",
    "A4_SCALE_PRIOR": "类别中位尺度的来源与适用域尚未冻结",
    "A5_RELATION_WEIGHTS": "A5 四类空间关系权重尚未校准",
    "A6_DECAY_SCALES": "A6 穿透、脱离和悬浮衰减尺度尚未由开发集校准",
    "Q_TOOL": "置信度乘子 q_tool 尚未冻结",
    "Q_CONTRACT": "置信度乘子 q_contract 尚未冻结",
}


@dataclass(frozen=True)
class Consts:
    tau_a1: float = 0.70
    tau_a2: float = 0.70
    tau_a3: float = 0.70
    tau_a4: float = 0.70
    tau_a5: float = 0.70
    tau_a6: float = 0.70

    confidence_band: float = 0.20
    abstain_below: float = 0.50
    q_tool: float = 1.0
    q_contract: float = 1.0

    a2_count_weight: float = 0.50
    a2_type_weight: float = 0.50
    a3_parts_weight: float = 0.70
    a3_interfaces_weight: float = 0.30
    a4_realism_weight: float = 0.70
    a4_view_weight: float = 0.20
    a4_scale_weight: float = 0.10
    a5_position_weight: float = 0.35
    a5_orientation_weight: float = 0.25
    a5_side_weight: float = 0.20
    a5_neighborhood_weight: float = 0.20

    a6_penetration_scale: float = 0.002
    a6_detached_ratio_scale: float = 0.05
    a6_floating_gap_scale: float = 0.01

    def tau(self, metric: str) -> float:
        return getattr(self, f"tau_{metric.lower()}")


DEFAULT = Consts()
