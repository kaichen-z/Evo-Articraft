"""Run A1-A6 on local Articraft records and emit one JSONL record per asset."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from .frontends.pipeline import find_record_model, run_asset
from .report.serialize import build_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--extensions", type=Path)
    parser.add_argument("--a4-signals", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-a6", action="store_true", help="skip generated-code/mesh checks")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    # Generated model.py files may change process cwd while importing CAD
    # helpers. Resolve every external path once so one asset cannot corrupt all
    # following records in the batch.
    args.data_dir = args.data_dir.resolve()
    args.annotations = args.annotations.resolve()
    args.contracts = args.contracts.resolve()
    args.extensions = args.extensions.resolve() if args.extensions else None
    args.a4_signals = args.a4_signals.resolve() if args.a4_signals else None
    args.output = args.output.resolve()

    with args.annotations.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if args.limit:
        rows = rows[: args.limit]

    done: set[str] = set()
    if args.resume and args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            try:
                previous = json.loads(line)
                # Missing data can be downloaded between runs, and a transient
                # execution error can be fixed. Only a completed row is safe to
                # skip when resuming.
                if previous.get("status") == "ok":
                    done.add(previous["record_id"])
            except Exception:
                pass
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.resume else "w"
    counts = {"ok": 0, "missing_model": 0, "error": 0}
    started = time.time()
    with args.output.open(mode, encoding="utf-8") as output:
        for index, row in enumerate(rows, 1):
            record_id = (row.get("Record ID") or "").strip()
            if not record_id or record_id in done:
                continue
            entry = {"record_id": record_id, "category": row.get("Category", "")}
            try:
                model_path = find_record_model(args.data_dir, record_id)
            except FileNotFoundError:
                entry["status"] = "missing_model"
                counts["missing_model"] += 1
            else:
                contract_path = args.contracts / f"{record_id}.json"
                extension_path = args.extensions / f"{record_id}.json" if args.extensions else None
                a4_signals_path = args.a4_signals / f"{record_id}.json" if args.a4_signals else None
                try:
                    results = run_asset(
                        model_path,
                        contract_path=contract_path if contract_path.exists() else None,
                        extension_path=extension_path,
                        a4_signals_path=a4_signals_path,
                        include_a6=not args.no_a6,
                    )
                    entry.update(
                        status="ok",
                        model_relpath=str(model_path.relative_to(args.data_dir)),
                        has_contract=contract_path.exists(),
                        report=build_report(results),
                    )
                    counts["ok"] += 1
                except Exception as exc:
                    entry.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500])
                    counts["error"] += 1
            output.write(json.dumps(entry, ensure_ascii=False) + "\n")
            output.flush()
            if index % 10 == 0:
                elapsed = time.time() - started
                print(f"[{index}/{len(rows)}] {counts}, {elapsed:.1f}s", file=sys.stderr, flush=True)
    print(json.dumps({"rows": len(rows), **counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
