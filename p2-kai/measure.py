"""Deterministic mesh measurements for the P2 geometry verifier.

Everything here reads ONE variant mesh (mm, CAD frame) and nothing else: no GT
mesh, no injection.json, no renders. The contract is the only reference, per
answer2/task-2_08-16-p2.html.
"""
import numpy as np
import trimesh

# --- frozen sampling constants -------------------------------------------------
Z_FRACTIONS = (0.02, 0.06, 0.12, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.88, 0.94, 0.98)
DEDUPE_MM = 1.5          # two cavity centres closer than this are the same feature
MIN_CAVITY_AREA = 1.0    # mm^2, drops tessellation slivers
LOBE_PROM = 0.15
SLIVER_FRAC = 1e-4        # components below this fraction of the largest are tessellation junk         # radial prominence (fraction of mean radius) for lobe peaks


def load(path):
    m = trimesh.load(path, force="mesh")
    m.merge_vertices()
    return m


def basic(mesh):
    comps = mesh.split(only_watertight=False)
    vols_all = [abs(float(c.volume)) for c in comps] or [abs(float(mesh.volume))]
    # drop tessellation slivers: cadquery STL exports can carry zero-volume shells
    big = max(vols_all) if vols_all else 0.0
    vols = [v for v in vols_all if v > SLIVER_FRAC * big] or [big]
    ext = mesh.extents
    order = np.argsort(ext)[::-1]
    return dict(
        n_components=int(len(vols)),
        main_volume_fraction=float(max(vols) / sum(vols)) if sum(vols) else 1.0,
        watertight=bool(mesh.is_watertight),
        euler=int(mesh.euler_number),
        genus=float((2 * (len(vols) or 1) - mesh.euler_number) / 2.0),
        volume_mm3=float(abs(mesh.volume)),
        area_mm2=float(mesh.area),
        extents=[float(x) for x in ext],
        extents_sorted=[float(ext[i]) for i in order],
        bbox_min=[float(x) for x in mesh.bounds[0]],
        bbox_max=[float(x) for x in mesh.bounds[1]],
        centroid=[float(x) for x in mesh.centroid],
        bbox_center=[float(x) for x in mesh.bounds.mean(axis=0)],
        convex_fill=float(abs(mesh.volume) / abs(mesh.convex_hull.volume)) if mesh.convex_hull.volume else 1.0,
    )


# world axes kept in the 2D frame, so section coordinates stay comparable across
# planes and across variants: axis 2 -> (x, y), axis 0 -> (y, z), axis 1 -> (x, z)
_KEEP = {0: (1, 2), 1: (0, 2), 2: (0, 1)}


def _to_2D(axis):
    """Rigid transform sending the cut plane to z=0 while keeping world axes."""
    T = np.zeros((4, 4)); T[3, 3] = 1.0
    u, v = _KEEP[axis]
    T[0, u] = 1.0
    T[1, v] = 1.0
    T[2, axis] = 1.0
    return T


def _section(mesh, axis, coord):
    """Return shapely polygons of the cross-section in world coordinates."""
    normal = np.zeros(3); normal[axis] = 1.0
    origin = mesh.bounds.mean(axis=0).copy(); origin[axis] = coord
    sec = mesh.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        return []
    planar, _ = sec.to_2D(to_2D=_to_2D(axis))
    return list(planar.polygons_full)


def sections(mesh, axis=2, fractions=Z_FRACTIONS):
    """Cross-sections along one axis: exteriors, interior rings, per plane."""
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    out = []
    for f in fractions:
        c = lo + (hi - lo) * f
        polys = _section(mesh, axis, c)
        rings = []
        for p in polys:
            for ring in p.interiors:
                from shapely.geometry import Polygon
                q = Polygon(ring)
                if q.area < MIN_CAVITY_AREA:
                    continue
                round_ = float(4 * np.pi * q.area / (q.length ** 2)) if q.length else 0.0
                rings.append(dict(center=[q.centroid.x, q.centroid.y], area=float(q.area),
                                  equiv_d=float(2 * np.sqrt(q.area / np.pi)), roundness=round_))
        out.append(dict(axis=axis, coord=float(c), frac=float(f),
                        n_exterior=len(polys),
                        exterior_area=float(sum(p.area for p in polys)),
                        rings=rings, polys=polys))
    return out


def cavities(mesh, axis=2):
    """Distinct interior cavities seen in the section stack along `axis`."""
    found = []
    for s in sections(mesh, axis):
        for r in s["rings"]:
            for f in found:
                dmin = min(f["equiv_d"], r["equiv_d"]); dmax = max(f["equiv_d"], r["equiv_d"])
                tol = max(DEDUPE_MM, 0.5 * dmin)
                same = (np.hypot(f["center"][0] - r["center"][0],
                                 f["center"][1] - r["center"][1]) < tol) and (dmax / dmin < 3.0)
                if same:
                    f["planes"].append(s["frac"]); f["coords"].append(s["coord"])
                    if r["equiv_d"] > f["equiv_d"]:
                        f["equiv_d"], f["roundness"] = r["equiv_d"], r["roundness"]
                    break
            else:
                found.append(dict(center=r["center"], equiv_d=r["equiv_d"],
                                  roundness=r["roundness"], planes=[s["frac"]], coords=[s["coord"]]))
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    span = (hi - lo) or 1.0
    for f in found:
        f["depth_frac"] = float((max(f["coords"]) - min(f["coords"])) / span)
        f["n_planes"] = len(f["planes"])
    return found


