"""GF1-GF4 scorers: contract in, geometry out.

Deviation from answer2/task-2_08-16-p2.html, stated up front: the spec computes
GF1/GF2 with a frozen CLIP/SigLIP image-text encoder. No CLIP or torch is
available locally and Task-13-4 asks for a *geometry* verifier, so GF1/GF2 here
are deterministic 3D measurements against the same contract fields the text
branch would have consumed. GF3/GF4 follow the spec directly, including
GF4_r = exp(-|log(r_obs / r_target)| / sigma_r).

Every threshold is frozen here, before the run (plan section 03).
"""
import numpy as np
import bindings

# --- frozen thresholds --------------------------------------------------------
GF1_W_CONN = 0.6      # connectivity vs main-body volume fraction inside GF1
SYM_OK = 0.90         # mirror-symmetry score that still counts as "centred"
EVEN_CV = 0.10        # spacing coefficient of variation allowed by "evenly spaced"
DETECT_DELTA = 0.05   # drop vs the uuid's GT baseline that counts as a detection


# ------------------------------------------------------------------ GF1
def gf1(contract, g):
    n = max(1, g.n_components)
    score = GF1_W_CONN * (1.0 / n) + (1 - GF1_W_CONN) * g.b["main_volume_fraction"]
    return float(score), dict(n_components=n,
                              main_volume_fraction=round(g.b["main_volume_fraction"], 4),
                              why=f"{n} connected body/bodies; contract asks for one solid")


# ------------------------------------------------------------------ GF2
def _count_score(det, exp):
    return float(max(0.0, 1.0 - abs(det - exp) / float(max(1, exp))))


def _detect_part(spec, g):
    """(detected, expected, evidence) or None when the part has no detector."""
    kind = spec["det"]
    if kind == "none":
        return None
    if kind == "body":
        ok = g.b["volume_mm3"] > 0 and g.b["main_volume_fraction"] > 0.5
        return int(ok), 1, "main body present" if ok else "no dominant solid body"
    if kind == "cavity":
        c = g.cavities(spec.get("axis", 2), spec.get("frac"), spec.get("d"),
                       roundness=spec.get("roundness"))
        return len(c), spec["n"], f"{len(c)} enclosed cross-section ring(s) in the bound window"
    if kind == "through":
        c = [x for x in g.cavities(spec.get("axis", 2), d=spec.get("d")) if x["depth_frac"] > 0.8]
        return len(c), spec["n"], f"{len(c)} cavity/cavities spanning the full axis"
    if kind == "lobe":
        n = g.lobes(spec["frac"], prom=spec.get("prom"))
        return n, spec["n"], f"{n} radial lobe(s) on the bound section"
    if kind == "ring":
        ro, ri = g.ring(spec["frac"])
        ok = bool(ro and ri and ri > 0)
        return int(ok), 1, f"annular section outer {ro} inner {ri}" if ok else "no annular section"
    if kind == "hollow":
        w = g.wall(spec.get("frac", 0.5))
        return int(bool(w)), 1, f"wall thickness {w:.2f} mm" if w else "no hollow wall found"
    if kind == "notch":
        d = g.notch_depth(spec.get("frac", 0.5), spec.get("axis", 2))
        ok = bool(d and d >= spec.get("min_depth", 3.0))
        return int(ok), 1, f"deepest outline indentation {d:.2f} mm (needs >= {spec.get('min_depth', 3.0)})"
    raise ValueError(kind)


def gf2(contract, g, bind):
    checks = []
    for part in contract["required_parts"]:
        spec = bind["parts"].get(part["id"])
        if spec is None:
            checks.append(dict(part=part["id"], kind=part["kind"], status="unresolved",
                               why="no binding for this part"))
            continue
        got = _detect_part(spec, g)
        if got is None:
            checks.append(dict(part=part["id"], kind=part["kind"], status="unresolved",
                               why=spec.get("why", "")))
            continue
        det, exp, why = got
        checks.append(dict(part=part["id"], kind=part["kind"], status="scored",
                           score=_count_score(det, exp), detected=det, expected=exp,
                           detector=spec["det"], why=why))
    scored = [c["score"] for c in checks if c["status"] == "scored"]
    return (float(np.mean(scored)) if scored else None), dict(
        checks=checks, coverage=f"{len(scored)}/{len(contract['required_parts'])}")


