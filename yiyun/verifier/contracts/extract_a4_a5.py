"""Extract frozen A4/A5 requirements from prompts with an offline LLM call.

The LLM translates the prompt into auditable requirements.  It never sees the
generated asset and never scores it.  Explicit requirements must quote an exact
substring of the prompt; inferred common sense is advisory and cannot deduct
points.  This follows Wanglin's contract-extraction protocol while extending it
with appearance and spatial-relation fields needed by A4/A5.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..frontends.static_asset import read_prompt

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.6-flash"
KEY_NAME = "GEMINI_API_KEY"
SCHEMA_PATH = Path(__file__).with_name("a4_a5_output_schema.json")

APPEARANCE_TYPES = frozenset(
    {"shape", "proportion", "relative_size", "visibility", "style", "detail", "scale"}
)
RELATIONS = frozenset(
    {
        "above", "below", "left_of", "right_of", "in_front_of", "behind",
        "inside", "contains", "between", "at_end_of", "centered_on",
        "aligned_with", "parallel_to", "perpendicular_to", "adjacent_to",
        "attached_to", "surrounds", "overlaps", "spaced_around",
    }
)
CHECK_MODES = frozenset({"geometry", "vlm", "hybrid"})
INTERFACE_TYPES = frozenset(
    {"hinge", "pivot", "axle", "bearing", "bushing", "rail", "guide", "slot", "collar", "bracket", "mount", "contact"}
)

INSTRUCTION = """\
You read a text description of an articulated 3D object and translate only its
explicit A3 functional interfaces, A4 appearance requirements, and A5
spatial/assembly relations into JSON.
You do not design, judge, score, or inspect a generated asset.

Return JSON only, with this shape:

{
  "required_interfaces": [
    {"id":"lid_side_hinge", "interface_type":"hinge", "moving_part":"lid",
     "support_parts":["body"], "description":"lid rotates on a side hinge",
     "source":"prompt", "confidence":1.0, "evidence_text":"VERBATIM QUOTE"}
  ],
  "appearance_claims": [
    {"id":"...", "subject":"...", "claim_type":"proportion",
     "description":"...", "comparison_target":"...", "check_mode":"geometry",
     "source":"prompt", "confidence":1.0, "evidence_text":"VERBATIM QUOTE"}
  ],
  "spatial_relations": [
    {"id":"...", "subject":"...", "relation":"between",
     "objects":["left bracket","right bracket"], "frame":"object",
     "check_mode":"geometry", "source":"prompt", "confidence":1.0,
     "evidence_text":"VERBATIM QUOTE"}
  ],
  "advisory_inferences": [
    {"kind":"appearance|spatial", "description":"...", "confidence":0.5}
  ]
}

Rules:
1. evidence_text must be copied VERBATIM from the description and be an exact
   substring. Never paraphrase evidence. If there is no exact quote, omit the
   scored requirement.
2. Only prompt-explicit requirements enter required_interfaces,
   appearance_claims, or spatial_relations.
   Put useful category common sense in advisory_inferences; it is never scored.
3. Do not invent numeric thresholds. Preserve qualitative words such as small,
   long, compact, evenly spaced, realistic, or refined in description.
4. claim_type is one of shape, proportion, relative_size, visibility, style,
   detail, scale. Use geometry for directly measurable ratios/sizes, vlm for
   visual semantics/style/realism, and hybrid when both are useful.
5. relation is one of above, below, left_of, right_of, in_front_of, behind,
   inside, contains, between, at_end_of, centered_on, aligned_with, parallel_to,
   perpendicular_to, adjacent_to, attached_to, surrounds, overlaps,
   spaced_around. If the relation cannot be represented faithfully, omit it or
   record it as an advisory inference.
6. objects is always a JSON list. For between it should contain the two boundary
   objects; otherwise it usually contains one reference object.
7. frame is "world" only for explicit world directions such as vertical or top;
   otherwise use "object". Do not infer camera-relative left/right.
8. Make stable snake_case ids. Do not duplicate the same requirement.
9. Empty lists are valid. A vague product name alone does not authorize detailed
   hard requirements.
10. required_interfaces contains only physical support/guide interfaces that the
    Prompt explicitly names (hinge, pivot, axle, bearing/bushing, rail, guide,
    slot, collar, bracket, mount, or contact). A joint verb by itself does not
    authorize inventing an unmentioned bearing or rail. support_parts may be
    empty when the Prompt does not name the supporting part.
