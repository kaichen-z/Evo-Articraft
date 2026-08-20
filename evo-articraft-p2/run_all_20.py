"""Run the full patched pipeline (bug-fixed + prob_vs_chance + dictionary + shape)
across all 20 of xuge's cases, using the URDF caches materialized locally.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
import p2.spec as spec
spec.ARTICRAFT_ROOT = Path("/tmp/articraft_root_link")

import runner

CASES_PATH = Path("cases_20.json")


def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    runner.OUT.mkdir(parents=True, exist_ok=True)
    runner.SPECS.mkdir(parents=True, exist_ok=True)

    results = []
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            r = runner.process_case(case)
            results.append(r)
            print(f"[{i}/20] OK  {case['record_id']}  ({time.time()-t0:.2f}s)")
        except Exception as exc:
            print(f"[{i}/20] FAIL {case['record_id']}: {type(exc).__name__}: {exc}")

    print(f"\n{len(results)}/{len(cases)} cases rendered, running CLIP scoring...")
    runner.run_clip(results)

    payload = {
        "protocol": {
            "render": {"size": runner.consts.RENDER_SIZE, "azimuths": runner.consts.AZIMUTHS,
                        "elevation": runner.consts.ELEVATION, "dist_factor": runner.consts.DIST_FACTOR},
            "encoder": {"arch": runner.consts.CLIP_ARCH, "ckpt": runner.consts.CLIP_CKPT},
        },
        "results": results,
    }
    out_path = runner.OUT / "results_20_patched.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")

    print(f"\n{'record':45s} {'GF1prob':>8s} {'rank':>5s} {'GF2prob':>8s} {'vsChance':>9s} {'GF3':>6s} {'GF4':>6s} {'shape':>14s}")
    for r in results:
        gf1, gf2, gf3, gf4, shape = r.get("gf1", {}), r.get("gf2", {}), r.get("gf3", {}), r.get("gf4", {}), r.get("shape") or {}
        fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else "  n/a"
        print(f"{r['record_id'][:45]:45s} "
              f"{fmt(gf1.get('softmax_prob_vs_19_distractors'))} "
              f"{str(gf1.get('rank_among_20','')):>5s} "
              f"{fmt(gf2.get('macro_prob'))} "
              f"{fmt(gf2.get('macro_prob_vs_chance')):>9s} "
              f"{fmt(gf3.get('score')):>6s} "
              f"{fmt(gf4.get('score')):>6s} "
              f"{shape.get('shape_best_guess','')[:14]:>14s}")


if __name__ == "__main__":
    main()
