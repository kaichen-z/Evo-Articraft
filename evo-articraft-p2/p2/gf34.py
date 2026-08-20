"""GF3 部件关系保真 + GF4 比例保真（确定性三维测量，P0 真 schema）。

GF3 消费 part_relations: [{subject, relation, object}]
    relation ∈ {attached_to, inside, above, aligned}（兼容旧名 attached）
    subject/object 经 PartBinding 解析：实例 / 抽象 part（展开为全部实例）/ geom 名。
    抽象引用展开后 = 全部实例都要满足（如 6 个 drawer 都要 attached_to body）。

GF4 消费 proportion_claims：
    成组 {parts:[...], measure, target_ratio:[...], tolerance} → 逐一对第一个成员展开
    成对 {subject, object, measure, target_ratio, tolerance}
    score = exp(−|log(r_obs/r_target)| / σ),  σ = ln(1 + tolerance)
    （tolerance 边界处得分恰为 1/e ≈ 0.368；换算约定 PROVISIONAL）

不可测（引用解析失败 / link 无几何 / 尺寸退化）记 unmeasurable，不折成 0 分。
"""

from __future__ import annotations

import math

import numpy as np

from . import consts
from .binding import PartBinding, PartInstance
from .mj_scene import Scene

RELATION_ALIASES = {"attached": "attached_to"}


# ============================================================ 公共几何

def _aabb_inside_frac(lo_a, hi_a, lo_b, hi_b) -> float:
    inter_lo = np.maximum(lo_a, lo_b)
    inter_hi = np.minimum(hi_a, hi_b)
    inter = np.clip(inter_hi - inter_lo, 0.0, None)
    vol_a = float(np.prod(np.clip(hi_a - lo_a, 1e-12, None)))
    return float(np.prod(inter)) / vol_a


def _footprint_overlap_frac(lo_a, hi_a, lo_b, hi_b) -> float:
    inter_lo = np.maximum(lo_a[:2], lo_b[:2])
    inter_hi = np.minimum(hi_a[:2], hi_b[:2])
    inter = np.clip(inter_hi - inter_lo, 0.0, None)
    area_a = float(np.prod(np.clip(hi_a[:2] - lo_a[:2], 1e-12, None)))
    return float(np.prod(inter)) / area_a


# ============================================================ GF3

def _eval_pair(scene: Scene, rel: str, si: PartInstance, oi: PartInstance,
               axis) -> dict:
    """单实例对的关系判定。"""
    D = scene.d_bbox
    ga, gb = si.geom_ids, oi.geom_ids
    if not ga or not gb:
        return {"subject": si.instance_id, "object": oi.instance_id,
                "satisfied": None, "measured": None, "note": "no geoms"}

    notes = []
    if si.fused or oi.fused:
        notes.append("fused-proxy:" + ",".join(
            x.instance_id for x in (si, oi) if x.fused))
    if si.pseudo or oi.pseudo:
        notes.append("geom-level-ref")

    lo_a, hi_a = scene.world_aabb(ga)
    lo_b, hi_b = scene.world_aabb(gb)

    if rel == "attached_to":
        sd = scene.min_signed_distance(ga, gb)
        if sd < -consts.ATTACH_MAX_PEN * D:
            state = "penetration"
        elif sd <= consts.ATTACH_MAX_GAP * D:
            state = "contact"
        else:
            state = "separated"
        return {"subject": si.instance_id, "object": oi.instance_id,
                "satisfied": bool(state == "contact"),
                "measured": {"signed_distance": sd,
                             "signed_distance_over_D": sd / D,
                             "state": state},
                "note": ";".join(notes)}

    if rel == "inside":
        frac = _aabb_inside_frac(lo_a, hi_a, lo_b, hi_b)
        return {"subject": si.instance_id, "object": oi.instance_id,
                "satisfied": bool(frac >= consts.INSIDE_MIN_FRAC),
                "measured": {"inside_fraction": frac},
                "note": ";".join(notes)}

    if rel == "above":
        gap = float(lo_a[2] - hi_b[2])
        overlap = _footprint_overlap_frac(lo_a, hi_a, lo_b, hi_b)
        ok = (gap >= -consts.ABOVE_TOL * D) and (overlap >= consts.ABOVE_MIN_OVERLAP)
        return {"subject": si.instance_id, "object": oi.instance_id,
                "satisfied": bool(ok),
                "measured": {"z_gap_over_D": gap / D, "footprint_overlap": overlap},
                "note": ";".join(notes)}

    if rel == "aligned":
        ax = np.array(axis if axis is not None else [0, 0, 1], dtype=float)
        ax = ax / (np.linalg.norm(ax) + 1e-12)
        ca, cb = (lo_a + hi_a) / 2, (lo_b + hi_b) / 2
        delta = ca - cb
        off = float(np.linalg.norm(delta - ax * float(delta @ ax)))
        return {"subject": si.instance_id, "object": oi.instance_id,
                "satisfied": bool(off <= consts.ALIGN_TOL * D),
                "measured": {"off_axis_offset_over_D": off / D},
                "note": ";".join(notes)}

    return {"subject": si.instance_id, "object": oi.instance_id,
            "satisfied": None, "measured": None, "note": f"unknown relation '{rel}'"}


