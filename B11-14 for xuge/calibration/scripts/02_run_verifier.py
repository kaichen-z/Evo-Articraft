"""在重编好的资产上跑验证器, 逐关节打分并聚合到资产级。

设计交代:
- 契约从资产自身合成(关节限位 -> expected_range, 每个关节 -> expected_interface)。
  真实契约应来自 prompt, 这里没有。对 B11 不构成循环论证(它问的是关节能否
  真的走完自己声明的行程), 但 B12 的"每个关节都该有接口"是个假设。
- 人工标注是资产级的, 所以逐关节打分后按**最低分**聚合 —— 一个接口不成立
  就够让整件资产的 B12 不满足, 与人的判断方式一致。
- 扫掠对所有可动关节跑(便宜); 动态试验只对行程最大的 MAX_DYN 个关节跑,
  且只跑 nominal 一次。被截断的关节数写进结果, 不静默丢弃。
"""
import json, pathlib, sys, time, traceback
sys.path.insert(0, r"D:\projects\articraft-verifier")

from verifier.consts import DEFAULT
from verifier.contracts import new_contract
from verifier.metrics import b11, b12, b13, b14
from verifier.primitives.sweep import sweep_joint
from verifier.sim.loader import joint_name, load_urdf, movable_joints
from verifier.sim.runner import run_trial
from verifier.sim.signals import merge
from verifier.types import ToolFailure

CACHE = pathlib.Path(r"D:\articraft_project\articraft-data\cache\record_materialization")
HERE = pathlib.Path(__file__).parent
COMPILED = HERE / "compile_results.jsonl"
OUT = HERE / "verifier_results.jsonl"
MAX_DYN = 3          # 每个资产最多跑几个关节的动态试验


def build_contract(model, jids, rid):
    rng, ifaces = {}, {}
    for j in jids:
        n = joint_name(model, j)
        lo, hi = (float(x) for x in model.jnt_range[j])
        rng[n] = {"min": lo, "max": hi, "source": "asset_limit"}
        ifaces[n] = {"type": "hinge", "source": "synthesized"}
    return new_contract(asset_id=rid, expected_range=rng, expected_interfaces=ifaces,
                        mounting={"base_link": "root", "fixed_to_world": True},
                        expected_movables=[joint_name(model, j) for j in jids])


def run_one(rid: str) -> dict:
    urdf = CACHE / rid / "model.urdf"
    out = {"record_id": rid, "status": "ok", "joints": [], "capped_dynamic": 0}
    if not urdf.exists():
        return {**out, "status": "no_urdf"}
    try:
        loaded = load_urdf(urdf, DEFAULT)
    except ToolFailure as e:
        return {**out, "status": "load_tool_failure", "error": str(e)[:300]}
    except Exception as e:
        return {**out, "status": "load_error", "error": f"{type(e).__name__}: {e}"[:300]}

    m = loaded.model
    jids = movable_joints(m)
    out.update({"provenance": loaded.provenance, "d_bbox": loaded.d_bbox,
                "total_mass": loaded.total_mass, "n_joints": len(jids),
                "nbody": int(m.nbody), "ngeom": int(m.ngeom)})
    if not jids:
        return {**out, "status": "no_movable_joint"}

    contract = build_contract(m, jids, rid)
    span = lambda j: abs(float(m.jnt_range[j][1]) - float(m.jnt_range[j][0]))
    dyn_targets = set(sorted(jids, key=span, reverse=True)[:MAX_DYN])
    out["capped_dynamic"] = max(0, len(jids) - len(dyn_targets))

    for j in jids:
        rec = {"joint": joint_name(m, j), "span": span(j)}
        try:
            sw = sweep_joint(loaded, j, DEFAULT)
        except Exception as e:
            rec["sweep_error"] = f"{type(e).__name__}: {e}"[:200]
            out["joints"].append(rec)
            continue
        rec["sweep"] = {k: v for k, v in sw.as_signals().items()
                        if isinstance(v, (int, float))}
        rec["blocking_pair"] = sw.blocking_pair
        rec["truncated"] = len(sw.truncated)

        dyn = None
        if j in dyn_targets:
            try:
                dyn = run_trial(urdf, j, DEFAULT, 1.0, contract)
                rec["dynamic"] = {k: v for k, v in dyn.items()
                                  if isinstance(v, (int, float))}
            except ToolFailure as e:
                rec["dynamic_tool_failure"] = str(e)[:200]
            except Exception as e:
                rec["dynamic_error"] = f"{type(e).__name__}: {e}"[:200]

        sig = merge(sw, dyn, DEFAULT)
        rec["scores"] = {}
        for name, mod in (("B11", b11), ("B12", b12), ("B13", b13), ("B14", b14)):
            try:
                r = mod.score(sig, contract, DEFAULT)
                rec["scores"][name] = {
                    "score": r.score, "prediction": r.prediction.value,
                    "coverage": r.coverage.value,
                    "sub": {k: (round(v, 6) if isinstance(v, float) else v)
                            for k, v in r.sub_scores.items()},
                    "failure_reason": r.failure_reason,
                }
            except Exception as e:
                rec["scores"][name] = {"error": f"{type(e).__name__}: {e}"[:200]}
        out["joints"].append(rec)

    # 资产级聚合: 每条指标取所有关节里的最低分
    agg = {}
    for name in ("B11", "B12", "B13", "B14"):
        vals = [(jr["scores"][name]["score"], jr["joint"])
                for jr in out["joints"]
                if name in jr.get("scores", {})
                and jr["scores"][name].get("score") is not None]
        if vals:
            s, jn = min(vals, key=lambda t: t[0])
            agg[name] = {"score": s, "worst_joint": jn, "n_scored": len(vals)}
        else:
            agg[name] = {"score": None, "worst_joint": None, "n_scored": 0}
    out["asset"] = agg
    return out


def main():
    ids = []
    for line in COMPILED.read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("status") == "ok":
            ids.append(j["record_id"])
    print(f"待跑验证器: {len(ids)} 条", flush=True)

    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["record_id"])
            except Exception:
                pass
        print(f"已完成(续跑): {len(done)}", flush=True)

    t0 = time.time()
    n = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for i, rid in enumerate(ids, 1):
            if rid in done:
                continue
            t = time.time()
            try:
                res = run_one(rid)
            except Exception:
                res = {"record_id": rid, "status": "crash",
                       "error": traceback.format_exc()[-500:]}
            res["elapsed_s"] = round(time.time() - t, 2)
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 10 == 0 or res.get("status") != "ok":
                rate = (time.time() - t0) / n
                print(f"  [{i}/{len(ids)}] {res.get('status')}  {res['elapsed_s']}s  "
                      f"预计剩余 {(len(ids)-i)*rate/60:.1f} 分钟  {rid[:44]}", flush=True)
    print(f"\n完成 {n} 条, 总耗时 {(time.time()-t0)/60:.1f} 分钟", flush=True)


if __name__ == "__main__":
    main()