def max_exteriors(mesh, axis=2):
    """Largest number of disjoint solid islands seen in any cross-section."""
    return max([s["n_exterior"] for s in sections(mesh, axis)] or [1])


def lobe_count(mesh, axis=2, frac=0.5):
    """Count radial lobes (knurls / bumps / slots) on the outline of one section."""
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    polys = _section(mesh, axis, lo + (hi - lo) * frac)
    if not polys:
        return 0
    p = max(polys, key=lambda q: q.area)
    xy = np.asarray(p.exterior.coords)[:-1]
    c = xy.mean(axis=0)
    d = xy - c
    r = np.hypot(d[:, 0], d[:, 1])
    ang = np.arctan2(d[:, 1], d[:, 0])
    idx = np.argsort(ang)
    r = r[idx]
    if r.mean() <= 0:
        return 0
    rn = (r - r.mean()) / r.mean()
    peaks = 0
    n = len(rn)
    for i in range(n):
        if rn[i] > LOBE_PROM and rn[i] >= rn[(i - 1) % n] and rn[i] > rn[(i + 1) % n]:
            peaks += 1
    return int(peaks)


def wall_thickness(mesh, axis=2, frac=0.5):
    """Min gap between the outer boundary and the largest interior ring."""
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    polys = _section(mesh, axis, lo + (hi - lo) * frac)
    best = None
    for p in polys:
        for ring in p.interiors:
            from shapely.geometry import LinearRing
            d = p.exterior.distance(LinearRing(ring))
            best = d if best is None else min(best, d)
    return float(best) if best else None


def ring_radii(mesh, axis=2, frac=0.9):
    """Outer / inner equivalent radius of an annular cross-section."""
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    polys = _section(mesh, axis, lo + (hi - lo) * frac)
    if not polys:
        return None, None
    p = max(polys, key=lambda q: q.area)
    outer = np.sqrt((p.area + sum(_ring_area(r) for r in p.interiors)) / np.pi)
    inner = max([np.sqrt(_ring_area(r) / np.pi) for r in p.interiors] or [0.0])
    return float(outer), float(inner or 0.0)


def _ring_area(ring):
    from shapely.geometry import Polygon
    return Polygon(ring).area


def section_span(mesh, axis=2, frac=0.5):
    """Bounding size of the material at one height: (dx, dy)."""
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    polys = _section(mesh, axis, lo + (hi - lo) * frac)
    if not polys:
        return None
    xs, ys = [], []
    for p in polys:
        a, b, c, d = p.bounds
        xs += [a, c]; ys += [b, d]
    return float(max(xs) - min(xs)), float(max(ys) - min(ys))


def mirror_symmetry(mesh, axis, n=2000, seed=0):
    """1 = perfectly mirror-symmetric about the bbox mid-plane normal to `axis`."""
    pts, _ = trimesh.sample.sample_surface_even(mesh, n, seed=seed)
    if len(pts) == 0:
        return 0.0
    mid = mesh.bounds.mean(axis=0)[axis]
    ref = pts.copy(); ref[:, axis] = 2 * mid - ref[:, axis]
    d = trimesh.proximity.ProximityQuery(mesh).signed_distance(ref)
    diag = float(np.linalg.norm(mesh.extents)) or 1.0
    return float(np.exp(-np.mean(np.abs(d)) / (0.02 * diag)))


def profile_all(mesh):
    """One measurement bundle reused by GF1-GF4."""
    m = basic(mesh)
    m["cavities_z"] = cavities(mesh, 2)
    m["cavities_x"] = cavities(mesh, 0)
    m["cavities_y"] = cavities(mesh, 1)
    m["max_exteriors_z"] = max_exteriors(mesh, 2)
    m["max_exteriors_x"] = max_exteriors(mesh, 0)
    m["lobes_mid"] = lobe_count(mesh, 2, 0.5)
    m["lobes_low"] = lobe_count(mesh, 2, 0.1)
    m["wall_thickness"] = wall_thickness(mesh, 2, 0.5)
    m["ring_outer"], m["ring_inner"] = ring_radii(mesh, 2, 0.9)
    m["span_top"] = section_span(mesh, 2, 0.95)
    m["span_bottom"] = section_span(mesh, 2, 0.05)
    m["span_mid"] = section_span(mesh, 2, 0.5)
    return m


def notch_depth(mesh, axis=2, frac=0.5):
    """Depth (mm) of the deepest indentation in one cross-section outline."""
    lo, hi = mesh.bounds[0][axis], mesh.bounds[1][axis]
    polys = _section(mesh, axis, lo + (hi - lo) * frac)
    if not polys:
        return 0.0
    p = max(polys, key=lambda q: q.area)
    diff = p.convex_hull.difference(p)
    pieces = list(getattr(diff, "geoms", [diff])) if not diff.is_empty else []
    best = 0.0
    for piece in pieces:
        if piece.is_empty or piece.area < MIN_CAVITY_AREA:
            continue
        x0, y0, x1, y1 = piece.bounds
        best = max(best, min(x1 - x0, y1 - y0))
    return float(best)
