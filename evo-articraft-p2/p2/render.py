"""冻结渲染协议：整体 4 视角 + 逐部件隔离渲染。

- 相机: 方位角 0/90/180/270, 俯仰 −20°, 距离 = 1.7 × 目标 AABB 对角线
- 材质: 统一中性灰; 光照: 增强 headlight; 背景: 用分割通道抠成浅灰
- 部件隔离: geom_group 切换(其余 geom 移入组3并在渲染选项里关闭)
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

from . import consts
from .mj_scene import Scene


class RenderProtocol:
    def __init__(self, scene: Scene):
        self.scene = scene
        scene.apply_neutral_material()
        self.renderer = mujoco.Renderer(
            scene.model, height=consts.RENDER_SIZE, width=consts.RENDER_SIZE
        )
        self.vopt = mujoco.MjvOption()

    def close(self) -> None:
        self.renderer.close()

    # ---------- 内部 ----------
    def _camera(self, lo: np.ndarray, hi: np.ndarray, azimuth: float) -> mujoco.MjvCamera:
        cam = mujoco.MjvCamera()
        cam.lookat[:] = (lo + hi) / 2.0
        diag = float(np.linalg.norm(hi - lo))
        cam.distance = max(consts.DIST_FACTOR * diag, 1e-3)
        cam.elevation = consts.ELEVATION
        cam.azimuth = azimuth
        return cam

    def _render_one(self, cam: mujoco.MjvCamera) -> np.ndarray:
        """RGB 渲染 + 分割抠背景 → 浅灰底图。"""
        r = self.renderer
        r.update_scene(self.scene.data, camera=cam, scene_option=self.vopt)
        rgb = r.render().copy()

        r.enable_segmentation_rendering()
        r.update_scene(self.scene.data, camera=cam, scene_option=self.vopt)
        seg = r.render()
        r.disable_segmentation_rendering()

        background = seg[:, :, 0] < 0
        rgb[background] = consts.BG_GRAY
        return rgb

    def _views(self, geom_ids: list[int] | None) -> dict[float, np.ndarray]:
        """geom_ids=None → 整体; 否则只渲染这些 geom(隔离)。相机框住目标。"""
        self.vopt.geomgroup[:] = 1
        self.vopt.geomgroup[3] = 0
        self.scene.set_visible_only(geom_ids)

        target = geom_ids if geom_ids else list(range(self.scene.model.ngeom))
        lo, hi = self.scene.world_aabb(target)

        out = {}
        for az in consts.AZIMUTHS:
            cam = self._camera(lo, hi, az)
            out[az] = self._render_one(cam)

        self.scene.set_visible_only(None)   # 恢复
        return out

    # ---------- 对外 ----------
    def global_views(self, save_dir: Path | None = None) -> dict[float, np.ndarray]:
        views = self._views(None)
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            for az, img in views.items():
                Image.fromarray(img).save(save_dir / f"global_az{int(az):03d}.png")
        return views

    def part_views(self, link: str, save_dir: Path | None = None) -> dict[float, np.ndarray] | None:
        geoms = self.scene.body_geoms(link)
        if not geoms:
            return None                      # link 无直属几何(或被融合) → 不可测
        lo, hi = self.scene.world_aabb(geoms)
        if float(np.linalg.norm(hi - lo)) < 1e-6:
            return None
        views = self._views(geoms)
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            for az, img in views.items():
                Image.fromarray(img).save(save_dir / f"{link}_az{int(az):03d}.png")
        return views