# ------------------------------------------------------------------ GF3
def gf3(contract, g):
    out = []
    for rel in contract["part_relations"]:
        t = rel.lower()
        if "connected solid" in t or "one connected" in t or "one solid" in t or "remaining walls form" in t:
            ok = g.n_components == 1
            out.append(dict(rel=rel, status="scored", ok=ok,
                            why=f"n_components = {g.n_components} (claim: 1)"))
        elif any(k in t for k in ("centred", "centered", "symmetric", "mid-plane", "about the centre")):
            sx, sy = g.sym(0), g.sym(1)
            ok = max(sx, sy) >= SYM_OK
            out.append(dict(rel=rel, status="scored", ok=ok,
                            why=f"mirror symmetry x={sx:.3f} y={sy:.3f} (threshold {SYM_OK})"))
        elif any(k in t for k in ("evenly spaced", "evenly pitched", "equal spans", "evenly")):
            cav = g.cavities(2)
            if len(cav) >= 3:
                c = np.array([x["center"] for x in cav])
                axis = 0 if np.ptp(c[:, 0]) >= np.ptp(c[:, 1]) else 1
                v = np.sort(c[:, axis]); gaps = np.diff(v); gaps = gaps[gaps > 1e-6]
                cv = float(np.std(gaps) / np.mean(gaps)) if len(gaps) else 1.0
                ok = cv <= EVEN_CV
                out.append(dict(rel=rel, status="scored", ok=ok,
                                why=f"feature pitch CV = {cv:.3f} (threshold {EVEN_CV})"))
            else:
                out.append(dict(rel=rel, status="unresolved",
                                why=f"only {len(cav)} features detected, need 3 to test spacing"))
        elif "coaxial" in t or "common axis" in t or "on the part axis" in t:
            cav = g.cavities(2)
            if cav:
                c = np.array([x["center"] for x in cav])
                off = float(np.min(np.linalg.norm(c, axis=1)))
                diag = float(np.linalg.norm(g.b["extents"]))
                ok = off / diag < 0.05
                out.append(dict(rel=rel, status="scored", ok=ok,
                                why=f"nearest cavity axis offset {off:.2f} mm = {off/diag:.3f} of the bbox diagonal"))
            else:
                out.append(dict(rel=rel, status="unresolved", why="no axial cavity detected"))
        elif "monotonic" in t:
            a, b = g.span(0.02), g.span(0.98)
            ok = bool(a and b and b[0] >= a[0] - 1e-6 and b[1] >= a[1] - 1e-6)
            out.append(dict(rel=rel, status="scored", ok=ok,
                            why=f"section span {tuple(round(x,1) for x in a)} -> {tuple(round(x,1) for x in b)}"))
        elif any(k in t for k in ("attached", "fused", "stands on", "runs along", "stacked",
                                  "distributed on", "cut into", "cut through", "cut in",
                                  "pass through", "runs the full length", "enters from",
                                  "keeps its outer envelope", "are the two opposite faces")):
            ok = g.n_components == 1
            out.append(dict(rel=rel, status="scored", ok=ok,
                            why=f"attachment requires one body; n_components = {g.n_components}"))
        else:
            out.append(dict(rel=rel, status="unresolved", why="no predicate implemented for this claim"))
    scored = [r for r in out if r["status"] == "scored"]
    val = float(sum(1 for r in scored if r["ok"]) / len(scored)) if scored else None
    return val, dict(checks=out, coverage=f"{len(scored)}/{len(contract['part_relations'])}")


# ------------------------------------------------------------------ GF4
def gf4(contract, g, bind):
    rows = []
    for c in contract["proportion_claims"]:
        recipe = bind["claims"].get(c["claim"])
        target, sigma = float(c["target_ratio"]), float(c["tolerance"])
        if recipe is None:
            rows.append(dict(claim=c["claim"], status="unresolved", target=target,
                             why="no measurement recipe bound to this claim"))
            continue
        try:
            got = recipe(g)
        except Exception as exc:                       # measurement genuinely unavailable
            got = (None, f"measurement failed: {type(exc).__name__}")
        obs, why = got if isinstance(got, tuple) else (got, "")
        if obs is None or not np.isfinite(obs) or obs <= 0:
            rows.append(dict(claim=c["claim"], status="unresolved", target=target, why=why))
            continue
        rows.append(dict(claim=c["claim"], status="scored", target=target, sigma=sigma,
                         observed=float(obs), why=why,
                         score=float(np.exp(-abs(np.log(obs / target)) / sigma))))
    scored = [r["score"] for r in rows if r["status"] == "scored"]
    return (float(np.mean(scored)) if scored else None), dict(
        checks=rows, coverage=f"{len(scored)}/{len(contract['proportion_claims'])}")


# ------------------------------------------------------------------ detection
DIM_TO_DEFECT = {
    "GF1": "topology_break",
    "GF2": "part_deletion / silent_noop (missing feature)",
    "GF3": "part_displacement",
    "GF4": "proportion_scale",
}


def detect(profile, gt_profile, n_components=1):
    """Score a variant against its own uuid's GT baseline (plan section 03).

    Two rules are reported side by side:
      argmin  - plain "largest drop wins", the naive reading of the profile;
      gated   - P1-Gate first: a body that is no longer one connected solid is a
                topology failure, and its proportions are not meaningfully
                measurable, so GF1 takes precedence over a larger GF4 drop.
    """
    deltas = {}
    for d in ("GF1", "GF2", "GF3", "GF4"):
        a, b = profile.get(d), gt_profile.get(d)
        deltas[d] = None if (a is None or b is None) else round(a - b, 6)
    usable = {k: v for k, v in deltas.items() if v is not None}
    if not usable or min(usable.values()) > -DETECT_DELTA:
        return dict(dimension=None, defect="no defect above threshold", deltas=deltas,
                    gated_dimension=None, gated_defect="no defect above threshold")
    dim = min(usable, key=usable.get)
    gated = dim
    if n_components > 1 and (deltas.get("GF1") is not None and deltas["GF1"] <= -DETECT_DELTA):
        gated = "GF1"
    return dict(dimension=dim, defect=DIM_TO_DEFECT[dim], deltas=deltas,
                gated_dimension=gated, gated_defect=DIM_TO_DEFECT[gated])
