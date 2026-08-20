"""P2 Geometry Fidelity 端到端 runner（P0/P1 接口对齐版）。

数据流（与正式流水线同构，替身可整体替换）:
    P0 契约   → specs/<rid>.json         (真格式; 今天由 spec.draft_contract 起草)
    P1 绑定   → PartBinding              (今天由 URDF link 起草替身)
    P2 本体   → 渲染 + GF1..GF4 → out/results.json / summary.csv

用法:  python runner.py [--limit N] [--no-clip]
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import time
import traceback

import numpy as np

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from p2 import consts
from p2.binding import PartBinding
from p2.gf34 import gf3_score, gf4_score
from p2.mj_scene import Scene
from p2.render import RenderProtocol
from p2.spec import ARTICRAFT_ROOT, build_part_texts, build_t_global, load_or_draft
from p2.urdf_info import parse_urdf

OUT = ROOT / "out"
SPECS = ROOT / "specs"


def process_case(case: dict) -> dict:
    """加载 → 契约 → 绑定 → 渲染 → GF3/GF4；返回结果骨架与待编码图像。"""
    rid = case["record_id"]
    urdf = ARTICRAFT_ROOT / case["urdf_path"]

    info = parse_urdf(urdf)
    contract = load_or_draft(SPECS, rid, case["category"], info)

    scene = Scene.load(urdf, urdf_info=info)
    binding = PartBinding.from_urdf_standin(scene, info)

    # ---- 评分文本 (只从 P0 对应字段构造, overall_description 不进评分) ----
    t_global = build_t_global(contract)
    part_texts_by_id = build_part_texts(contract)

    # ---- 渲染 ----
    proto = RenderProtocol(scene)
    render_dir = OUT / "renders" / rid
    global_views = proto.global_views(save_dir=render_dir)

    part_views: dict[str, dict] = {}
    part_texts: dict[str, str] = {}
    parts_unmeasurable: list[str] = []
    for iid, inst in binding.instances.items():
        text = part_texts_by_id.get(inst.part_id)
        if not binding.renderable(inst) or text is None:
            parts_unmeasurable.append(iid)
            continue
        views = proto.part_views(iid, save_dir=render_dir / "parts")
        if views is None:
            parts_unmeasurable.append(iid)
        else:
            part_views[iid] = views
            part_texts[iid] = text
    proto.close()

    # ---- GF3 / GF4 ----
    gf3 = gf3_score(scene, binding, contract.get("part_relations", []))
    gf4 = gf4_score(scene, binding, contract.get("proportion_claims", []))

    return {
        "record_id": rid,
        "category": case["category"],
        "label": case.get("label", ""),
        "spec": contract,
        "t_global": t_global,
        "d_bbox": scene.d_bbox,
        "gf3": gf3,
        "gf4": gf4,
        "parts_unmeasurable": parts_unmeasurable,
        "_global_views": global_views,
        "_part_views": part_views,
        "_part_texts": part_texts,
    }


def run_clip(results: list[dict]) -> None:
    """GF1 + GF2: 批量编码, 就地写入 results。"""
    from p2.encoder import ClipEncoder
    enc = ClipEncoder()

    # ---------- GF1 ----------
    ok = [r for r in results if "_global_views" in r]
    txt_f = enc.encode_texts([r["t_global"] for r in ok])

    img_means = []
    for r in ok:
        views = r["_global_views"]
        azs = sorted(views.keys())
        feats = enc.encode_images([views[a] for a in azs])
        per_view = feats @ txt_f[len(img_means)]
        r["gf1"] = {
            "text": r["t_global"],
            "per_view": {f"az{int(a):03d}": float(s) for a, s in zip(azs, per_view)},
            "mean_cos": float(per_view.mean()),
            "min_cos": float(per_view.min()),
        }
        m = feats.mean(axis=0)
        img_means.append(m / (np.linalg.norm(m) + 1e-12))

    sims = np.stack(img_means) @ txt_f.T
    logits = enc.logit_scale * sims
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = probs / probs.sum(axis=1, keepdims=True)
    for i, r in enumerate(ok):
        r["gf1"]["softmax_prob_vs_19_distractors"] = float(probs[i, i])
        r["gf1"]["rank_among_20"] = int((sims[i] > sims[i, i]).sum()) + 1

    # ---------- GF2 ----------
    for r in ok:
        part_views = r.pop("_part_views")
        part_texts = r.pop("_part_texts")
        r.pop("_global_views")
        if not part_views:
            r["gf2"] = {"macro_mean_cos": None, "parts": {}, "note": "no measurable parts"}
            continue

        links = sorted(part_views.keys())
        ptxt_f = enc.encode_texts([part_texts[l] for l in links])

        per_part = {}
        pf_means = []
        for li, link in enumerate(links):
            views = part_views[link]
            azs = sorted(views.keys())
            feats = enc.encode_images([views[a] for a in azs])
            cos = feats @ ptxt_f[li]
            per_part[link] = {"text": part_texts[link],
                              "mean_cos": float(cos.mean()), "min_cos": float(cos.min())}
            m = feats.mean(axis=0)
            pf_means.append(m / (np.linalg.norm(m) + 1e-12))

        pf = np.stack(pf_means)
        psims = pf @ ptxt_f.T
        plogits = enc.logit_scale * psims
        pprobs = np.exp(plogits - plogits.max(axis=1, keepdims=True))
        pprobs = pprobs / pprobs.sum(axis=1, keepdims=True)
        for li, link in enumerate(links):
            per_part[link]["prob_vs_sibling_parts"] = float(pprobs[li, li])
            per_part[link]["best_matching_part"] = links[int(np.argmax(psims[li]))]

        r["gf2"] = {
            "macro_mean_cos": float(np.mean([p["mean_cos"] for p in per_part.values()])),
            "macro_prob": float(np.mean([p["prob_vs_sibling_parts"] for p in per_part.values()])),
            "n_parts_scored": len(links),
            "parts": per_part,
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-clip", action="store_true")
    args = ap.parse_args()

    cases = json.loads((ROOT / "cases_20.json").read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]

    OUT.mkdir(exist_ok=True)
    results: list[dict] = []
    t0 = time.time()

    for i, case in enumerate(cases, 1):
        rid = case["record_id"]
        try:
            r = process_case(case)
            g3, g4 = r["gf3"]["score"], r["gf4"]["score"]
            g3s = f"{g3:.3f}" if g3 is not None else "n/a"
            g4s = f"{g4:.3f}" if g4 is not None else "n/a"
            print(f"[{i:2d}/{len(cases)}] {case.get('label',''):<12} GF3={g3s:<6} GF4={g4s:<6} "
                  f"parts_ok={len(r['_part_views'])} unmeas={len(r['parts_unmeasurable'])}  {rid[:44]}")
            results.append(r)
        except Exception as e:
            print(f"[{i:2d}/{len(cases)}] TOOL-FAILURE {rid[:50]}: {e}")
            traceback.print_exc()
            results.append({
                "record_id": rid, "category": case["category"],
                "label": case.get("label", ""), "coverage": "tool-failure",
                "error": str(e),
            })

    if not args.no_clip:
        print("\n编码图文 (GF1/GF2)...")
        run_clip(results)
    else:
        for r in results:
            r.pop("_global_views", None)
            r.pop("_part_views", None)
            r.pop("_part_texts", None)

    # ---------- 落盘 ----------
    payload = {
        "protocol": {
            "render": {"size": consts.RENDER_SIZE, "azimuths": consts.AZIMUTHS,
                        "elevation": consts.ELEVATION, "dist_factor": consts.DIST_FACTOR},
            "encoder": {"arch": consts.CLIP_ARCH, "ckpt": consts.CLIP_CKPT},
            "provisional_params": {k: getattr(consts, k) for k in consts.PROVISIONAL_PARAMS},
        },
        "results": results,
    }
    (OUT / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["record_id", "label", "GF1_mean_cos", "GF1_prob", "GF1_rank",
                    "GF2_macro_cos", "GF2_macro_prob", "GF3", "GF4",
                    "gf3_claims", "gf3_unmeas", "gf4_pairs", "coverage"])
        for r in results:
            gf1, gf2 = r.get("gf1", {}), r.get("gf2", {})
            gf3, gf4 = r.get("gf3", {}), r.get("gf4", {})
            fmt = lambda v: (f"{v:.4f}" if isinstance(v, float) else ("" if v is None else v))
            w.writerow([
                r["record_id"], r.get("label", ""),
                fmt(gf1.get("mean_cos")), fmt(gf1.get("softmax_prob_vs_19_distractors")),
                gf1.get("rank_among_20", ""),
                fmt(gf2.get("macro_mean_cos")), fmt(gf2.get("macro_prob")),
                fmt(gf3.get("score")), fmt(gf4.get("score")),
                gf3.get("n_claims", ""), gf3.get("n_unmeasurable", ""),
                gf4.get("n_pairs", ""), r.get("coverage", "ok"),
            ])

    print(f"\n完成: {len(results)} 案例, {time.time()-t0:.0f}s")
    print(f"结果: {OUT/'results.json'}\n汇总: {OUT/'summary.csv'}")


if __name__ == "__main__":
    main()
