#!/usr/bin/env python3
"""Run the P2 geometry verifier over the zero-cad-10samples-gf testbed.

    env_mujoco/bin/python code/p2-kai/run_eval.py [--data DIR] [--out DIR]

Reads per variant: model.stl + the uuid's contract.yaml. Never reads the GT mesh
or injection.json while scoring; injection.json is opened afterwards only to
attach the ground-truth label for the report.
"""
import argparse, json, os, sys, time
import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure, geo, gf, bindings

DATA = "/Users/kai/Storage/Daily/Claude/0_Code/mechanism/data/zero-cad-10samples-gf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def score_variant(stl, contract, bind):
    g = geo.Geo(measure.load(stl))
    g1, e1 = gf.gf1(contract, g)
    g2, e2 = gf.gf2(contract, g, bind)
    g3, e3 = gf.gf3(contract, g)
    g4, e4 = gf.gf4(contract, g, bind)
    meas = dict(g.b)
    meas.update(wall=g.wall(0.5), ring=list(g.ring(0.75)),
                n_cavities_z=len(g.cavities(2)), n_cavities_x=len(g.cavities(0)))
    return dict(GF1=g1, GF2=g2, GF3=g3, GF4=g4), dict(GF1=e1, GF2=e2, GF3=e3, GF4=e4), meas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    index = json.load(open(os.path.join(a.data, "index.json")))

    contracts = {}
    records = []
    t0 = time.time()
    for e in index["entries"]:
        uid, variant = e["uuid"], e["variant"]
        if uid not in contracts:
            contracts[uid] = yaml.safe_load(open(os.path.join(a.data, uid, "contract.yaml")))
        stl = os.path.join(a.data, e["path"], "model.stl")
        prof, ev, meas = score_variant(stl, contracts[uid], bindings.BIND[uid])
        label = json.load(open(os.path.join(a.data, e["path"], "injection.json")))  # label only
        records.append(dict(uuid=uid, variant=variant, path=e["path"],
                            gt_error_type=label.get("error_type"),
                            gt_dimension=label.get("expect_dimension"),
                            gt_magnitude=label.get("magnitude"),
                            generic_fallback=bool(label.get("injection", {}).get("generic", False)),
                            volume_delta_frac=label.get("volume_delta_frac"),
                            profile=prof, evidence=ev,
                            measurements=meas))
        print(f"{uid[:8]} {variant:<18} " +
              " ".join(f"{d}={prof[d]:.3f}" if prof[d] is not None else f"{d}=NA" for d in ("GF1","GF2","GF3","GF4")))

    by_gt = {r["uuid"]: r["profile"] for r in records if r["variant"] == "gt"}
    for r in records:
        r["detection"] = gf.detect(r["profile"], by_gt[r["uuid"]], r["measurements"]["n_components"])

    out = dict(protocol="task-13_08-19 / P2 task-2_08-16-p2", data=a.data,
               thresholds=dict(GF1_W_CONN=gf.GF1_W_CONN, SYM_OK=gf.SYM_OK,
                               EVEN_CV=gf.EVEN_CV, DETECT_DELTA=gf.DETECT_DELTA),
               n_variants=len(records), seconds=round(time.time() - t0, 1), records=records)
    json.dump(out, open(os.path.join(a.out, "results.json"), "w"), indent=1)

    with open(os.path.join(a.out, "scores.csv"), "w") as fh:
        fh.write("uuid,variant,gt_error_type,gt_dimension,GF1,GF2,GF3,GF4,dGF1,dGF2,dGF3,dGF4,detected_dim,detected_defect\n")
        for r in records:
            p, d = r["profile"], r["detection"]["deltas"]
            f = lambda v: "" if v is None else f"{v:.4f}"
            fh.write(",".join([r["uuid"], r["variant"], str(r["gt_error_type"]), str(r["gt_dimension"]),
                               f(p["GF1"]), f(p["GF2"]), f(p["GF3"]), f(p["GF4"]),
                               f(d["GF1"]), f(d["GF2"]), f(d["GF3"]), f(d["GF4"]),
                               str(r["detection"]["dimension"]), '"' + r["detection"]["defect"] + '"',
                               str(r["detection"]["gated_dimension"])]) + "\n")
    print(f"\n{len(records)} variants in {out['seconds']}s -> {a.out}/results.json + scores.csv")


if __name__ == "__main__":
    main()
