"""Render records from eight views and obtain raw Codex A4 signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts.extract_a4_a5 import read_prompt
from .frontends.a4_vlm import measure_with_codex
from .frontends.pipeline import _load_generated_model, find_record_model
from .frontends.render_views import render_eight_views


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--extensions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path, required=True)
    parser.add_argument("--record-id", action="append", required=True)
    parser.add_argument("--model")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for record_id in args.record_id:
        target = args.output_dir / f"{record_id}.json"
        if target.exists() and not args.overwrite:
            continue
        extension = json.loads(
            (args.extensions / f"{record_id}.json").read_text(encoding="utf-8")
        )
        model_path = find_record_model(args.data_dir, record_id)
        module = _load_generated_model(model_path)
        image_dir = args.render_dir / record_id
        images = render_eight_views(module.object_model, image_dir)
        signals = measure_with_codex(
            read_prompt(args.data_dir, record_id),
            extension.get("appearance_claims") or [],
            images,
            model=args.model,
        )
        signals.update(record_id=record_id, render_paths=[str(path) for path in images])
        target.write_text(json.dumps(signals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
