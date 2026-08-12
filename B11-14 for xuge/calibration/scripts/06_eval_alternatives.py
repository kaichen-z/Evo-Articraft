"""替代估计量的判别力。

AUC_high = P(特征值在"不满足"组更大) + 0.5*P(相等)
  0.5 = 无信号   >0.5 = 值越大越失败   <0.5 = 反向
"""
import csv, json, pathlib
from statistics import median

HERE = pathlib.Path(__file__).parent
BASE = pathlib.Path(r"D:\articraft_project")
CSV_PATH = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"

B12 = "活动零件是否具有可信的实体连接或支撑结构"
INIT = "初始状态是否不存在非预期穿插、悬浮或脱离"
B13 = "运动过程中是否不存在非预期穿模或几何干涉"
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


def features(rec):
    """从一条探测记录导出候选特征。距离已按 D 归一。"""
    D = rec.get("d_bbox") or 1.0
    f = {}

    # ---- 逐关节: 取所有关节里最差的 ----
    per_joint = []
    for j in rec.get("joints", []):
        ds = [x for x in j["dists"] if x is not None]
        n_orphan = sum(1 for x in j["dists"] if x is None)
        n_tot = len(j["dists"]) or 1
        if not ds:
            per_joint.append({"min": None, "max": 1.0, "med": 1.0,
                              "orphan": n_orphan / n_tot, "pen": 0.0})
            continue
        nd = [x / D for x in ds]
        per_joint.append({
            "min": min(nd), "max": max(nd), "med": median(nd),
            "orphan": n_orphan / n_tot,
            "pen": max(0.0, -min(nd)),
            "frac_far_005": sum(1 for x in nd if x > 0.005) / n_tot,
            "frac_far_01": sum(1 for x in nd if x > 0.01) / n_tot,
            "frac_far_02": sum(1 for x in nd if x > 0.02) / n_tot,
        })
    if per_joint:
        f["j_min_gap"] = min(p["min"] for p in per_joint if p["min"] is not None) \
            if any(p["min"] is not None for p in per_joint) else 0.0
        f["j_max_gap"] = max(p["max"] for p in per_joint)
        f["j_med_gap"] = max(p["med"] for p in per_joint)
        f["j_orphan_frac"] = max(p["orphan"] for p in per_joint)
        f["j_penetration"] = max(p["pen"] for p in per_joint)
        for k in ("frac_far_005", "frac_far_01", "frac_far_02"):
            vals = [p.get(k, 0.0) for p in per_joint]
            f[f"j_{k}"] = max(vals) if vals else 0.0

    # ---- 资产级: 所有 body 的最近邻分布 ----
    bs = rec.get("bodies", [])
    near = [b["nearest"] / D for b in bs if b.get("nearest") is not None]
    orph = sum(b.get("n_orphan", 0) for b in bs)
    ngeom = sum(b.get("n_geom", 0) for b in bs) or 1
    if near:
        f["b_max_gap"] = max(near)
        f["b_med_gap"] = median(near)
        f["b_penetration"] = max(0.0, -min(near))
        for eps in (0.002, 0.005, 0.01, 0.02):
            f[f"b_frac_float_{eps}"] = sum(1 for x in near if x > eps) / len(near)
            f[f"b_n_float_{eps}"] = sum(1 for x in near if x > eps)
        f["b_frac_pen"] = sum(1 for x in near if x < -0.001) / len(near)
    f["b_orphan_geoms"] = orph / ngeom
    f["n_bodies"] = len(bs)
    return f


def main():
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    labels = {r["Record ID"].strip(): r for r in rows
              if r["数据来源"].strip() in SRC_NEW
              and r["是否需要人工复核"].strip() == "否"}

    probes = {}
    for line in (HERE / "attach_probe.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("status") == "ok":
            probes[j["record_id"]] = j

    print(f"探测成功 {len(probes)} / 标注 {len(labels)}")
    capped = sum(1 for j in probes.values() if j.get("capped"))
    print(f"距离查询被截断的资产: {capped}")

    feats = {rid: features(j) for rid, j in probes.items()}
    keys = sorted({k for f in feats.values() for k in f})

    # 现有 g0 作为基线
    base = {}
    for line in (HERE / "verifier_results.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("status") != "ok":
            continue
        worst = j["asset"]["B12"].get("worst_joint")
        for jr in j["joints"]:
            if jr.get("joint") == worst:
                sw = jr.get("sweep") or {}
                base[j["record_id"]] = {"[基线] g0": sw.get("g0"),
                                        "[基线] s_clearance": sw.get("s_clearance"),
                                        "[基线] d_anchor": sw.get("d_anchor")}

    for target, col in (("B12 实体连接支撑", B12),
                        ("初始状态穿插/悬浮/脱离", INIT),
                        ("B13 运动穿模干涉", B13)):
        bad_ids = [r for r in feats if r in labels and labels[r][col].strip() == "不满足"]
        good_ids = [r for r in feats if r in labels and labels[r][col].strip() == "满足"]
        print()
        print("=" * 86)
        print(f"目标: {target}    不满足={len(bad_ids)}  满足={len(good_ids)}")
        print("=" * 86)
        scored = []
        for k in keys:
            bd = [feats[r][k] for r in bad_ids if k in feats[r]]
            gd = [feats[r][k] for r in good_ids if k in feats[r]]
            a = auc_high(bd, gd)
            if a is not None:
                scored.append((abs(a - 0.5), a, k, bd, gd))
        for k in ("[基线] g0", "[基线] s_clearance", "[基线] d_anchor"):
            bd = [base[r][k] for r in bad_ids if r in base and base[r].get(k) is not None]
            gd = [base[r][k] for r in good_ids if r in base and base[r].get(k) is not None]
            a = auc_high(bd, gd)
            if a is not None:
                scored.append((abs(a - 0.5), a, k, bd, gd))
        print(f"  {'特征':<24} {'AUC_high':>9} {'|信号|':>7}  {'不满足中位':>13} {'满足中位':>13}")
        for _, a, k, bd, gd in sorted(scored, key=lambda t: -t[0])[:16]:
            print(f"  {k:<24} {a:>9.4f} {abs(a-0.5):>7.4f}  "
                  f"{median(bd):>13.6g} {median(gd):>13.6g}")


if __name__ == "__main__":
    main()
