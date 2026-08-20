"""MuJoCo 场景封装：加载、几何测量（AABB / 符号距离）、部件分组。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import mujoco
import numpy as np

from . import consts


@dataclass
class Scene:
    model: mujoco.MjModel
    data: mujoco.MjData
    urdf_path: Path
    d_bbox: float = 0.0
    body_of_link: dict[str, int] = field(default_factory=dict)
    fused_links: set[str] = field(default_factory=set)

    # ---------- 构造 ----------
    @classmethod
    def load(cls, urdf_path: str | Path, urdf_info=None) -> "Scene":
        p = Path(urdf_path)

        # 注入 MuJoCo 扩展标签: fusestatic="false" 禁止把 fixed link 融合进父 body,
        # 让所有零件按名字可查(否则需要 fused-proxy 别名, 精度打折)。
        # 只在内存里改, 不动资产源文件; meshdir 指向 URDF 所在目录以解析相对网格路径。
        model = None
        try:
            xml = p.read_text(encoding="utf-8", errors="replace")
            if "<mujoco" not in xml:
                meshdir = str(p.parent).replace("\\", "/")
                inject = f'<mujoco><compiler fusestatic="false" meshdir="{meshdir}"/></mujoco>'
                m = re.search(r"<robot\b[^>]*>", xml)
                if m:
                    xml = xml[: m.end()] + "\n  " + inject + xml[m.end():]
                    model = mujoco.MjModel.from_xml_string(xml)
        except Exception:
            model = None
        if model is None:
            model = mujoco.MjModel.from_xml_path(str(p))   # 回退: 旧路径(会融合)

        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)

        scene = cls(model=model, data=data, urdf_path=p)

        # link 名 → body id（MuJoCo 保留 URDF link 名作为 body 名）
        for bid in range(model.nbody):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, bid)
            if name:
                scene.body_of_link[name] = bid

        # MuJoCo 会把 fixed joint 的子 link 融合进父 body（根 link 融进 world）。
        # 对每个查不到的 link，沿 fixed 链向上别名到实际存在的 body。
        # 注意：别名后测的是融合体（含兄弟 geom），精度有损，测量结果里会带 fused 标记。
        if urdf_info is not None:
            fixed_parent = {
                j.child: j.parent for j in urdf_info.joints if j.jtype == "fixed"
            }
            for link in urdf_info.links:
                if link in scene.body_of_link:
                    continue
                cur, hops = link, 0
                while cur not in scene.body_of_link and hops < 64:
                    if cur == urdf_info.root_link:
                        scene.body_of_link[link] = 0
                        break
                    if cur not in fixed_parent:
                        break
                    cur, hops = fixed_parent[cur], hops + 1
                else:
                    if cur in scene.body_of_link:
                        scene.body_of_link[link] = scene.body_of_link[cur]
                if link in scene.body_of_link:
                    scene.fused_links.add(link)

        lo, hi = scene.world_aabb(list(range(model.ngeom)))
        scene.d_bbox = float(np.linalg.norm(hi - lo))
        return scene

    # ---------- 几何查询 ----------
    def body_geoms(self, link: str) -> list[int]:
        """该 link 直属的 geom id 列表（不含子树）。"""
        bid = self.body_of_link.get(link, -1)
        if bid < 0:
            return []
        adr = int(self.model.body_geomadr[bid])
        num = int(self.model.body_geomnum[bid])
        return list(range(adr, adr + num))

    def world_aabb(self, geom_ids: list[int]) -> tuple[np.ndarray, np.ndarray]:
        """一组 geom 的世界系 AABB (lo, hi)。"""
        if not geom_ids:
            z = np.zeros(3)
            return z, z
        corners = []
        signs = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=float)
        for g in geom_ids:
            center = self.model.geom_aabb[g, :3]
            half = self.model.geom_aabb[g, 3:]
            xpos = self.data.geom_xpos[g]
            xmat = self.data.geom_xmat[g].reshape(3, 3)
            local = center[None, :] + signs * half[None, :]
            world = xpos[None, :] + local @ xmat.T
            corners.append(world)
        allc = np.concatenate(corners, axis=0)
        return allc.min(axis=0), allc.max(axis=0)

    def min_signed_distance(self, geoms_a: list[int], geoms_b: list[int]) -> float:
        """两组 geom 间的最小符号距离（负 = 穿透）。"""
        if not geoms_a or not geoms_b:
            return float("nan")
        distmax = max(self.d_bbox, 1e-3)
        best = float("inf")
        fromto = np.zeros(6)
        for ga in geoms_a:
            for gb in geoms_b:
                d = mujoco.mj_geomDistance(self.model, self.data, ga, gb, distmax, fromto)
                if d < best:
                    best = d
        return float(best)

    def displaced_min_signed_distance(self, geoms_a: list[int], geoms_b: list[int],
                                      offset) -> float:
        """把 geoms_a 整体虚拟平移 offset（世界系，米）后，与 geoms_b 的最小符号距离。

        实现：mj_geomDistance 直接读取 data.geom_xpos/geom_xmat 的当前值，
        所以临时改写 geoms_a 对应行、查询、再精确还原即可——不动 qpos、
        不受关节约束限制（这正是"不信关节、只问几何"的支撑探测要的性质）。
        """
        if not geoms_a or not geoms_b:
            return float("nan")
        off = np.asarray(offset, dtype=float)
        saved = self.data.geom_xpos[geoms_a].copy()
        try:
            self.data.geom_xpos[geoms_a] = saved + off
            return self.min_signed_distance(geoms_a, geoms_b)
        finally:
            self.data.geom_xpos[geoms_a] = saved

    # ---------- 渲染辅助 ----------
    def apply_neutral_material(self) -> None:
        self.model.geom_rgba[:, :3] = consts.NEUTRAL_GRAY
        self.model.geom_rgba[:, 3] = 1.0
        hl = self.model.vis.headlight
        hl.ambient[:] = consts.HEADLIGHT_AMBIENT
        hl.diffuse[:] = consts.HEADLIGHT_DIFFUSE

    def set_visible_only(self, geom_ids: list[int] | None) -> None:
        """把指定 geom 置为组 0，其余置为组 3（渲染时关掉组 3 实现隔离）。
        None 表示全部可见。"""
        if geom_ids is None:
            self.model.geom_group[:] = 0
            return
        self.model.geom_group[:] = 3
        for g in geom_ids:
            self.model.geom_group[g] = 0
