"""Obtain raw A4 evidence from eight renders using the local Codex model."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["realism_probability", "cross_view_consistency", "low_scoring_views", "evidence"],
    "properties": {
        "realism_probability": {"type": "number", "minimum": 0, "maximum": 1},
        "cross_view_consistency": {"type": "number", "minimum": 0, "maximum": 1},
        "low_scoring_views": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 7}},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
}

INSTRUCTION = """\
You are the measurement frontend for metric A4 of an articulated-object design
benchmark. The attached eight images are fixed views of the SAME generated 3D
asset, in view order 0 through 7. Judge the asset, not image aesthetics.

Use the Prompt and its explicit appearance claims. Return JSON only:
- realism_probability: probability in [0,1] that shape, dimensions and
  proportions are plausible for the described manufactured object;
- cross_view_consistency: in [0,1], whether all views describe one coherent
  solid construction without view-specific implausible geometry;
- low_scoring_views: view indices that expose defects;
- evidence: short visible observations tied to parts/proportions.

Do not penalize unspecified cosmetic details. Do not assume a unique reference
design. This is a raw visual measurement, not a final pass/fail decision.
"""


def measure_with_codex(
    prompt: str, claims: list[dict[str, Any]], images: list[Path | str], *,
    model: str | None = None, timeout: float = 300.0,
) -> dict[str, Any]:
    if len(images) != 8:
        raise ValueError(f"A4 requires exactly eight views, got {len(images)}")
    with tempfile.TemporaryDirectory(prefix="a4-vlm-") as temporary:
        schema_path = Path(temporary) / "schema.json"
        answer_path = Path(temporary) / "answer.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        command = ["codex", "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check"]
        if model:
            command.extend(["--model", model])
        for image in images:
            command.extend(["--image", str(Path(image).resolve())])
        command.extend(["--output-schema", str(schema_path), "--output-last-message", str(answer_path), "-"])
        request = (
            f"{INSTRUCTION}\n\nPrompt:\n{prompt}\n\n"
            f"Explicit appearance claims:\n{json.dumps(claims, ensure_ascii=False)}"
        )
        completed = subprocess.run(
            command, input=request, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
        if completed.returncode != 0 or not answer_path.exists():
            detail = (completed.stderr or completed.stdout)[-1000:]
            raise RuntimeError(f"Codex A4 measurement failed ({completed.returncode}): {detail}")
        result = json.loads(answer_path.read_text(encoding="utf-8"))
    return {
        "vlm_realism_probability": float(result["realism_probability"]),
        "cross_view_consistency": float(result["cross_view_consistency"]),
        "low_scoring_views": list(result["low_scoring_views"]),
        "a4_vlm_evidence": list(result["evidence"]),
        # Raw Codex probabilities are not declared calibrated until a held-out
        # calibration procedure writes a calibration artifact.
        "vlm_calibrated": False,
    }
