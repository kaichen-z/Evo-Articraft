from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
import p2.spec as spec
spec.ARTICRAFT_ROOT = Path("/tmp/articraft_root_link")

import runner


def main() -> None:
    cases = json.loads(Path("cases_new16.json").read_text())
    runner.OUT.mkdir(parents=True, exist_ok=True)
    runner.SPECS.mkdir(parents=True, exist_ok=True)

    results = []
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            r = runner.process_case(case)
            r["rating"] = case["rating"]
            results.append(r)
            print(f"[{i}/16] OK  {case['record_id']}  ({time.time()-t0:.2f}s)")
        except Exception as exc:
            print(f"[{i}/16] FAIL {case['record_id']}: {type(exc).__name__}: {exc}")

    print(f"\n{len(results)}/{len(cases)} rendered, scoring...")
    runner.run_clip(results)

    out_path = runner.OUT / "results_new16.json"
    out_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out_path)


if __name__ == "__main__":
    main()
