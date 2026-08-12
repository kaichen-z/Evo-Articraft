"""输出契约序列化 (PRO-12 §09) 与试验聚合 (§06)。"""

from __future__ import annotations

import copy
import json
from typing import Any, Iterable

from ..consts import (ACTUATE_S, DT, HOLD_S, SETTLE_S, TRIAL_AGGREGATION_LABEL,
                      TRIALS, Consts)
from ..types import Coverage, MetricResult

VERIFIER_VERSION = "articraft-b11-b14-v0.1"


def _detach(r: MetricResult, **diag: Any) -> MetricResult:
    """复制一份结果并追加诊断字段, 不碰原对象。

    以前 aggregate_trials 返回的就是入参里那个最低分对象本身, 还就地往它的
    diagnostics 里写 —— 聚合结果和该次试验的记录成了同一个对象, 之后改报告
    会连带改掉试验记录。这里保证返回的永远是独立对象。
    """
    out = copy.deepcopy(r)
    out.diagnostics.update(diag)
    return out


def aggregate_trials(results: Iterable[MetricResult]) -> MetricResult:
    """三次物理鲁棒性试验取最低分 (PRO-12 §06)。

    防止只在一组猜测参数下偶然通过。任一试验工具故障 -> 整体工具故障。
    返回的是新对象, 入参不受影响。
    """
    results = list(results)
    if not results:
        raise ValueError("no trials")
    for r in results:
        if r.coverage is Coverage.TOOL_FAILURE:
            return _detach(r)
    scored = [r for r in results if r.score is not None]
    if not scored:
        return _detach(results[0])
    worst = min(scored, key=lambda r: r.score)
    return _detach(
        worst,
        trial_scores=[r.score for r in scored],
        trial_aggregation=TRIAL_AGGREGATION_LABEL,
    )


def _trial_label(scale: float) -> str:
    """§06 的 TRIALS 缩放系数 -> 输出契约里的写法。

    以前这里是写死的 ["nominal","0.8x","1.2x"], 改 TRIALS 报告会说谎。
    """
    return "nominal" if scale == 1.0 else f"{scale:g}x"


def simulator_block(consts: Consts, provenance: str = "default",
                    tool_failures: list[str] | None = None) -> dict[str, Any]:
    return {
        "dt_s": round(DT, 7),
        "settle_s": SETTLE_S,
        "actuate_s": ACTUATE_S,
        "hold_s": HOLD_S,
        "trials": [_trial_label(t) for t in TRIALS],
        "aggregation": TRIAL_AGGREGATION_LABEL,
        "physics_provenance": provenance,
        "engine": None,   # 待确认: Isaac Sim / Isaac Lab / 其他
        "tool_failures": tool_failures or [],
    }


def build_report(results: dict[str, MetricResult], consts: Consts,
                 provenance: str = "default") -> dict[str, Any]:
    metrics = {k: v.to_dict() for k, v in results.items()}

    counted = [r for r in results.values() if r.counts_in_aggregate]
    coverage_rate = len(counted) / len(results) if results else 0.0

    provisional: set[str] = set()
    for r in results.values():
        provisional.update(r.provisional_params)

    failures = [
        r.failure_reason for r in results.values()
        if r.coverage is Coverage.TOOL_FAILURE and r.failure_reason
    ]

    return {
        "verifier_version": VERIFIER_VERSION,
        "human_metrics": metrics,
        "simulator": simulator_block(consts, provenance, failures),
        "coverage": {
            "scored_metrics": len(counted),
            "total_metrics": len(results),
            "rate": round(coverage_rate, 4),
        },
        "provisional_params": sorted(provisional),
        "repair_queue": _repair_queue(results),
    }


def _repair_queue(results: dict[str, MetricResult]) -> list[str]:
    """去重后的修复建议。

    注意: 分数侧没有去重机制 —— 一个"没有合页"会同时压低 B12,
    一个"抽屉被挡"会同时压低 B11 与 B13, Score_full 对同一根因重复计价。
    已列入待确认问题。这里只保证 repair_queue 本身不重复。
    """
    seen, out = set(), []
    for r in results.values():
        if r.prediction.value == "fail" and r.repair_hint and r.repair_hint not in seen:
            seen.add(r.repair_hint)
            out.append(r.repair_hint)
    return out


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
