"""Measurement facade used by the frozen part/claim bindings.

One Geo wraps one variant mesh and exposes only geometric queries. It never sees
the GT mesh or the injection label.
"""
import numpy as np
import measure


class Geo:
    def __init__(self, mesh):
        self.mesh = mesh
        self.b = measure.basic(mesh)
        self._cav = {}
        self._sec = {}

    # --- bounding box ---------------------------------------------------------
    @property
    def X(self): return self.b["extents"][0]
    @property
    def Y(self): return self.b["extents"][1]
    @property
    def Z(self): return self.b["extents"][2]
    @property
    def L(self): return self.b["extents_sorted"][0]
    @property
    def W(self): return self.b["extents_sorted"][1]
    @property
    def H(self): return self.b["extents_sorted"][2]
    @property
    def n_components(self): return self.b["n_components"]

    # --- cavities -------------------------------------------------------------
    def cavities(self, axis=2, frac=None, d=None, region=None, roundness=None):
        if axis not in self._cav:
            self._cav[axis] = measure.cavities(self.mesh, axis)
        out = []
        for c in self._cav[axis]:
            if d and not (d[0] <= c["equiv_d"] <= d[1]):
                continue
            if frac and not any(frac[0] <= p <= frac[1] for p in c["planes"]):
                continue
            if roundness and c.get("roundness", 0) < roundness:
                continue
            if region:
                (x0, x1), (y0, y1) = region
                if not (x0 <= c["center"][0] <= x1 and y0 <= c["center"][1] <= y1):
                    continue
            out.append(c)
        return out

    def cav_d(self, axis=2, frac=None, d=None):
        c = self.cavities(axis, frac, d)
        return max((x["equiv_d"] for x in c), default=None)

    # --- sections -------------------------------------------------------------
    def span(self, frac, axis=2):
        key = (axis, round(frac, 4))
        if key not in self._sec:
            self._sec[key] = measure.section_span(self.mesh, axis, frac)
        return self._sec[key]

    def band(self, ratio=0.9, axis=2, ref=None):
        """Extent along `axis` over which the section is at least `ratio` as wide
        as the widest section (used for 'plate thickness' style claims)."""
        fr = np.linspace(0.01, 0.99, 40)
        spans = [(f, self.span(f, axis)) for f in fr]
        widths = [max(s) if s else 0.0 for _, s in spans]
        top = ref if ref else max(widths)
        keep = [f for (f, _), w in zip(spans, widths) if w >= ratio * top]
        if not keep:
            return None
        lo, hi = self.mesh.bounds[0][axis], self.mesh.bounds[1][axis]
        return (max(keep) - min(keep)) * (hi - lo)

    def wall(self, frac=0.5, axis=2):
        return measure.wall_thickness(self.mesh, axis, frac)

    def ring(self, frac=0.9, axis=2):
        return measure.ring_radii(self.mesh, axis, frac)

    def lobes(self, frac=0.5, axis=2, prom=None):
        old = measure.LOBE_PROM
        if prom is not None:
            measure.LOBE_PROM = prom
        try:
            return measure.lobe_count(self.mesh, axis, frac)
        finally:
            measure.LOBE_PROM = old

    def notch_depth(self, frac=0.5, axis=2):
        return measure.notch_depth(self.mesh, axis, frac)

    def notch_defect(self, frac=0.5, axis=2):
        """Convex deficiency of a cross-section: >0 means the outline is notched."""
        polys = measure._section(self.mesh, axis, self._coord(frac, axis))
        if not polys:
            return None
        p = max(polys, key=lambda q: q.area)
        hull = p.convex_hull.area
        return float((hull - p.area) / hull) if hull else 0.0

    def _coord(self, frac, axis):
        lo, hi = self.mesh.bounds[0][axis], self.mesh.bounds[1][axis]
        return lo + (hi - lo) * frac

    # --- misc -----------------------------------------------------------------
    def hole_pitch(self, axis=2, d=None, along=0):
        c = [x["center"] for x in self.cavities(axis, d=d)]
        if len(c) < 2:
            return None
        v = np.sort(np.array(c)[:, along])
        gaps = np.diff(v); gaps = gaps[gaps > 1e-6]
        return float(np.median(gaps)) if len(gaps) else None

    def hole_spread(self, axis=2, d=None, along=0):
        c = [x["center"] for x in self.cavities(axis, d=d)]
        if len(c) < 2:
            return None
        return float(np.ptp(np.array(c)[:, along]))

    def mean_abs_offset(self, axis=2, d=None, along=0):
        c = [x["center"] for x in self.cavities(axis, d=d)]
        if not c:
            return None
        return float(np.mean(np.abs(np.array(c)[:, along])))

    def sym(self, axis):
        return measure.mirror_symmetry(self.mesh, axis)
