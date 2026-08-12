"""人工标注集的可用性分析: 569 条里有多少能真跑验证器。"""
import csv, json, pathlib
from collections import Counter

BASE = pathlib.Path(r"D:\articraft_project")
V6 = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6"
CACHE = BASE / "articraft-data" / "cache" / "record_materialization"

B_COLS = {
    "B11": "运动学关节的运动范围是否合理",
    "B12": "活动零件是否具有可信的实体连接或支撑结构",
    "B13": "运动过程中是否不存在非预期穿模或几何干涉",
    "B14": "多部件机构的连接与运动关系是否合理",
}

for name in ("data/batches/all_569_cases.csv", "tools/569.csv"):
    p = V6 / name
    if not p.exists():
        continue
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    print("=" * 78)
    print(f"{name}   {len(rows)} 行   {len(rows[0])} 列")
    print("=" * 78)
    if name.startswith("data/"):
        print("列名:", list(rows[0].keys()))
    print()
    for b, col in B_COLS.items():
        if col not in rows[0]:
            print(f"  {b}: 列缺失"); continue
        c = Counter(r[col].strip() for r in rows)
        tot = sum(c.values())
        line = "  ".join(f"{k or '(空)'}={v}" for k, v in c.most_common())
        print(f"  {b}  {line}   (n={tot})")
    print()
    # 数据来源与置信度
    for col in ("数据来源", "转换置信度", "是否需要人工复核", "检查是否完成"):
        if col in rows[0]:
            c = Counter(r[col].strip() for r in rows)
            print(f"  {col}: " + "  ".join(f"{k or '(空)'}={v}" for k, v in c.most_common(6)))
    print()

# ---------------- 可跑性: 有多少标注案例有 full 级 URDF ----------------
rows = list(csv.DictReader((V6 / "tools" / "569.csv").open(encoding="utf-8-sig")))
key = "Record ID" if "Record ID" in rows[0] else "record_id"
annotated = {r[key].strip() for r in rows}

levels = {}
for rep in CACHE.rglob("compile_report.json"):
    try:
        j = json.loads(rep.read_text(encoding="utf-8"))
    except Exception:
        continue
    rid = j.get("record_id") or rep.parent.name
    if (rep.parent / "model.urdf").exists():
        levels[rid] = j.get("metrics", {}).get("compile_level")

print("=" * 78)
print("可跑性")
print("=" * 78)
print(f"  标注案例          {len(annotated)}")
print(f"  已物化 URDF 的记录 {len(levels)}  ({Counter(levels.values())})")
inter = annotated & set(levels)
print(f"  两者交集          {len(inter)}")
full = {r for r in inter if levels[r] == "full"}
print(f"  其中 compile_level=full  {len(full)}")
for r in sorted(full):
    print(f"    {r[:70]}")
