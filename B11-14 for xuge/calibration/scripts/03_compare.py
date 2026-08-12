"""人工标注 vs 验证器: 判别力、阈值校准、混淆矩阵。

AUC 约定: 正类 = 人工判"不满足"。
  AUC = P(score(不满足) < score(满足)) + 0.5*P(相等)
  1.0 = 完全分开(失败案例分数一律更低)   0.5 = 纯噪声   <0.5 = 方向反了
"""
import csv, json, pathlib
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).parent
BASE = pathlib.Path(r"D:\articraft_project")
CSV_PATH = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"

B = {
    "B11": "运动学关节的运动范围是否合理",
    "B12": "活动零件是否具有可信的实体连接或支撑结构",
    "B13": "运动过程中是否不存在非预期穿模或几何干涉",
    "B14": "多部件机构的连接与运动关系是否合理",
}
SRC_NEW = {"新版原始标注（新增案例）", "新版原始标注（覆盖旧版前350条）"}


def auc(bad: list[float], good: list[float]) -> float | None:
    """P(bad < good) + 0.5*P(tie)。bad/good 为空时返回 None。"""
    if not bad or not good:
        return None
    less = ties = 0
    for x in bad:
        for y in good:
            if x < y:
                less += 1
            elif x == y:
                ties += 1
    return (less + 0.5 * ties) / (len(bad) * len(good))


def quart(xs):
    if not xs:
        return "—"
    s = sorted(xs)
    n = len(s)
    q = lambda p: s[min(n - 1, int(p * n))]
    return f"{q(0.25):.4g} / {q(0.5):.4g} / {q(0.75):.4g}"


