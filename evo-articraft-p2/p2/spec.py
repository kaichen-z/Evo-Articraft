"""P0 Prompt Contract（真格式）的加载与替身起草。

正式流程：这份 JSON 就是 P0 的结构化提示词契约，P2 只读四个字段：
    global_form → GF1, part_geometry → GF2,
    part_relations → GF3, proportion_claims → GF4
（required_parts 归 Gate；kinematic_claims/dynamics_claims 归 P3/P4，P2 不读。）

今天没有 P0，用「原始 prompt + URDF link 命名 + joint 拓扑 + 命名对称性」
起草一份 P0 同构的替身契约，落盘 specs/<rid>.json，可手工修订后重跑。
每条自动生成的 claim 都带 source 字段注明来历。

schema 对照 P0 文档（task-2_08-16-p0.html）的柜子示例：
    required_parts:    [{id, count, role}]
    global_form:       {category, geometry, coarse_structure}
    part_geometry:     [{id, geometry}]
    part_relations:    [{subject, relation, object}]   # inside/attached_to/above/aligned
    proportion_claims: 成组 {parts, measure, target_ratio[], tolerance}
                       或成对 {subject, object, measure, target_ratio, tolerance}
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path

from . import consts
from .urdf_info import UrdfInfo

ARTICRAFT_ROOT = Path(r"D:\articraft_project")

# 命名启发式（P0 缺位时的替身；正式 P0 里这些关系由作者声明）
INSIDE_WORDS = ("drawer", "tray", "rack", "bucket", "register", "cartridge")
ABOVE_WORDS = ("lid", "cover", "cap", "top_panel")


# ---------------------------------------------------------------- 工具

def _prompt_text(record_id: str) -> str:
    rec_dir = ARTICRAFT_ROOT / "articraft-data" / "records" / record_id / "revisions"
    if not rec_dir.exists():
        return ""
    for rev in sorted(rec_dir.glob("rev_*"), reverse=True):
        p = rev / "prompt.txt"
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _humanize(name: str) -> str:
    return re.sub(r"[_\-]+", " ", name).strip()


def part_id_of(instance_name: str) -> str:
    """实例名 → 抽象 part ID：去掉数字后缀与 left/right 前缀。
    drawer_0 → drawer;  left_wheel → wheel;  body → body"""
    base = re.sub(r"[_\-]?\d+$", "", instance_name)
    base = re.sub(r"^(left|right)[_\-]", "", base)
    return base or instance_name


# ---------------------------------------------------------------- 起草

def draft_contract(record_id: str, category: str, info: UrdfInfo) -> dict:
    cat = category.strip().rstrip(".").lower()
    movable_children = {j.child for j in info.movable_joints}

    # required_parts: 按抽象 part ID 分组计数
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for link in info.links:
        groups.setdefault(part_id_of(link), []).append(link)

    required_parts = []
    for pid, members in groups.items():
        role = "movable" if any(m in movable_children for m in members) else "fixed"
        required_parts.append({"id": pid, "count": len(members), "role": role})

    # global_form: 替身只有 category 可靠，geometry/coarse_structure 留空待 P0 填
    global_form = {
        "category": cat,
        "geometry": "",
        "coarse_structure": "",
    }

    # part_geometry: 每个抽象 part 一条；替身描述 = 人话化的部件名 + 类别语境
    part_geometry = [
        {"id": pid, "geometry": f"{_humanize(pid)} of a {cat}"}
        for pid in groups
    ]

    # part_relations: subject–relation–object 三元组
    part_relations: list[dict] = []
    for j in info.movable_joints:
        part_relations.append({
            "subject": j.child, "relation": "attached_to", "object": j.parent,
            "source": f"joint:{j.name}",
        })
        low = j.child.lower()
        if any(w in low for w in INSIDE_WORDS):
            part_relations.append({
                "subject": j.child, "relation": "inside", "object": j.parent,
                "source": f"name-heuristic:{j.child}",
            })
        if any(w in low for w in ABOVE_WORDS):
            part_relations.append({
                "subject": j.child, "relation": "above", "object": j.parent,
                "source": f"name-heuristic:{j.child}",
            })

    # proportion_claims: 命名对称组 → 成组形 claim（P0 真格式）
    proportion_claims: list[dict] = []
    for pid, members in groups.items():
        if len(members) >= 2:
            proportion_claims.append({
                "parts": list(members),
                "measure": "long",                # PROVISIONAL: 替身用最长边
                "target_ratio": [1.0] * len(members),
                "tolerance": consts.DEFAULT_TOLERANCE,
                "source": "symmetry-naming",
            })

    return {
        "record_id": record_id,
        "overall_description": _prompt_text(record_id),   # 只给人读，不进任何评分
        "required_parts": required_parts,
        "global_form": global_form,
        "part_geometry": part_geometry,
        "part_relations": part_relations,
        "proportion_claims": proportion_claims,
        "_standin_note": "P0 替身：由 URDF 命名/拓扑与 prompt 自动起草；正式 P0 契约可直接整体替换本文件",
    }


def load_or_draft(spec_dir: Path, record_id: str, category: str, info: UrdfInfo) -> dict:
    spec_dir.mkdir(parents=True, exist_ok=True)
    path = spec_dir / f"{record_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    contract = draft_contract(record_id, category, info)
    path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    return contract


# ---------------------------------------------------------------- 评分文本构造
# P0 明确规定 overall_description 不作为评分文本；GF1/GF2 文本只从对应字段构造。

def build_t_global(contract: dict) -> str:
    gf = contract.get("global_form", {})
    pieces = [gf.get("category", "").strip(),
              gf.get("geometry", "").strip(),
              gf.get("coarse_structure", "").strip()]
    pieces = [p for p in pieces if p]
    if not pieces:
        return "a 3D rendering of an object"
    head = f"a 3D rendering of a {pieces[0]}"
    rest = ", ".join(pieces[1:])
    return f"{head}, {rest}" if rest else head


def build_part_texts(contract: dict) -> dict[str, str]:
    """part_id → GF2 评分文本。"""
    return {
        e["id"]: f"a 3D rendering of a {e['geometry']}"
        for e in contract.get("part_geometry", [])
        if e.get("geometry")
    }
