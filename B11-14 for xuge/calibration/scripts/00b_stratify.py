"""标注集可用性: 能重编多少? 分层后每条指标还剩多少可用信号?"""
import csv, pathlib
from collections import Counter, defaultdict

BASE = pathlib.Path(r"D:\articraft_project")
CSV = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"
RECORDS = BASE / "articraft-data" / "records"

B = {
    "B11": "运动学关节的运动范围是否合理",
    "B12": "活动零件是否具有可信的实体连接或支撑结构",
    "B13": "运动过程中是否不存在非预期穿模或几何干涉",
    "B14": "多部件机构的连接与运动关系是否合理",
}
rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))

# ---- 1. 有多少能重编 (record 源目录 + model.py 都在) ----
ok, missing = [], []
for r in rows:
    rid = r["Record ID"].strip()
    d = RECORDS / rid
    mp = list(d.glob("revisions/*/model.py")) if d.exists() else []
    (ok if mp else missing).append(rid)
print("=" * 76)
print("可重编性")
print("=" * 76)
print(f"  标注案例 569 中, records/ 里有 model.py 的: {len(ok)}")
print(f"  找不到源的: {len(missing)}")
for rid in missing[:5]:
    print(f"    缺: {rid[:66]}")

# ---- 2. 按数据来源分层 ----
print()
print("=" * 76)
print("按标注来源分层 (不满足 / 可判定数)")
print("=" * 76)
SRC_NEW = {"新版原始标注（新增案例）", "新版原始标注（覆盖旧版前350条）"}
groups = defaultdict(list)
for r in rows:
    key = "新版原始标注" if r["数据来源"].strip() in SRC_NEW else "旧版350转换"
    groups[key].append(r)
groups["全部"] = rows

print(f"  {'分层':<14} {'n':>5}  " + "  ".join(f"{b:>16}" for b in B))
for key in ("新版原始标注", "旧版350转换", "全部"):
    rs = groups[key]
    cells = []
    for b, col in B.items():
        c = Counter(x[col].strip() for x in rs)
        bad = c.get("不满足", 0)
        judged = bad + c.get("满足", 0)
        cells.append(f"{bad:>5}/{judged:<5}({bad/judged*100 if judged else 0:>4.1f}%)")
    print(f"  {key:<14} {len(rs):>5}  " + "  ".join(f"{x:>16}" for x in cells))

# ---- 3. 需要复核的比例 ----
print()
print("=" * 76)
print("标注可信度")
print("=" * 76)
for col in ("转换置信度", "是否需要人工复核"):
    c = Counter(r[col].strip() for r in rows)
    print(f"  {col:<16} " + "  ".join(f"{k or '(空)'}={v}" for k, v in c.most_common()))

# ---- 4. 最干净的子集: 新版原始 + 不需复核 ----
clean = [r for r in rows
         if r["数据来源"].strip() in SRC_NEW and r["是否需要人工复核"].strip() == "否"]
print()
print(f"  最干净子集 (新版原始 且 不需复核): {len(clean)}")
for b, col in B.items():
    c = Counter(r[col].strip() for r in clean)
    bad, good = c.get("不满足", 0), c.get("满足", 0)
    print(f"    {b}  不满足={bad:>3}  满足={good:>3}  未核验={c.get('未核验',0):>3}  "
          f"不涉及={c.get('不涉及',0):>3}  待复核={c.get('待复核',0):>3}")

# ---- 5. B12/B13 同时可判的交集 (最有价值的对比集) ----
print()
usable = [r for r in rows
          if r[B["B12"]].strip() in ("满足", "不满足")
          and r[B["B13"]].strip() in ("满足", "不满足")]
print(f"  B12 与 B13 同时可判定的案例: {len(usable)}")
c12 = Counter(r[B["B12"]].strip() for r in usable)
c13 = Counter(r[B["B13"]].strip() for r in usable)
print(f"    其中 B12 不满足={c12.get('不满足',0)}  B13 不满足={c13.get('不满足',0)}")