"""


class ExtractionError(RuntimeError):
    """The model call or validation failed; this is not an asset failure."""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def read_api_key(env_file: Path | str | None = None) -> str:
    value = os.environ.get(KEY_NAME, "").strip()
    if value:
        return value
    if env_file:
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            name, separator, raw = line.partition("=")
            if separator and name.strip() == KEY_NAME:
                return raw.strip().strip("\"'")
    raise ExtractionError(f"{KEY_NAME} is not set")


def build_request(prompt: str, *, model: str, api_key: str) -> urllib.request.Request:
    body = {
        "contents": [{"parts": [{"text": f"{INSTRUCTION}\n\nDescription:\n{prompt}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0},
    }
    return urllib.request.Request(
        ENDPOINT.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )


def call_model(prompt: str, *, model: str, api_key: str, timeout: float = 60.0) -> str:
    try:
        with urllib.request.urlopen(
            build_request(prompt, model=model, api_key=api_key), timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        raise ExtractionError(f"HTTP {error.code} from {model}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise ExtractionError(f"could not reach {model}: {error}") from None
    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise ExtractionError(f"unexpected response shape: {json.dumps(payload)[:400]}") from None


def call_codex(prompt: str, *, model: str | None = None, timeout: float = 180.0) -> str:
    """Use the locally authenticated Codex CLI; no API key is read or stored."""
    with tempfile.TemporaryDirectory(prefix="a4-a5-codex-") as temp_dir:
        output = Path(temp_dir) / "answer.json"
        command = [
            "codex", "exec", "--ephemeral", "--sandbox", "read-only",
            "--skip-git-repo-check", "--output-schema", str(SCHEMA_PATH),
            "--output-last-message", str(output), "-",
        ]
        if model:
            command[2:2] = ["--model", model]
        try:
            completed = subprocess.run(
                command,
                input=f"{INSTRUCTION}\n\nDescription:\n{prompt}",
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExtractionError(f"Codex invocation failed: {error}") from None
        if completed.returncode != 0 or not output.exists():
            detail = (completed.stderr or completed.stdout)[-800:]
            raise ExtractionError(f"Codex exited {completed.returncode}: {detail}")
        return output.read_text(encoding="utf-8")


def extension_from_answer(
    answer: str | Mapping[str, Any], *, record_id: str, prompt: str, extractor: str
) -> dict[str, Any]:
    if isinstance(answer, str):
        try:
            payload = json.loads(answer)
        except json.JSONDecodeError as error:
            raise ExtractionError(f"{record_id}: answer is not JSON: {error}") from None
    else:
        payload = dict(answer)
    if not isinstance(payload, Mapping):
        raise ExtractionError(f"{record_id}: answer is not a JSON object")

    interfaces = [_interface(item, prompt, record_id) for item in payload.get("required_interfaces", ())]
    claims = [_appearance(item, prompt, record_id) for item in payload.get("appearance_claims", ())]
    relations = [_relation(item, prompt, record_id) for item in payload.get("spatial_relations", ())]
    advisories = list(payload.get("advisory_inferences", ()))
    return {
        "version": "1",
        "record_id": record_id,
        "extractor": extractor,
        "required_interfaces": interfaces,
        "appearance_claims": claims,
        "spatial_relations": relations,
        "advisory_inferences": advisories,
    }


def _common(item: Mapping[str, Any], prompt: str, record_id: str) -> dict[str, Any]:
    evidence = str(item.get("evidence_text", ""))
    if not evidence or _normalise(evidence) not in _normalise(prompt):
        raise ExtractionError(f"{record_id}: evidence is not an exact prompt substring: {evidence!r}")
    if item.get("source") != "prompt":
        raise ExtractionError(f"{record_id}: scored requirement must use source=prompt")
    confidence = float(item.get("confidence", 1.0))
    if not 0.0 <= confidence <= 1.0:
        raise ExtractionError(f"{record_id}: confidence outside [0,1]")
    identifier = str(item.get("id", "")).strip()
    subject = str(item.get("subject", "")).strip()
    if not identifier or not subject:
        raise ExtractionError(f"{record_id}: requirement needs id and subject")
    return {
        "id": identifier,
        "subject": subject,
        "source": "prompt",
        "confidence": confidence,
        "evidence_text": evidence,
    }


def _appearance(item: Mapping[str, Any], prompt: str, record_id: str) -> dict[str, Any]:
    result = _common(item, prompt, record_id)
    claim_type = str(item.get("claim_type", ""))
    mode = str(item.get("check_mode", ""))
    if claim_type not in APPEARANCE_TYPES or mode not in CHECK_MODES:
        raise ExtractionError(f"{record_id}: invalid appearance type/mode")
    result.update(
        claim_type=claim_type,
        description=str(item.get("description", "")).strip(),
        comparison_target=str(item.get("comparison_target", "") or "").strip(),
        check_mode=mode,
    )
    return result


def _interface(item: Mapping[str, Any], prompt: str, record_id: str) -> dict[str, Any]:
    evidence = str(item.get("evidence_text", ""))
    if not evidence or _normalise(evidence) not in _normalise(prompt):
        raise ExtractionError(f"{record_id}: interface evidence is not in prompt: {evidence!r}")
    if item.get("source") != "prompt":
        raise ExtractionError(f"{record_id}: scored interface must use source=prompt")
    interface_type = str(item.get("interface_type", ""))
    if interface_type not in INTERFACE_TYPES:
        raise ExtractionError(f"{record_id}: invalid interface type: {interface_type!r}")
    identifier = str(item.get("id", "")).strip()
    moving_part = str(item.get("moving_part", "")).strip()
    supports = item.get("support_parts", ())
    if not identifier or not moving_part or not isinstance(supports, list):
        raise ExtractionError(f"{record_id}: interface needs id, moving_part and support_parts")
    return {
        "id": identifier,
        "interface_type": interface_type,
        "moving_part": moving_part,
        "support_parts": [str(value).strip() for value in supports if str(value).strip()],
        "description": str(item.get("description", "")).strip(),
        "source": "prompt",
        "confidence": float(item.get("confidence", 1.0)),
        "evidence_text": evidence,
    }


def _relation(item: Mapping[str, Any], prompt: str, record_id: str) -> dict[str, Any]:
    result = _common(item, prompt, record_id)
    relation = str(item.get("relation", ""))
    mode = str(item.get("check_mode", ""))
    objects = item.get("objects", ())
    if relation not in RELATIONS or mode not in CHECK_MODES:
        raise ExtractionError(f"{record_id}: invalid relation/mode")
    if not isinstance(objects, list) or not objects or not all(str(value).strip() for value in objects):
        raise ExtractionError(f"{record_id}: spatial relation needs a non-empty objects list")
    if relation == "between" and len(objects) != 2:
        raise ExtractionError(f"{record_id}: between requires exactly two objects")
    result.update(
        relation=relation,
        objects=[str(value).strip() for value in objects],
        frame=str(item.get("frame", "object")),
        check_mode=mode,
    )
    return result


def extract(record_id: str, prompt: str, *, api_key: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    answer = call_model(prompt, model=model, api_key=api_key)
    return extension_from_answer(answer, record_id=record_id, prompt=prompt, extractor=model)


def extract_with_codex(
    record_id: str, prompt: str, *, model: str | None = None
) -> dict[str, Any]:
    answer = call_codex(prompt, model=model)
    extractor = f"codex:{model or 'configured-default'}"
    return extension_from_answer(answer, record_id=record_id, prompt=prompt, extractor=extractor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--record-id", action="append", default=[])
    parser.add_argument("--annotations", type=Path,
                        help="CSV export; extract every Record ID in file order")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--provider", choices=("codex", "gemini"), default="codex")
    parser.add_argument("--model", help="provider model; omitted uses provider default")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    key = read_api_key(args.env_file) if args.provider == "gemini" else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    record_ids = list(args.record_id)
    if args.annotations:
        with args.annotations.open(encoding="utf-8-sig", newline="") as handle:
            record_ids.extend(
                row["Record ID"].strip() for row in csv.DictReader(handle)
                if row.get("Record ID", "").strip()
            )
    record_ids = list(dict.fromkeys(record_ids))
    if not record_ids:
        parser.error("provide --record-id or --annotations")
    for record_id in record_ids:
        target = args.output_dir / f"{record_id}.json"
        if target.exists() and not args.overwrite:
            continue
        prompt = read_prompt(args.data_dir, record_id)
        if args.provider == "codex":
            result = extract_with_codex(record_id, prompt, model=args.model)
        else:
            result = extract(
                record_id, prompt, api_key=key or "", model=args.model or DEFAULT_MODEL
            )
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
