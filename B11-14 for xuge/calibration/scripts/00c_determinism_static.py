"""219 条干净子集: 有多少写了 inertial? 重编是否确定性?"""
import csv, json, pathlib, re
from collections import Counter

BASE = pathlib.Path(r"D:\articraft_project")
CSV = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"
RECORDS = BASE / "articraft-data" / "records"

rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
SRC_NEW = {"新版原始标注（新增案例）", "新版原始标注（覆盖旧版前350条）"}
clean = [r for r in rows if r["数据来源"].strip() in SRC_NEW
         and r["是否需要人工复核"].strip() == "否"]
B12 = "活动零件是否具有可信的实体连接或支撑结构"

INERTIAL = re.compile(r"Inertial\.from_geometry|\.inertial\s*=|Inertial\(")
RANDOM = re.compile(r"\bimport\s+random\b|\brandom\.|np\.random|numpy\.random|"
                    r"\buuid\b|\btime\.time\b|datetime\.now|os\.urandom|\bid\(")

def model_py(rid):
    d = RECORDS / rid
    got = sorted(d.glob("revisions/*/model.py")) if d.exists() else []
    return got[-1] if got else None

stats = Counter()
nondet = []
by_label = {"满足": Counter(), "不满足": Counter()}
for r in clean:
    rid = r["Record ID"].strip()
    p = model_py(rid)
    if not p:
        stats["无源"] += 1
        continue
    src = p.read_text(encoding="utf-8", errors="replace")
    has_i = bool(INERTIAL.search(src))
    stats["有 inertial" if has_i else "无 inertial"] += 1
    lbl = r[B12].strip()
    if lbl in by_label:
        by_label[lbl]["有" if has_i else "无"] += 1
    hits = sorted(set(RANDOM.findall(src)))
    if hits:
        nondet.append((rid, hits))

print("=" * 74)
print(f"219 条干净子集里 model.py 是否写了惯量")
print("=" * 74)
for k, v in stats.most_common():
    print(f"  {k:<12} {v}")
print()
print("  按 B12 人工标签拆分 (预测重编后的 provenance):")
for lbl, c in by_label.items():
    tot = sum(c.values())
    print(f"    B12={lbl:<4}  有 inertial={c['有']:>3}  无={c['无']:>3}  "
          f"(-> asset {c['有']/tot*100 if tot else 0:.0f}% / inferred {c['无']/tot*100 if tot else 0:.0f}%)")

print()
print("=" * 74)
print("确定性: model.py 里有没有随机/时间/uuid 来源")
print("=" * 74)
print(f"  命中的文件: {len(nondet)} / {len(clean)}")
for rid, hits in nondet[:8]:
    print(f"    {rid[:52]:<52} {hits}")

# ---- SDK 兼容性: model.py 导入的符号现在还在不在 ----
print()
print("=" * 74)
print("SDK 兼容性: model.py 导入的符号在当前 sdk 里是否还存在")
print("=" * 74)
import sys
sys.path.insert(0, str(BASE / "articraft"))
try:
    import sdk
    exported = set(dir(sdk))
except Exception as e:
    print("  无法 import sdk:", e)
    exported = None

if exported is not None:
    missing = Counter()
    checked = 0
    for r in clean:
        p = model_py(r["Record ID"].strip())
        if not p:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"from sdk import \(([^)]*)\)", src) or \
            re.search(r"from sdk import ([^\n(]+)", src)
        if not m:
            continue
        checked += 1
        for name in re.split(r"[,\s]+", m.group(1)):
            name = name.strip().strip(",")
            if name and name not in exported:
                missing[name] += 1
    print(f"  检查了 {checked} 个 model.py 的 sdk 导入")
    if missing:
        print(f"  当前 sdk 里缺失的符号:")
        for name, cnt in missing.most_common(15):
            print(f"    {name:<28} 被 {cnt} 个 model.py 导入")
    else:
        print("  全部导入符号在当前 sdk 中都存在")

# ---- provenance 里记的 sdk 版本 ----
print()
vers = Counter()
for r in clean:
    d = RECORDS / r["Record ID"].strip()
    for pv in d.glob("revisions/*/provenance.json"):
        try:
            j = json.loads(pv.read_text(encoding="utf-8"))
            vers[(j.get("sdk", {}) or {}).get("sdk_version")] += 1
        except Exception:
            pass
print("  provenance 记录的 sdk_version:", dict(vers))
