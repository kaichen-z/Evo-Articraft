"""B12 这个人工维度, 是不是可以由"整体质量"或"类目"解释?

如果 B12 标签主要由星级/类目/复杂度决定, 那它就不是一个可由几何单独判定的
维度 —— 那样的话问题在规范, 不在测量。
"""
import csv, json, pathlib
from collections import Counter, defaultdict
from statistics import median

HERE = pathlib.Path(__file__).parent
BASE = pathlib.Path(r"D:\articraft_project")
V6 = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6"
CSV_PATH = V6 / "tools" / "569.csv"
ALL_CASES = V6 / "data" / "master" / "all_cases.csv"

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


rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
labels = {r["Record ID"].strip(): r for r in rows
          if r["数据来源"].strip() in SRC_NEW and r["是否需要人工复核"].strip() == "否"}

# 星级: 从 records_index.jsonl 取
rating = {}
idx = BASE / "articraft-data" / "records_index.jsonl"
for line in idx.read_text(encoding="utf-8").splitlines():
    try:
        j = json.loads(line)
    except Exception:
        continue
    if j.get("record_id") in labels:
        rating[j["record_id"]] = j.get("effective_rating") or j.get("rating")

res = {}
for line in (HERE / "verifier_results.jsonl").read_text(encoding="utf-8").splitlines():
    try:
        j = json.loads(line)
    except Exception:
        continue
    if j.get("status") == "ok":
        res[j["record_id"]] = j

bad = [r for r in labels if labels[r][B12].strip() == "不满足"]
good = [r for r in labels if labels[r][B12].strip() == "满足"]

print("=" * 80)
print("① B12 标签 vs 整体星级")
print("=" * 80)
rb = [rating[r] for r in bad if rating.get(r) is not None]
rg = [rating[r] for r in good if rating.get(r) is not None]
print(f"  有星级的: 不满足 {len(rb)} / 满足 {len(rg)}")
if rb and rg:
    print(f"  星级中位: 不满足={median(rb)}  满足={median(rg)}   AUC={auc_high(rb, rg):.4f}")
    print(f"  不满足组星级分布: {dict(sorted(Counter(rb).items()))}")
    print(f"  满足组星级分布:   {dict(sorted(Counter(rg).items()))}")

print()
print("=" * 80)
print("② B12 标签 vs 资产复杂度")
print("=" * 80)
for key, get in (("n_joints", lambda j: j.get("n_joints")),
                 ("nbody", lambda j: j.get("nbody")),
                 ("ngeom", lambda j: j.get("ngeom")),
                 ("total_mass", lambda j: j.get("total_mass")),
                 ("d_bbox", lambda j: j.get("d_bbox"))):
    b = [get(res[r]) for r in bad if r in res and get(res[r]) is not None]
    g = [get(res[r]) for r in good if r in res and get(res[r]) is not None]
    a = auc_high(b, g)
    if a is not None:
        print(f"  {key:<12} AUC={a:.4f}  中位 不满足={median(b):<10.4g} 满足={median(g):<10.4g}")

print()
print("=" * 80)
print("③ B12 标签 vs 类目 (失败率最高/最低的类目)")
print("=" * 80)
bycat = defaultdict(lambda: [0, 0])
for r in labels:
    lab = labels[r][B12].strip()
    if lab not in ("满足", "不满足"):
        continue
    cat = labels[r]["Category"].strip()
    bycat[cat][0 if lab == "不满足" else 1] += 1
cats = [(b / (b + g), b + g, c) for c, (b, g) in bycat.items() if b + g >= 3]
cats.sort(reverse=True)
print(f"  样本数>=3 的类目: {len(cats)}")
print("  失败率最高:")
for rate, n, c in cats[:8]:
    print(f"    {rate*100:>5.1f}%  n={n:<3} {c[:56]}")
print("  失败率最低:")
for rate, n, c in cats[-8:]:
    print(f"    {rate*100:>5.1f}%  n={n:<3} {c[:56]}")
allrates = [r for r, n, c in cats]
print(f"  类目间失败率范围: {min(allrates)*100:.0f}% – {max(allrates)*100:.0f}%")

print()
print("=" * 80)
print("④ 标注者一致性线索: 谁标的")
print("=" * 80)
ann = Counter(labels[r].get("Annotator", "").strip() or "(空)" for r in labels)
print(f"  {dict(ann)}")
for a in [x for x in ann if x != "(空)"]:
    sub = [r for r in labels if labels[r].get("Annotator", "").strip() == a]
    c = Counter(labels[r][B12].strip() for r in sub)
    tot = c.get("满足", 0) + c.get("不满足", 0)
    if tot:
        print(f"  {a:<12} n={tot:<4} B12 不满足率={c.get('不满足',0)/tot*100:.1f}%")
