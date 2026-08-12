"""人到底在判什么: B12 不满足与其他标注维度的共现 + 分歧案例的 notes。"""
import csv, json, pathlib
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).parent
BASE = pathlib.Path(r"D:\articraft_project")
CSV_PATH = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"

B12 = "活动零件是否具有可信的实体连接或支撑结构"
B11 = "运动学关节的运动范围是否合理"
B13 = "运动过程中是否不存在非预期穿模或几何干涉"
SRC_NEW = {"新版原始标注（新增案例）", "新版原始标注（覆盖旧版前350条）"}

rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
clean = {r["Record ID"].strip(): r for r in rows
         if r["数据来源"].strip() in SRC_NEW and r["是否需要人工复核"].strip() == "否"}

res = {}
for line in (HERE / "verifier_results.jsonl").read_text(encoding="utf-8").splitlines():
    try:
        j = json.loads(line)
    except Exception:
        continue
    if j.get("status") == "ok":
        res[j["record_id"]] = j

DIMS = [c for c in rows[0]
        if c.endswith(("是否合理", "是否正确", "是否完整", "是否符合描述",
                       "或脱离", "支撑结构", "几何干涉", "运动学关节"))
        and c not in ("检查是否完成",)]

print("=" * 88)
print("① B12=不满足 时, 其他标注维度同时不满足的比例")
print("=" * 88)
bad_ids = [r for r in clean if clean[r][B12].strip() == "不满足"]
good_ids = [r for r in clean if clean[r][B12].strip() == "满足"]
print(f"  B12 不满足 {len(bad_ids)} 条, 满足 {len(good_ids)} 条\n")
print(f"  {'维度':<38} {'B12不满足组':>12} {'B12满足组':>12} {'提升':>8}")
stats = []
for d in DIMS:
    if d == B12:
        continue
    pb = sum(1 for r in bad_ids if clean[r][d].strip() == "不满足") / max(1, len(bad_ids))
    pg = sum(1 for r in good_ids if clean[r][d].strip() == "不满足") / max(1, len(good_ids))
    stats.append((pb - pg, d, pb, pg))
for lift, d, pb, pg in sorted(stats, key=lambda t: -t[0]):
    print(f"  {d:<38} {pb*100:>11.1f}% {pg*100:>11.1f}% {lift*100:>+7.1f}pp")

print()
print("=" * 88)
print("② Notes 填写率与内容")
print("=" * 88)
withnote = [r for r in clean if clean[r].get("Notes", "").strip()]
print(f"  219 条里有 Notes 的: {len(withnote)}")
nb = [r for r in withnote if clean[r][B12].strip() == "不满足"]
print(f"  其中 B12 不满足的: {len(nb)}")
for r in nb[:12]:
    print(f"\n  --- {r[:58]}")
    print(f"      {clean[r]['Notes'].strip()[:300]}")

print()
print("=" * 88)
print("③ 分歧最大的案例 (人判不满足, 但验证器 S_interface 最高)")
print("=" * 88)


def s_interface(rid):
    j = res.get(rid)
    if not j:
        return None
    worst = j["asset"]["B12"].get("worst_joint")
    for jr in j["joints"]:
        if jr.get("joint") == worst:
            return jr.get("scores", {}).get("B12", {}).get("sub", {}).get("S_interface")
    return None


miss = sorted(((s_interface(r), r) for r in bad_ids if s_interface(r) is not None),
              key=lambda t: -t[0])[:8]
print("  验证器认为接口没问题, 但人判不满足:")
for s, r in miss:
    j = res[r]
    print(f"    S_interface={s:.4g}  joints={j['n_joints']:<3} prov={j.get('provenance'):<9} "
          f"{r[:52]}")
    print(f"       类目: {clean[r]['Category'][:60]}")
    note = clean[r].get("Notes", "").strip()
    if note:
        print(f"       note: {note[:180]}")

print()
fp = sorted(((s_interface(r), r) for r in good_ids if s_interface(r) is not None),
            key=lambda t: t[0])[:8]
print("  验证器判接口=0, 但人判满足:")
for s, r in fp:
    j = res[r]
    print(f"    S_interface={s:.4g}  joints={j['n_joints']:<3} prov={j.get('provenance'):<9} "
          f"{r[:52]}")
    print(f"       类目: {clean[r]['Category'][:60]}")

print()
print("=" * 88)
print("④ 人工标注里最常见的失败维度 (全 219 条)")
print("=" * 88)
for d in DIMS:
    c = Counter(clean[r][d].strip() for r in clean)
    bad = c.get("不满足", 0)
    if bad:
        print(f"  {d:<40} 不满足={bad:>3}  满足={c.get('满足',0):>3}  "
              f"不涉及={c.get('不涉及',0):>3}")
