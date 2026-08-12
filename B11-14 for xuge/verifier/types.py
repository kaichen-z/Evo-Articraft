"""B11-B14 共用的数据类型。

设计约束(见 CLAUDE.md):
- coverage 必须与 score 同时返回
- 工具故障 != 资产失败: score=None, coverage=TOOL_FAILURE
- 不适用: score=None, coverage=NOT_APPLICABLE, 不进聚合分母
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Coverage(str, Enum):
    """覆盖程度。前五项来自 PRO-12 §04。

    TOOL_FAILURE 是本实现的扩展: 规范 §04 只列了五档, 但 §06 要求
    仿真器故障返回独立的 tool_failure 而非资产 0 分, 两处未统一。
    已列入待确认问题。
    """

    FULL = "full"
    ESTIMATED_PHYSICS = "estimated-physics"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not-applicable"
    TOOL_FAILURE = "tool-failure"


class Prediction(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"
    NONE = "none"


@dataclass
class MetricResult:
    """单项指标的完整输出, 对应 PRO-12 §09 的输出契约。"""

    metric: str
    score: float | None
    threshold: float
    coverage: Coverage
    prediction: Prediction = Prediction.NONE
    confidence: float | None = None
    tools: list[str] = field(default_factory=list)
    raw_measurements: dict[str, Any] = field(default_factory=dict)
    sub_scores: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None
    repair_hint: str | None = None
    provisional_params: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "prediction": self.prediction.value,
            "threshold": self.threshold,
            "confidence": self.confidence,
            "coverage": self.coverage.value,
            "tools": self.tools,
            "raw_measurements": self.raw_measurements,
            "sub_scores": self.sub_scores,
            "evidence": self.evidence,
            "failure_reason": self.failure_reason,
            "repair_hint": self.repair_hint,
            "provisional_params": self.provisional_params,
            "diagnostics": self.diagnostics,
        }

    @property
    def counts_in_aggregate(self) -> bool:
        """N/A 与工具故障不进聚合分母 (PRO-12 §07)。"""
        return self.score is not None and self.coverage not in (
            Coverage.NOT_APPLICABLE,
            Coverage.TOOL_FAILURE,
            Coverage.UNSUPPORTED,
        )


class ToolFailure(Exception):
    """仿真器/几何工具故障。捕获后转成 Coverage.TOOL_FAILURE, 绝不返回 0.0。"""
