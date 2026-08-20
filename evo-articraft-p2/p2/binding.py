"""部件绑定层：part 引用 → 模型实体（body/geom）。

正式流程里这张表由 P1 Gate 交付（P0: "Gate output = part ID → MJCF body/geom 绑定,
part mask / isolated render"）。今天没有 P1，用 URDF link 名充当实例 ID 起草替身绑定。

引用解析顺序（GF3/GF4 的所有名字都从这里走）:
    1. 实例 ID   (drawer_0)         → 该实例
    2. 抽象 part (drawer)           → 该 part 的全部实例
    3. geom 名   (drawer_front)     → 子部件级引用, 绑到同名 geom（伪实例）
    4. 都不中                        → None (claim 记 unmeasurable, 不折 0 分)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import mujoco

from .mj_scene import Scene
from .spec import part_id_of
from .urdf_info import UrdfInfo


@dataclass
class PartInstance:
    instance_id: str
    part_id: str
    body_id: int                  # -1 表示 geom 级伪实例
    geom_ids: list[int]
    fused: bool = False           # 被 MuJoCo 融合、按别名测量（URDF 时代的替身痕迹）
    is_root: bool = False
    pseudo: bool = False          # geom 名兜底出来的子部件引用


@dataclass
class PartBinding:
    instances: dict[str, PartInstance] = field(default_factory=dict)
    by_part: dict[str, list[str]] = field(default_factory=dict)
    _scene: Scene | None = None

    # ---------- 构造 ----------
    @classmethod
    def from_urdf_standin(cls, scene: Scene, info: UrdfInfo) -> "PartBinding":
        b = cls(_scene=scene)
        for link in info.links:
            inst = PartInstance(
                instance_id=link,
                part_id=part_id_of(link),
                body_id=scene.body_of_link.get(link, -1),
                geom_ids=scene.body_geoms(link),
                fused=link in scene.fused_links,
                is_root=(link == info.root_link),
            )
            b.instances[link] = inst
            b.by_part.setdefault(inst.part_id, []).append(link)
        return b

    # ---------- 解析 ----------
    def resolve(self, ref: str) -> list[PartInstance] | None:
        if ref in self.instances:
            return [self.instances[ref]]
        if ref in self.by_part:
            return [self.instances[i] for i in self.by_part[ref]]
        # geom 名兜底: 子部件级引用 (如 drawer_front)
        if self._scene is not None:
            m = self._scene.model
            geoms = [g for g in range(m.ngeom)
                     if mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) == ref]
            if geoms:
                return [PartInstance(instance_id=ref, part_id=ref, body_id=-1,
                                     geom_ids=geoms, pseudo=True)]
        return None

    # ---------- GF2 部件渲染的准入 ----------
    def renderable(self, inst: PartInstance) -> bool:
        """中间融合 link 的隔离渲染会画出整个融合体(标签失真) → 不渲染；根 link 例外。"""
        if not inst.geom_ids:
            return False
        if inst.fused and not inst.is_root:
            return False
        return True
