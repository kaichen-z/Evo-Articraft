import json, pathlib
from collections import Counter

HERE = pathlib.Path(__file__).parent
rows = [json.loads(l) for l in (HERE / "compile_results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
st = Counter(r["status"] for r in rows)
tot = sum(r["elapsed_s"] for r in rows)
el = sorted(r["elapsed_s"] for r in rows)
print(f"总数 {len(rows)}   状态 {dict(st)}")
print(f"总耗时 {tot/60:.1f} 分钟   单条 中位={el[len(el)//2]:.2f}s  最慢={el[-1]:.2f}s")
print()
bad = [r for r in rows if r["status"] != "ok"]
if bad:
    print("失败条目:")
    for r in bad:
        print(f"  {r['record_id'][:60]}  {r['status']}  {r['error'][:200]}")
else:
    print("无失败")

# 编译产物核对
CACHE = pathlib.Path(r"D:\articraft_project\articraft-data\cache\record_materialization")
lv = Counter()
have_i = have_c = 0
for r in rows:
    if r["status"] != "ok":
        continue
    d = CACHE / r["record_id"]
    rep = d / "compile_report.json"
    u = d / "model.urdf"
    if rep.exists():
        try:
            lv[json.loads(rep.read_text(encoding="utf-8")).get("metrics", {}).get("compile_level")] += 1
        except Exception:
            lv["parse-error"] += 1
    if u.exists():
        t = u.read_text(encoding="utf-8", errors="replace")
        have_i += "<inertial" in t
        have_c += "<collision" in t
print()
print(f"compile_level 分布: {dict(lv)}")
print(f"URDF 含 <inertial>: {have_i}    含 <collision>: {have_c}")
