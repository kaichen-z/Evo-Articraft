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


def kinematic_role(info: UrdfInfo, link: str) -> dict:
    """Structural (not visual) read of a link's role in the joint graph.

    Shape alone cannot tell a short rigid connecting-rod apart from a hinge/
    pivot component -- both are commonly modeled as a bare cylinder, and
    "arm" is not required to look elongated (short links are normal in real
    mechanisms: scissor lifts, articulated lamp arms). What shape can't
    settle, topology can: a body that sits between two joints (one connecting
    it to its parent, at least one more connecting a child to it) is playing
    the role of a link/connecting-rod, whatever it happens to look like.
    """
    parent_joint = next((j for j in info.joints if j.child == link), None)
    child_joints = [j for j in info.joints if j.parent == link]
    return {
        "is_root": link == info.root_link,
        "parent_joint_type": parent_joint.jtype if parent_joint else None,
        "n_child_joints": len(child_joints),
        "child_joint_types": [j.jtype for j in child_joints],
        "is_intermediate_link": bool(parent_joint is not None and child_joints),
    }
