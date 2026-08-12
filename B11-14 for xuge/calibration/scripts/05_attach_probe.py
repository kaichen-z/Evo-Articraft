"""静止姿态下的"装配可信度"替代估计量。

现有 g0 = min(活动连杆几何 × 父连杆几何) 的距离。min 对"悬浮"极不敏感:
只要有一对几何贴着, min 就是 0, 哪怕整个零件其余部分都悬空。

这里改成保留**每个几何到最近非自身几何的距离**这一整个分布, 之后可以在
分布上试各种统计量(比例/最大值/分位数)和阈值, 不用重跑仿真。
只算 q0 单姿态, 纯几何, 不跑动力学。
"""
import json, pathlib, sys, time
sys.path.insert(0, r"D:\projects\articraft-verifier")

import mujoco
import numpy as np

from verifier.consts import DEFAULT
from verifier.sim.loader import (body_name, body_subtree_geoms, joint_name,
                                 load_urdf, movable_joints)
from verifier.types import ToolFailure

CACHE = pathlib.Path(r"D:\articraft_project\articraft-data\cache\record_materialization")
HERE = pathlib.Path(__file__).parent
OUT = HERE / "attach_probe.jsonl"
DISTMAX = 1.0
MAX_QUERIES = 400_000       # 每个资产的距离查询上限, 超了记录下来


def nearest_dists(m, d, group, others, budget):
    """group 里每个 geom 到 others 中最近者的距离。超量程记 None。"""
    out, used = [], 0
    for g in group:
        best = None
        for o in others:
            if used >= budget:
                return out, used, True
            used += 1
            dist = mujoco.mj_geomDistance(m, d, int(g), int(o), DISTMAX, None)
            if dist >= DISTMAX:
                continue
            if best is None or dist < best:
                best = float(dist)
        out.append(best)          # None = 量程内没有任何邻居
    return out, used, False


def probe(rid: str) -> dict:
    urdf = CACHE / rid / "model.urdf"
    rec = {"record_id": rid}
    try:
        loaded = load_urdf(urdf, DEFAULT)
    except ToolFailure as e:
        return {**rec, "status": "tool_failure", "error": str(e)[:200]}
    m, d = loaded.model, loaded.data
    mujoco.mj_forward(m, d)
    rec.update({"status": "ok", "d_bbox": loaded.d_bbox,
                "provenance": loaded.provenance, "ngeom": int(m.ngeom)})

    budget = MAX_QUERIES
    capped = False

    # --- 逐关节: 活动连杆每个几何到"非自身子树"最近距离的分布 ---
    joints = []
    for j in movable_joints(m):
        sub = body_subtree_geoms(m, int(m.jnt_bodyid[j]))
        rest = [g for g in range(m.ngeom) if g not in set(sub)]
        if not sub or not rest:
            continue
        ds, used, cap = nearest_dists(m, d, sub, rest, budget)
        budget -= used
        capped = capped or cap
        joints.append({"joint": joint_name(m, j), "n_geom": len(sub),
                       "dists": [None if x is None else round(x, 8) for x in ds]})
        if budget <= 0:
            capped = True
            break
    rec["joints"] = joints

    # --- 资产级: 每个非世界 body 到其他 body 的最近距离 ---
    bodies = []
    for b in range(1, m.nbody):
        gs = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) == b]
        rest = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) != b]
        if not gs or not rest or budget <= 0:
            if budget <= 0:
                capped = True
            continue
        ds, used, cap = nearest_dists(m, d, gs, rest, budget)
        budget -= used
        capped = capped or cap
        vals = [x for x in ds if x is not None]
        bodies.append({"body": body_name(m, b), "n_geom": len(gs),
                       "nearest": round(min(vals), 8) if vals else None,
                       "farthest_nearest": round(max(vals), 8) if vals else None,
                       "n_orphan": sum(1 for x in ds if x is None)})
    rec["bodies"] = bodies
    rec["capped"] = capped
    return rec


def main():
    ids = []
    for line in (HERE / "verifier_results.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("status") == "ok":
            ids.append(j["record_id"])
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["record_id"])
            except Exception:
                pass
    print(f"待探测 {len(ids)} 条, 已完成 {len(done)}", flush=True)

    t0 = time.time()
    n = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for i, rid in enumerate(ids, 1):
            if rid in done:
                continue
            t = time.time()
            try:
                r = probe(rid)
            except Exception as e:
                r = {"record_id": rid, "status": "crash", "error": f"{type(e).__name__}: {e}"[:200]}
            r["elapsed_s"] = round(time.time() - t, 2)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 20 == 0:
                rate = (time.time() - t0) / n
                print(f"  [{i}/{len(ids)}] {(len(ids)-i)*rate/60:.1f} 分钟剩余", flush=True)
    print(f"完成 {n} 条, {(time.time()-t0)/60:.1f} 分钟", flush=True)


if __name__ == "__main__":
    main()
