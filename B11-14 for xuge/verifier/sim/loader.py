"""URDF -> MuJoCo 模型, 并判定物理参数来源。

MuJoCo 不接受"只有 visual 几何"的 URDF: visual geom 不参与惯量计算, 运动体
质量为 0 直接编译失败。ArtiCraft 的 `compile_level="visual"` 缓存正是这种。
我们不给它硬凑质量 —— 那等于伪造资产没有的物理参数, 再让下游按"真实测量"
打分。这类模型返回 ToolFailure, 由 metrics 转成 coverage="tool-failure"。

provenance 三档直接由 URDF 内容决定, 对应 PRO-12 §04 的 q_physics:
    <inertial> 存在            -> "asset"    1.0
    只有 <collision>, 质量按密度推 -> "inferred" 0.8
    两者都没有                  -> 加载失败, 不打分
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from ..consts import DT, Consts
from ..types import ToolFailure


@dataclass(frozen=True)
class LoadedModel:
    """一份加载好、协议参数已冻结的模型。"""

    model: Any                      # mujoco.MjModel
    data: Any                       # mujoco.MjData
    provenance: str                 # asset / inferred
    d_bbox: float                   # 整体包围盒对角线 D (米)
    source: Path
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def total_mass(self) -> float:
        """资产总质量 (kg), B13 的 mgT 基准。

        优先用 URDF 原文声明的总和: MuJoCo 会把焊到世界的 body 融进 world 并
        丢掉它们的质量, 对固定底座的资产那几乎是全部质量, mgT 会小一个量级。
        """
        declared = float(self.notes.get("declared_mass") or 0.0)
        return declared if declared > 0 else float(self.model.body_mass.sum())

    @property
    def mass_is_declared(self) -> bool:
        return float(self.notes.get("declared_mass") or 0.0) > 0


def inspect_urdf(path: str | Path) -> dict[str, Any]:
    """只读 XML, 不进仿真器 —— 判定 provenance 与是否可用。"""
    p = Path(path)
    try:
        root = ET.parse(p).getroot()
    except ET.ParseError as e:
        raise ToolFailure(f"URDF 解析失败: {e}") from e

    n_inertial = len(root.findall(".//inertial"))
    n_collision = len(root.findall(".//collision"))
    n_visual = len(root.findall(".//visual"))
    n_joint = len(root.findall("joint"))

    # MuJoCo 把焊到世界的 body 融进 world 并丢掉它们的质量, 所以 body_mass.sum()
    # 会漏掉固定底座 —— 对一个固定在世界上的柜子, 那几乎是全部质量。
    # B13 的 mgT 基准要的是资产总质量, 从 URDF 原文取。
    declared = 0.0
    for mass_el in root.findall(".//inertial/mass"):
        try:
            declared += float(mass_el.get("value", "0"))
        except ValueError:
            pass

    if n_inertial:
        provenance = "asset"
    elif n_collision:
        provenance = "inferred"
    else:
        provenance = None

    return {
        "n_inertial": n_inertial, "n_collision": n_collision,
        "n_visual": n_visual, "n_joint": n_joint,
        "declared_mass": declared,
        "provenance": provenance,
    }


def load_urdf(path: str | Path, consts: Consts) -> LoadedModel:
    """加载 URDF 并按 §06 冻结协议参数。视觉级模型抛 ToolFailure。"""
    p = Path(path)
    if not p.exists():
        raise ToolFailure(f"URDF 不存在: {p}")

    info = inspect_urdf(p)
    if info["provenance"] is None:
        raise ToolFailure(
            f"视觉级模型: {info['n_visual']} 个 visual, 无 inertial 也无 collision。"
            f"MuJoCo 无法从 visual 几何推惯量, 不为它伪造物理参数"
        )

    try:
        model = mujoco.MjModel.from_xml_path(str(p))
    except Exception as e:                      # mujoco 抛的是 ValueError
        raise ToolFailure(f"MuJoCo 编译失败: {str(e).strip().splitlines()[0]}") from e

    _freeze_protocol(model, consts)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    return LoadedModel(
        model=model, data=data,
        provenance=info["provenance"],
        d_bbox=bbox_diagonal(model, data),
        source=p,
        notes={k: v for k, v in info.items() if k != "provenance"},
    )


def _freeze_protocol(model: Any, consts: Consts) -> None:
    """把 §06 冻结量与 PROVISIONAL 接触参数写进模型。

    不这么做的话, timestep 用的是 MuJoCo 默认的 0.002 而不是冻结的 1/240,
    接触参数则取决于每份 URDF 自己带了什么 —— 判定就不可复现了。
    """
    model.opt.timestep = DT
    model.geom_solref[:] = np.asarray(consts.mj_solref, dtype=float)
    model.geom_solimp[:] = np.asarray(consts.mj_solimp, dtype=float)


def bbox_diagonal(model: Any, data: Any, geom_ids: list[int] | None = None) -> float:
    """几何包围盒对角线。geom_ids 为 None 时算整体, 即符号表里的 D。

    用 geom_rbound (包围球半径) 把几何自身尺寸算进去 —— 只用 geom_xpos
    会把一个大立方体算成一个点。
    """
    ids = list(range(model.ngeom)) if geom_ids is None else list(geom_ids)
    if not ids:
        return 0.0
    pos = data.geom_xpos[ids]
    r = model.geom_rbound[ids].reshape(-1, 1)
    lo = (pos - r).min(axis=0)
    hi = (pos + r).max(axis=0)
    return float(np.linalg.norm(hi - lo))


def body_subtree_geoms(model: Any, body_id: int) -> list[int]:
    """body 及其所有后代上的 geom —— 活动连杆的完整几何。"""
    wanted = {int(body_id)}
    for b in range(model.nbody):
        parent = b
        while parent > 0:
            if parent == body_id:
                wanted.add(b)
                break
            parent = int(model.body_parentid[parent])
    return [g for g in range(model.ngeom) if int(model.geom_bodyid[g]) in wanted]


def joint_link_diagonal(loaded: LoadedModel, joint_id: int) -> float:
    """关节 j 的活动连杆包围盒对角线, 即符号表里的 L_j。"""
    child_body = int(loaded.model.jnt_bodyid[joint_id])
    geoms = body_subtree_geoms(loaded.model, child_body)
    return bbox_diagonal(loaded.model, loaded.data, geoms)


def joint_name(model: Any, joint_id: int) -> str:
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id) or f"joint_{joint_id}"


def geom_name(model: Any, geom_id: int) -> str:
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or f"geom_{geom_id}"


def part_label(model: Any, geom_id: int) -> str:
    """几何所属零件的可回溯名字 (铁律 6)。

    优先 geom 名: MuJoCo 会把焊到世界的 body 融进 world, 只报 body 名的话
    "抽屉撞上侧板"会变成 "slider vs world", 回溯不到具体零件。geom 名在
    融合后仍然保留。
    """
    g = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
    if g:
        return g
    return body_name(model, int(model.geom_bodyid[geom_id]))


def body_name(model: Any, body_id: int) -> str:
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or f"body_{body_id}"


def movable_joints(model: Any) -> list[int]:
    """有非零行程的铰接/滑动关节。range 为 [0,0] 的装饰性关节不算。"""
    out = []
    for j in range(model.njnt):
        jtype = int(model.jnt_type[j])
        if jtype not in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
            continue
        lo, hi = model.jnt_range[j]
        if bool(model.jnt_limited[j]) and abs(hi - lo) <= 0.0:
            continue
        out.append(j)
    return out
