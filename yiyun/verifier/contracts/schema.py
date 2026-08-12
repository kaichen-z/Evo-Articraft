"""A1-A6 需求契约。

契约是评分器输入，不在 metrics 运行时调用 LLM 生成。每一项硬约束应保存
Prompt 原文来源；推断项只能 advisory，不能直接扣分。
"""

from __future__ import annotations

import copy
from typing import Any


CONTRACT_TEMPLATE: dict[str, Any] = {
    "asset_id": "",
    "category": "",
    "required_movables": [],
    "required_parts": [],
    "required_interfaces": [],
    "appearance_claims": [],
    "category_scale": None,
    "spatial_relations": [],
    "advisory_inferences": [],
}


def new_contract(**overrides: Any) -> dict[str, Any]:
    contract = copy.deepcopy(CONTRACT_TEMPLATE)
    unknown = set(overrides) - set(contract)
    if unknown:
        raise KeyError(f"未知契约字段: {sorted(unknown)}")
    contract.update(overrides)
    return contract


def applicable_metrics(contract: dict) -> dict[str, bool]:
    return {
        "A1": bool(contract.get("required_movables")),
        "A2": bool(contract.get("required_parts")),
        "A3": bool(contract.get("required_parts") or contract.get("required_interfaces")),
        "A4": bool(contract.get("appearance_claims") or contract.get("category_scale")),
        "A5": bool(contract.get("spatial_relations")),
        "A6": True,
    }


def validate(contract: dict) -> list[str]:
    problems: list[str] = []
    for key in CONTRACT_TEMPLATE:
        if key not in contract:
            problems.append(f"缺少字段: {key}")

    for field in ("required_movables", "required_parts", "required_interfaces",
                  "appearance_claims", "spatial_relations"):
        for item in contract.get(field) or []:
            if not isinstance(item, dict):
                problems.append(f"{field} 项必须是对象: {item!r}")
                continue
            if item.get("source") != "prompt":
                problems.append(f"{field} 的硬约束必须标 source=prompt: {item!r}")
            if not item.get("evidence_text"):
                problems.append(f"{field} 缺少 Prompt 原文 evidence_text: {item!r}")
    return problems
