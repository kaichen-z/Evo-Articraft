"""从 URDF XML 读取结构信息（link 名、joint 拓扑）。

MuJoCo 编译后会把固定 body 融合，所以拓扑一律从 XML 原文读。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class JointInfo:
    name: str
    jtype: str          # revolute / continuous / prismatic / fixed / ...
    parent: str
    child: str
    axis: tuple[float, float, float]


@dataclass
class UrdfInfo:
    links: list[str]
    joints: list[JointInfo]
    root_link: str

    @property
    def movable_joints(self) -> list[JointInfo]:
        return [j for j in self.joints if j.jtype in ("revolute", "continuous", "prismatic")]


def parse_urdf(path: str | Path) -> UrdfInfo:
    root = ET.parse(Path(path)).getroot()

    links = [l.get("name", "") for l in root.findall("link")]

    joints = []
    children = set()
    for j in root.findall("joint"):
        parent = j.find("parent")
        child = j.find("child")
        axis_el = j.find("axis")
        axis = (0.0, 0.0, 1.0)
        if axis_el is not None:
            vals = (axis_el.get("xyz") or "0 0 1").split()
            axis = tuple(float(v) for v in vals)  # type: ignore[assignment]
        ji = JointInfo(
            name=j.get("name", ""),
            jtype=j.get("type", "fixed"),
            parent=parent.get("link", "") if parent is not None else "",
            child=child.get("link", "") if child is not None else "",
            axis=axis,  # type: ignore[arg-type]
        )
        joints.append(ji)
        children.add(ji.child)

    roots = [l for l in links if l not in children]
    root_link = roots[0] if roots else (links[0] if links else "")

    return UrdfInfo(links=links, joints=joints, root_link=root_link)
