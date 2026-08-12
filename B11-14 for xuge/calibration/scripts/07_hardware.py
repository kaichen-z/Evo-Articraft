"""假设: 人看的是"关节处有没有专门的连接硬件"。

真合页有轴筒/销/支架等额外几何; 假合页只是两块板对在一起。
这体现为关节邻域的几何数量与来源, 而不是间隙距离。纯位置计算, 不查距离。
"""
import csv, json, pathlib, sys
from statistics import median
sys.path.insert(0, r"D:\projects\articraft-verifier")

import mujoco
import numpy as np

from verifier.consts import DEFAULT
from verifier.sim.loader import body_subtree_geoms, joint_name, load_urdf, movable_joints
from verifier.types import ToolFailure

CACHE = pathlib.Path(r"D:\articraft_project\articraft-data\cache\record_materialization")
HERE = pathlib.Path(__file__).parent
BASE = pathlib.Path(r"D:\articraft_project")
CSV_PATH = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"
B12 = "活动零件是否具有可信的实体连接或支撑结构"
SRC_NEW = {"新版原始标注（新增案例）", "新版原始标注（覆盖旧版前350条）"}


def auc_high(bad, good):
    if not bad or not good:
        return None
    gt = ties = 0
    for x in bad:
        for y in good:
            if x > y:
                gt += 1
            elif x == y:
                ties += 1
    return (gt + 0.5 * ties) / (len(bad) * len(good))


def dist_to_axis(p, anchor, axis):
    v = p - anchor
    return float(np.linalg.norm(v - np.dot(v, axis) * axis))


def feats(rid):
    try:
        loaded = load_urdf(CACHE / rid / "model.urdf", DEFAULT)
    except ToolFailure:
        return None
    m, d = loaded.model, loaded.data
    mujoco.mj_forward(m, d)
    D = loaded.d_bbox or 1.0
    out = []
    for j in movable_joints(m):
        child = int(m.jnt_bodyid[j])
        parent = int(m.body_parentid[child])
        sub = set(body_subtree_geoms(m, child))
        anchor = np.asarray(d.xanchor[j], dtype=float)
        axis = np.asarray(d.xaxis[j], dtype=float)
        n = np.linalg.norm(axis)
        axis = axis / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])

        # 活动连杆自身尺度
        subg = list(sub)
        L = 1.0
        if subg:
            pos = d.geom_xpos[subg]
            r = m.geom_rbound[subg].reshape(-1, 1)
            L = float(np.linalg.norm((pos + r).max(0) - (pos - r).min(0))) or 1.0

        rec = {"joint": joint_name(m, j)}
        for frac in (0.10, 0.25, 0.50):
            R = frac * L
            near_child = near_parent = near_third = 0
            small_near = 0
            for g in range(m.ngeom):
                if dist_to_axis(d.geom_xpos[g], anchor, axis) > R:
                    continue
                b = int(m.geom_bodyid[g])
                if g in sub:
                    near_child += 1
                elif b == parent:
                    near_parent += 1
                else:
                    near_third += 1
                if float(m.geom_rbound[g]) < 0.05 * L:
                    small_near += 1
            tag = f"{int(frac*100)}"
            rec[f"near_total_{tag}"] = near_child + near_parent + near_third
            rec[f"near_child_{tag}"] = near_child
            rec[f"near_parent_{tag}"] = near_parent
            rec[f"near_third_{tag}"] = near_third
            rec[f"has_third_{tag}"] = 1.0 if near_third else 0.0
            rec[f"small_near_{tag}"] = small_near
        rec["l_over_d"] = L / D
        out.append(rec)
    return out


def main():
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    labels = {r["Record ID"].strip(): r for r in rows
              if r["数据来源"].strip() in SRC_NEW and r["是否需要人工复核"].strip() == "否"}
    ids = []
    for line in (HERE / "verifier_results.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("status") == "ok":
            ids.append(j["record_id"])

    per_asset = {}
    for i, rid in enumerate(ids, 1):
        f = feats(rid)
        if f:
            per_asset[rid] = f
        if i % 50 == 0:
            print(f"  {i}/{len(ids)}", flush=True)
    print(f"完成 {len(per_asset)} 条\n")

    keys = sorted({k for v in per_asset.values() for r in v for k in r if k != "joint"})
    bad = [r for r in per_asset if labels.get(r, {}).get(B12, "").strip() == "不满足"]
    good = [r for r in per_asset if labels.get(r, {}).get(B12, "").strip() == "满足"]
    print("=" * 80)
    print(f"关节邻域硬件特征 vs B12    不满足={len(bad)} 满足={len(good)}")
    print("=" * 80)
    print(f"  {'特征':<20} {'聚合':<6} {'AUC_high':>9} {'|信号|':>7}  {'不满足中位':>11} {'满足中位':>11}")
    scored = []
    for k in keys:
        for how, fn in (("min", min), ("max", max), ("median", median)):
            b = [fn([r[k] for r in per_asset[x] if k in r]) for x in bad
                 if any(k in r for r in per_asset[x])]
            g = [fn([r[k] for r in per_asset[x] if k in r]) for x in good
                 if any(k in r for r in per_asset[x])]
            a = auc_high(b, g)
            if a is not None:
                scored.append((abs(a - 0.5), a, k, how, b, g))
    for _, a, k, how, b, g in sorted(scored, key=lambda t: -t[0])[:18]:
        print(f"  {k:<20} {how:<6} {a:>9.4f} {abs(a-0.5):>7.4f}  "
              f"{median(b):>11.4g} {median(g):>11.4g}")


if __name__ == "__main__":
    main()
