"""需求契约 schema (B11-B14 相关部分)。

契约是**输入的 JSON**, 不在运行时由 LLM 生成 (CLAUDE.md 铁律 7)。
只列 B11-B14 用得到的字段; A1-A6/B7-B10 的字段由他人负责。
"""

from __future__ import annotations

from typing import Any

CONTRACT_TEMPLATE: dict[str, Any] = {
    "asset_id": "",
    "category": "",
    # B11: 预期活动范围。缺失 -> B11 返回 N/A
    "expected_range": {
        # "<joint_name>": {"min": 0.0, "max": 0.45, "unit": "m", "source": "prompt"}
    },
    # B12: 预期接口与安装
    "expected_interfaces": {
        # "<joint_name>": {"type": "hinge", "source": "prompt"}
    },
    "mounting": None,      # 例: {"base_link": "cabinet_body", "fixed_to_world": True}
    "payload": None,       # 例: {"link": "shelf", "mass_kg": 2.0}
    # B13: 预期活动件 + 允许的接触白名单
    "expected_movables": [],           # ["drawer", "door"]
    "expected_contacts": [],           # [["drawer", "rail"]]
    # B14: 耦合与闭环。两者皆空 -> B14 返回 N/A
    "coupling": [],        # [{"joints": ["l", "r"], "ratio": 1.0, "phase": 0.0}]
    "closed_loop": [],     # [{"name": "four_bar", "links": [...]}]
    "task": None,          # 例: {"name": "open_drawer", "success": "..." }
}

_B11_REQUIRED = ("expected_range",)
_B12_REQUIRED = ("expected_interfaces", "mounting")
_B13_REQUIRED = ("expected_movables",)
_B14_REQUIRED = ("coupling", "closed_loop")


def new_contract(**overrides: Any) -> dict[str, Any]:
    """构造一份契约, 未指定字段用模板默认值。"""
    import copy

    c = copy.deepcopy(CONTRACT_TEMPLATE)
    unknown = set(overrides) - set(c)
    if unknown:
        raise KeyError(f"未知契约字段: {sorted(unknown)}")
    c.update(overrides)
    return c


def applicable_metrics(contract: dict) -> dict[str, bool]:
    """哪些指标适用。不适用的返回 N/A, 不进聚合分母 (PRO-12 §07)。"""
    return {
        "B11": any(contract.get(k) for k in _B11_REQUIRED),
        "B12": any(contract.get(k) for k in _B12_REQUIRED),
        "B13": any(contract.get(k) for k in _B13_REQUIRED),
        "B14": any(contract.get(k) for k in _B14_REQUIRED),
    }


def validate(contract: dict) -> list[str]:
    """返回问题列表, 空列表表示通过。不做静默修复 (PRO-12 §02 模块1)。"""
    problems = []
    for key in CONTRACT_TEMPLATE:
        if key not in contract:
            problems.append(f"缺少字段: {key}")
    for c in contract.get("coupling") or []:
        if "joints" not in c or len(c.get("joints", [])) < 2:
            problems.append(f"耦合项需要至少两个关节: {c}")
        if "ratio" not in c:
            problems.append(f"耦合项缺少预期传动比 r_exp: {c}")
    return problems
