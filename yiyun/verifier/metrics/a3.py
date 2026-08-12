"""A3 必要结构完整性。"""

from __future__ import annotations

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "A3"


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    required_parts = C.contract_ids(contract.get("required_parts") or [])
    required_interfaces = C.contract_ids(contract.get("required_interfaces") or [])
    if not required_parts and not required_interfaces:
        return C.not_applicable(METRIC, consts, "Prompt 未明确要求部件或功能前置接口")
    if required_parts and signals.get("part_match_failed"):
        return C.tool_failure(METRIC, consts, "部件名称解析不完整，不能将缺失解释为资产错误")

    matched_parts = set(map(str, signals.get("matched_required_parts") or []))
    matched_interfaces = set(map(str, signals.get("matched_required_interfaces") or []))
    if required_parts and signals.get("matched_required_parts") is None:
        return C.tool_failure(METRIC, consts, "缺少必要部件匹配证据")
    if required_interfaces and signals.get("matched_required_interfaces") is None:
        return C.tool_failure(METRIC, consts, "缺少必要接口匹配证据")

    parts_score = len(matched_parts & set(required_parts)) / len(required_parts) if required_parts else None
    interfaces_score = (
        len(matched_interfaces & set(required_interfaces)) / len(required_interfaces)
        if required_interfaces else None
    )
    if parts_score is not None and interfaces_score is not None:
        value = consts.a3_parts_weight * parts_score + consts.a3_interfaces_weight * interfaces_score
    else:
        value = parts_score if parts_score is not None else interfaces_score

    missing_parts = sorted(set(required_parts) - matched_parts)
    missing_interfaces = sorted(set(required_interfaces) - matched_interfaces)
    sub = {}
    if parts_score is not None:
        sub["C_parts"] = parts_score
    if interfaces_score is not None:
        sub["C_interfaces"] = interfaces_score

    coverage = Coverage.PARTIAL if required_interfaces and signals.get("interface_measurement_partial") else Coverage.FULL
    return C.build_result(
        METRIC, value, coverage, consts,
        tools=["contract", "semantic-match", "geometry-existence"],
        sub_scores=sub,
        evidence={"missing_parts": missing_parts, "missing_interfaces": missing_interfaces,
                  "interface_results": signals.get("interface_results", [])},
        failure_reason=None if value >= consts.tau_a3 else "Prompt 明确要求的部件或功能接口缺失",
        repair_hint="补齐缺失的必要部件或功能前置接口",
        provisional_params=["A3_PART_INTERFACE_WEIGHTS", "Q_TOOL", "Q_CONTRACT"],
    )
