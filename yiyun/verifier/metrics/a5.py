"""A5 位置、朝向与装配关系。"""

from __future__ import annotations

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "A5"
COMPONENTS = ("position", "orientation", "side", "neighborhood")


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    relations = contract.get("spatial_relations") or []
    if not relations:
        return C.not_applicable(METRIC, consts, "Prompt 未明确要求可计算的空间/装配关系")
    results = signals.get("relation_results")
    if results is None:
        return C.tool_failure(METRIC, consts, "缺少空间关系测量结果")

    expected_ids = C.contract_ids(relations)
    by_id = {str(item.get("id")): item for item in results if item.get("id")}
    missing_relations = sorted(set(expected_ids) - set(by_id))

    weights = {
        "position": consts.a5_position_weight,
        "orientation": consts.a5_orientation_weight,
        "side": consts.a5_side_weight,
        "neighborhood": consts.a5_neighborhood_weight,
    }
    component_values: dict[str, list[float]] = {name: [] for name in COMPONENTS}
    violations: list[dict] = []
    for relation_id in expected_ids:
        item = by_id[relation_id]
        for name in COMPONENTS:
            if item.get(name) is not None:
                component_values[name].append(C.clip01(float(item[name])))
        available = [float(item[name]) for name in COMPONENTS if item.get(name) is not None]
        if available and sum(available) / len(available) < consts.tau_a5:
            violations.append({"id": relation_id, "measurements": item})

    means = {name: sum(values) / len(values) for name, values in component_values.items() if values}
    if not means:
        return C.unsupported(METRIC, consts, "关系模板存在，但没有可计算的关系分量")

    available_weight = sum(weights[name] for name in means)
    measured = sum(weights[name] * means[name] for name in means)
    full = len(means) == len(COMPONENTS)
    # Missing components are N/A, not a perfect score.  Renormalise the formula
    # over the components that the relation type makes measurable.
    value = measured / available_weight
    coverage = Coverage.FULL if full else Coverage.PARTIAL

    return C.build_result(
        METRIC, value, coverage, consts,
        tools=["contract", "relative-transform", "geometry"],
        sub_scores={f"S_{name}": value_ for name, value_ in means.items()},
        evidence={"violated_relations": violations,
                  "unmeasured_relations": missing_relations,
                  "missing_components": sorted(set(COMPONENTS) - set(means))},
        failure_reason=None if value >= consts.tau_a5 else "一个或多个部件的空间/装配关系不满足契约",
        repair_hint="根据违规关系移动或旋转对应部件，并重新检查连接邻域",
        provisional_params=["A5_RELATION_WEIGHTS", "Q_TOOL", "Q_CONTRACT"],
    )
