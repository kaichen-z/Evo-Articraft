from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Coverage(str, Enum):
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
        return self.score is not None and self.coverage not in (
            Coverage.NOT_APPLICABLE,
            Coverage.UNSUPPORTED,
            Coverage.TOOL_FAILURE,
        )


class ToolFailure(Exception):
    """输入或测量工具故障，不能解释为资产失败。"""