def load():
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    clean = {r["Record ID"].strip(): r for r in rows
             if r["数据来源"].strip() in SRC_NEW
             and r["是否需要人工复核"].strip() == "否"}
    res = {}
    for line in (HERE / "verifier_results.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        res[j["record_id"]] = j
    return clean, res


def main():
    labels, results = load()
    print("=" * 82)
    print("对比集构成")
    print("=" * 82)
    print(f"  干净标注子集      {len(labels)}")
    print(f"  验证器跑出结果    {len(results)}")
    inter = set(labels) & set(results)
    print(f"  两者交集          {len(inter)}")
    st = Counter(results[r]["status"] for r in inter)
    print(f"  验证器状态分布    {dict(st)}")
    scored = [r for r in inter if results[r]["status"] == "ok"]
    print(f"  可用于对比        {len(scored)}")
    prov = Counter(results[r].get("provenance") for r in scored)
    print(f"  physics_provenance {dict(prov)}")
    capped = sum(results[r].get("capped_dynamic", 0) for r in scored)
    print(f"  被截断未跑动态的关节总数 {capped}  (每资产最多跑 3 个)")

    for metric in ("B11", "B12", "B13", "B14"):
        col = B[metric]
        bad, good, nones = [], [], Counter()
        for rid in scored:
            lab = labels[rid][col].strip()
            if lab not in ("满足", "不满足"):
                continue
            s = results[rid]["asset"][metric]["score"]
            if s is None:
                nones[lab] += 1
                continue
            (bad if lab == "不满足" else good).append(s)

        print()
        print("=" * 82)
        print(f"{metric}   人工不满足={len(bad)}  满足={len(good)}  "
              f"分数为 None={dict(nones) or '{}'}")
        print("=" * 82)
        if not bad or not good:
            print("  正例或负例为空, 无法评估判别力")
            continue

        a = auc(bad, good)
        print(f"  AUC = {a:.4f}   (0.5=纯噪声)")
        print(f"  分数四分位 (Q1/中位/Q3)")
        print(f"    不满足  {quart(bad)}")
        print(f"    满足    {quart(good)}")
        z_bad = sum(1 for x in bad if x == 0.0)
        z_good = sum(1 for x in good if x == 0.0)
        print(f"  恰好为 0 的比例:  不满足 {z_bad}/{len(bad)} ({z_bad/len(bad)*100:.0f}%)"
              f"   满足 {z_good}/{len(good)} ({z_good/len(good)*100:.0f}%)")

        # 阈值扫描
        cand = sorted(set(bad + good))
        best = None
        for t in cand:
            tp = sum(1 for x in bad if x < t)
            fn = len(bad) - tp
            tn = sum(1 for x in good if x >= t)
            fp = len(good) - tn
            bacc = 0.5 * (tp / len(bad) + tn / len(good))
            if best is None or bacc > best[1]:
                best = (t, bacc, tp, fn, tn, fp)
        t, bacc, tp, fn, tn, fp = best
        print(f"  τ=0.70 下的混淆矩阵 (预测不满足 = score<τ):")
        tp0 = sum(1 for x in bad if x < 0.70)
        tn0 = sum(1 for x in good if x >= 0.70)
        print(f"    TP={tp0:>3} FN={len(bad)-tp0:>3} | TN={tn0:>3} FP={len(good)-tn0:>3}"
              f"   平衡准确率={0.5*(tp0/len(bad)+tn0/len(good)):.4f}")
        print(f"  经验最优 τ={t:.6g}:  TP={tp} FN={fn} | TN={tn} FP={fp}"
              f"   平衡准确率={bacc:.4f}")

    # ---------------- B12 逐因子判别力 ----------------
    print()
    print("=" * 82)
    print("B12 逐因子判别力 —— 哪几个因子携带信号, 哪几个是噪声")
    print("=" * 82)
    col = B["B12"]
    factors = defaultdict(lambda: ([], []))
    for rid in scored:
        lab = labels[rid][col].strip()
        if lab not in ("满足", "不满足"):
            continue
        worst = results[rid]["asset"]["B12"].get("worst_joint")
        for jr in results[rid]["joints"]:
            if jr.get("joint") != worst:
                continue
            sub = jr.get("scores", {}).get("B12", {}).get("sub", {})
            for k, v in sub.items():
                if isinstance(v, (int, float)):
                    factors[k][0 if lab == "不满足" else 1].append(float(v))
    print(f"  {'因子':<16} {'AUC':>7}  {'不满足 Q1/中位/Q3':>28}  {'满足 Q1/中位/Q3':>28}")
    rows = []
    for k, (bd, gd) in factors.items():
        a = auc(bd, gd)
        rows.append((a if a is not None else 0.5, k, bd, gd))
    for a, k, bd, gd in sorted(rows, key=lambda t: -abs(t[0] - 0.5)):
        print(f"  {k:<16} {a:>7.4f}  {quart(bd):>28}  {quart(gd):>28}")

    # ---------------- 原始测量的判别力 ----------------
    print()
    print("=" * 82)
    print("扫掠原始测量的判别力 (绕开公式, 看测量本身有没有信号)")
    print("=" * 82)
    raws = defaultdict(lambda: ([], []))
    for rid in scored:
        lab = labels[rid][col].strip()
        if lab not in ("满足", "不满足"):
            continue
        worst = results[rid]["asset"]["B12"].get("worst_joint")
        for jr in results[rid]["joints"]:
            if jr.get("joint") != worst:
                continue
            for k, v in (jr.get("sweep") or {}).items():
                if isinstance(v, (int, float)):
                    raws[k][0 if lab == "不满足" else 1].append(float(v))
    print(f"  {'测量':<20} {'AUC':>7}  {'不满足 中位':>14}  {'满足 中位':>14}")
    rr = []
    for k, (bd, gd) in raws.items():
        a = auc(bd, gd)
        if a is None:
            continue
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else float("nan")
        rr.append((a, k, med(bd), med(gd)))
    for a, k, mb, mg in sorted(rr, key=lambda t: -abs(t[0] - 0.5)):
        print(f"  {k:<20} {a:>7.4f}  {mb:>14.6g}  {mg:>14.6g}")


if __name__ == "__main__":
    main()
