"""把 219 条干净标注子集按 --target full 重编。

每条独立子进程: 一条 model.py 崩了不会带走整批。失败逐条记录, 不静默丢弃。
结果写 compile_results.jsonl, 可随时读进度。
"""
import csv, json, pathlib, subprocess, sys, time

BASE = pathlib.Path(r"D:\articraft_project")
REPO = BASE / "articraft"
DATA = BASE / "articraft-data"
PY = REPO / ".venv" / "Scripts" / "python.exe"
CSV_PATH = BASE / "articraft_annotation_v6_old_new" / "articraft_annotation_v6" / "tools" / "569.csv"
OUT = pathlib.Path(__file__).parent / "compile_results.jsonl"

SRC_NEW = {"新版原始标注（新增案例）", "新版原始标注（覆盖旧版前350条）"}
rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
clean = [r for r in rows if r["数据来源"].strip() in SRC_NEW
         and r["是否需要人工复核"].strip() == "否"]
ids = [r["Record ID"].strip() for r in clean]
print(f"待编译: {len(ids)} 条", flush=True)

done = set()
if OUT.exists():
    for line in OUT.read_text(encoding="utf-8").splitlines():
        try:
            done.add(json.loads(line)["record_id"])
        except Exception:
            pass
    print(f"已完成(断点续跑): {len(done)}", flush=True)

t0 = time.time()
ok = fail = 0
with OUT.open("a", encoding="utf-8") as fh:
    for i, rid in enumerate(ids, 1):
        if rid in done:
            continue
        t = time.time()
        try:
            p = subprocess.run(
                [str(PY), "-m", "cli.main", "compile", rid, "--target", "full",
                 "--repo-root", str(REPO), "--data-dir", str(DATA)],
                cwd=str(REPO), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300,
            )
            status, code = ("ok" if p.returncode == 0 else "fail"), p.returncode
            err = "" if p.returncode == 0 else (p.stderr or p.stdout or "")[-600:]
        except subprocess.TimeoutExpired:
            status, code, err = "timeout", -1, "300s 超时"
        except Exception as e:
            status, code, err = "error", -2, f"{type(e).__name__}: {e}"

        el = time.time() - t
        ok, fail = (ok + 1, fail) if status == "ok" else (ok, fail + 1)
        fh.write(json.dumps({"record_id": rid, "status": status, "returncode": code,
                             "elapsed_s": round(el, 2), "error": err},
                            ensure_ascii=False) + "\n")
        fh.flush()
        if i % 10 == 0 or status != "ok":
            rate = (time.time() - t0) / max(1, i - len(done))
            left = (len(ids) - i) * rate
            print(f"  [{i}/{len(ids)}] ok={ok} fail={fail}  本条 {el:.1f}s  "
                  f"预计剩余 {left/60:.1f} 分钟  {rid[:44]}", flush=True)

print(f"\n完成: ok={ok} fail={fail}  总耗时 {(time.time()-t0)/60:.1f} 分钟", flush=True)