def eval_relation(scene: Scene, binding: PartBinding, claim: dict) -> dict:
    rel = RELATION_ALIASES.get(claim["relation"], claim["relation"])
    subj = binding.resolve(claim["subject"])
    obj = binding.resolve(claim["object"])

    if subj is None or obj is None:
        missing = claim["subject"] if subj is None else claim["object"]
        return {**claim, "satisfied": None, "pairs": [],
                "note": f"unmeasurable: unresolved reference '{missing}'"}

    pairs = []
    for si in subj:
        for oi in obj:
            if si.instance_id == oi.instance_id:
                continue
            pairs.append(_eval_pair(scene, rel, si, oi, claim.get("axis")))

    judged = [p for p in pairs if p["satisfied"] is not None]
    if not judged:
        return {**claim, "satisfied": None, "pairs": pairs,
                "note": "unmeasurable: no measurable instance pair"}

    satisfied = all(p["satisfied"] for p in judged)   # 抽象引用 = 全部实例都要满足
    note = "" if len(judged) == len(pairs) else f"partial: {len(pairs)-len(judged)} pair(s) unmeasurable"
    return {**claim, "relation": rel, "satisfied": bool(satisfied),
            "pairs": pairs, "note": note}


def gf3_score(scene: Scene, binding: PartBinding, relations: list[dict]) -> dict:
    results = [eval_relation(scene, binding, c) for c in relations]
    evaluated = [r for r in results if r["satisfied"] is not None]
    n_sat = sum(1 for r in evaluated if r["satisfied"])
    return {
        "score": (n_sat / len(evaluated)) if evaluated else None,
        "n_claims": len(relations),
        "n_evaluated": len(evaluated),
        "n_satisfied": n_sat,
        "n_unmeasurable": len(results) - len(evaluated),
        "claims": results,
    }


# ============================================================ GF4

def _measure(scene: Scene, binding: PartBinding, ref: str, measure: str):
    """按 P0 的 measure 语义提取尺寸。约定（PROVISIONAL, 见 consts）:
    height=Z 边; length=水平长边; width=水平短边; area=水平投影面积;
    volume=AABB 体积; long=三边最大(替身对称 claims 用); diag=对角线"""
    insts = binding.resolve(ref)
    if insts is None:
        return None, f"unresolved reference '{ref}'"
    if len(insts) > 1:
        return None, f"ambiguous multi-instance reference '{ref}'"
    inst = insts[0]
    if not inst.geom_ids:
        return None, f"'{ref}' has no geoms"

    lo, hi = scene.world_aabb(inst.geom_ids)
    ex, ey, ez = (hi - lo).tolist()
    if min(ex, ey, ez) < 0 or max(ex, ey, ez) <= 1e-9:
        return None, f"degenerate extent for '{ref}'"

    val = {
        "height": ez,
        "length": max(ex, ey),
        "width": min(ex, ey),
        "area": ex * ey,
        "volume": ex * ey * ez,
        "long": max(ex, ey, ez),
        "diag": float(np.linalg.norm(hi - lo)),
    }.get(measure)
    if val is None:
        return None, f"unknown measure '{measure}'"
    return float(val), ""


def _sigma_from_tolerance(tolerance) -> float:
    if tolerance is None:
        return consts.SIGMA_R
    return math.log1p(float(tolerance))     # σ = ln(1+tol): 容差边界处得分 = 1/e


def _score_pair(scene, binding, subject, obj, measure, target, tolerance, name, source):
    va, note_a = _measure(scene, binding, subject, measure)
    vb, note_b = _measure(scene, binding, obj, measure)
    if va is None or vb is None or vb <= 1e-12 or va <= 1e-12:
        return {"name": name, "subject": subject, "object": obj, "measure": measure,
                "score": None, "measured": None,
                "note": f"unmeasurable: {note_a or note_b or 'zero dimension'}",
                "source": source}
    r_obs = va / vb
    sigma = _sigma_from_tolerance(tolerance)
    log_err = abs(math.log(r_obs / float(target)))
    return {"name": name, "subject": subject, "object": obj, "measure": measure,
            "score": math.exp(-log_err / sigma),
            "measured": {"r_obs": r_obs, "r_target": float(target),
                         "abs_log_error": log_err, "sigma": sigma,
                         "tolerance": tolerance},
            "note": "", "source": source}


def gf4_score(scene: Scene, binding: PartBinding, claims: list[dict]) -> dict:
    results = []
    for c in claims:
        src = c.get("source", "prompt")
        tol = c.get("tolerance")
        measure = c.get("measure", "long")

        if "parts" in c:                                   # 成组形
            parts = c["parts"]
            ratios = c.get("target_ratio", [1.0] * len(parts))
            ref_part, ref_ratio = parts[0], float(ratios[0])
            for p, r in zip(parts[1:], ratios[1:]):
                results.append(_score_pair(
                    scene, binding, p, ref_part, measure,
                    float(r) / ref_ratio, tol,
                    name=f"{p}_vs_{ref_part}_{measure}", source=src))
        else:                                              # 成对形
            results.append(_score_pair(
                scene, binding, c["subject"], c["object"], measure,
                c.get("target_ratio", 1.0), tol,
                name=f"{c['subject']}_vs_{c['object']}_{measure}", source=src))

    scored = [r["score"] for r in results if r["score"] is not None]
    return {
        "score": (float(np.mean(scored)) if scored else None),
        "n_claims": len(claims),
        "n_pairs": len(results),
        "n_evaluated": len(scored),
        "n_unmeasurable": len(results) - len(scored),
        "claims": results,
    }
