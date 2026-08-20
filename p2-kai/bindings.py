"""Frozen binding of contract items to geometric detectors.

P2 (answer2/task-2_08-16-p2.html) assumes the P1 Initialization Gate has already
bound each required part to something measurable ("use the part masks ... already
bound by the Gate"). This file is that binding, written once per contract from the
contract text alone, before any variant was scored. It never references a GT mesh,
a GT measurement or an injection label, so the same table applies to gt and to all
injected variants of a uuid.

Part detector kinds
    cavity  count enclosed cross-section rings (holes, pockets, slots, bores)
    through cavity that spans the whole axis (open tube / through hole)
    lobe    radial bumps or slots on a round outline (knurls)
    notch   indentation of at least `min_depth` mm in a cross-section outline
    ring    annular cross-section present
    hollow  a wall of finite thickness around an interior void
    body    the main solid exists
    none    no geometric signature at this verifier's resolution -> unresolved
"""

D = dict  # shorthand

BIND = {
# ---------------------------------------------------------------- knurled disc
"09d46e9b-ab70-ccc4-c1fc-57a7e39602bb": D(
    parts=D(
        base_disc=D(det="body"),
        knurl_ring=D(det="lobe", frac=0.09, prom=0.003, n=40),
        drive_tabs=D(det="none", why="tabs are unioned inside the disc envelope: no free surface"),
        blind_holes=D(det="cavity", axis=2, frac=(0.5, 1.0), d=(4, 9), n=4),
        rim_chamfer=D(det="none", why="decoration"),
    ),
    claims={
        "disc diameter to thickness": lambda g: (g.X / g.Z, f"bbox X/Z = {g.X:.2f}/{g.Z:.2f} mm"),
        "hub radius to outer radius": lambda g: (None, "hub is not a free surface in the solid"),
        "hole circle offset to outer radius": lambda g: (
            (g.mean_abs_offset(2, d=(4, 9), along=0) or 0) / (g.X / 2),
            f"mean |x| of blind holes {g.mean_abs_offset(2, d=(4,9), along=0):.2f} / outer radius {g.X/2:.2f} mm"
            if g.mean_abs_offset(2, d=(4, 9), along=0) else "no blind holes detected"),
    }),
# ---------------------------------------------------------------- bearing block
"3753d810-9ce6-a122-fac6-fd64e414f887": D(
    parts=D(
        base_block=D(det="body"),
        rib_plus_y=D(det="none", why="rib is flush with the block envelope: no isolated signature"),
        rib_minus_y=D(det="none", why="rib is flush with the block envelope: no isolated signature"),
        central_bore=D(det="cavity", axis=0, frac=(0.3, 1.0), d=(8, 18), n=1),
        top_pocket=D(det="cavity", axis=2, frac=(0.7, 1.0), d=(10, 30), n=1),
        end_chamfers=D(det="none", why="decoration"),
    ),
    claims={
        "block length to width": lambda g: (g.span(0.05)[0] / g.span(0.05)[1],
                                            f"base slab span {g.span(0.05)[0]:.1f}/{g.span(0.05)[1]:.1f} mm"),
        "block width to height": lambda g: (g.span(0.05)[1] / g.Z,
                                            f"base slab width {g.span(0.05)[1]:.1f} / bbox Z {g.Z:.1f} mm"),
        "bore depth to block length": lambda g: (
            (max([c["depth_frac"] for c in g.cavities(0, d=(8, 18))], default=0) or None) and
            max(c["depth_frac"] for c in g.cavities(0, d=(8, 18))),
            "bore depth fraction along X" if g.cavities(0, d=(8, 18)) else "no bore cavity detected"),
    }),
# ---------------------------------------------------------------- tool handle
"447aae45-d4fa-82ea-8fe8-e6572bf9f0bf": D(
    parts=D(
        grip=D(det="body"),
        transition=D(det="none", why="taper blends into the grip: no separable signature"),
        shaft=D(det="none", why="shaft is part of the same revolved envelope"),
        knurl_slots=D(det="lobe", frac=0.19, prom=0.04, n=12),
        through_hole=D(det="through", axis=2, d=(4, 9), n=1),
    ),
    claims={
        "overall length to grip diameter": lambda g: (g.Z / g.span(0.05)[0],
                                                      f"bbox Z {g.Z:.1f} / grip span {g.span(0.05)[0]:.1f} mm"),
        "grip diameter to shaft diameter": lambda g: (g.span(0.05)[0] / g.span(0.9)[0],
                                                      f"grip span {g.span(0.05)[0]:.1f} / shaft span {g.span(0.9)[0]:.1f} mm"),
        "grip length to overall length": lambda g: (_grip_frac(g), "axial height where the section is still grip-wide"),
    }),
# ---------------------------------------------------------------- clamp jaw
"87e570d9-0ca6-6676-f215-d34f9a7be557": D(
    parts=D(
        base_plate=D(det="body"),
        top_rib=D(det="none", why="rib is flush with the plate envelope"),
        internal_ribs=D(det="none", why="webs are interior to the plate envelope"),
        relief_pocket=D(det="cavity", axis=2, frac=(0.6, 1.0), d=(10, 40), n=1),
        mounting_holes=D(det="cavity", axis=2, frac=(0.3, 1.0), d=(4, 8), n=3),
        edge_treatment=D(det="none", why="decoration"),
    ),
    claims={
        "jaw width to height": lambda g: (g.X / g.Y, f"bbox X/Y = {g.X:.1f}/{g.Y:.1f} mm"),
        "jaw height to thickness": lambda g: (g.Y / (g.band(0.9, 2) or 1e9),
                                              f"bbox Y {g.Y:.1f} / full-width slab {g.band(0.9,2):.1f} mm"),
        "hole pitch to jaw width": lambda g: ((g.hole_pitch(2, d=(4, 8), along=0) or 0) / g.X,
                                              f"median hole pitch {g.hole_pitch(2, d=(4,8), along=0)} / bbox X {g.X:.1f} mm"),
    }),
# ---------------------------------------------------------------- sleeve
"8ef0010b-ab19-d328-5ff9-aa49d94cd201": D(
    parts=D(
        outer_box=D(det="body"),
        wall_shell=D(det="hollow", frac=0.5),
        open_ends=D(det="through", axis=2, d=(20, 1e9), n=1),
    ),
    claims={
        "length to width": lambda g: (g.X / g.Y, f"bbox X/Y = {g.X:.1f}/{g.Y:.1f} mm"),
        "width to height": lambda g: (g.Y / g.Z, f"bbox Y/Z = {g.Y:.1f}/{g.Z:.1f} mm"),
        "length to wall thickness": lambda g: ((g.X / g.wall(0.5)) if g.wall(0.5) else None,
                                               f"bbox X {g.X:.1f} / measured wall {g.wall(0.5)} mm"),
    }),
# ---------------------------------------------------------------- flanged tray
"940297b1-cfb4-7311-6db4-51fc2e6fb070": D(
    parts=D(
        tray_shell=D(det="hollow", frac=0.5),
        mount_holes=D(det="cavity", axis=2, d=(4, 6), n=4),
        vent_slots=D(det="cavity", axis=2, d=(6.2, 9), n=3),
        under_ribs=D(det="none", why="ribs are flush with the tray envelope"),
        perimeter_chamfer=D(det="none", why="decoration"),
    ),
    claims={
        "outer width to outer depth": lambda g: (g.X / g.Y, f"bbox X/Y = {g.X:.1f}/{g.Y:.1f} mm"),
        "outer width to plate thickness": lambda g: (g.X / (g.band(0.9, 2) or 1e9),
                                                     f"bbox X {g.X:.1f} / full-width slab {g.band(0.9,2):.1f} mm"),
        "mount hole pitch X to pitch Y": lambda g: (
            (g.hole_spread(2, d=(4, 6), along=0) or 0) / (g.hole_spread(2, d=(4, 6), along=1) or 1e9),
            f"hole pattern spread {g.hole_spread(2, d=(4,6), along=0)} x {g.hole_spread(2, d=(4,6), along=1)} mm"),
    }),
# ---------------------------------------------------------------- sector bracket
"bfa02503-3b85-4d34-e74f-2b4a4432192f": D(
    parts=D(
        revolved_body=D(det="body"),
        side_notch=D(det="notch", axis=2, frac=0.4, min_depth=3.0),
        cbore_hole=D(det="cavity", axis=2, frac=(0.5, 1.0), d=(6, 16), n=1),
        edge_treatment=D(det="none", why="decoration"),
    ),
    claims={
        "total height to block width": lambda g: (None, "revolve axis is outside the body: radial width not recoverable"),
        "outer radius to inner radius": lambda g: (None, "sector: revolve axis not recoverable from the mesh"),
        "counterbore head diameter to hole diameter": lambda g: _cbore_ratio(g),
    }),
# ---------------------------------------------------------------- annular plate
"c4db4bf8-b95c-eabf-6def-ecdfc43ece89": D(
    parts=D(
        base_plate=D(det="body"),
        cross_ribs=D(det="none", why="ribs are flush with the plate underside envelope"),
        annular_frame=D(det="ring", frac=0.75),
        ring_holes=D(det="cavity", axis=2, frac=(0.4, 0.95), d=(3, 6), n=11),
        mount_holes=D(det="cavity", axis=2, frac=(0.0, 0.35), d=(4, 6.5), n=4),
    ),
    claims={
        "plate side to plate thickness": lambda g: (g.X / (g.band(0.9, 2) or 1e9),
                                                    f"bbox X {g.X:.1f} / full-width slab {g.band(0.9,2):.1f} mm"),
        "frame outer radius to inner radius": lambda g: _ring_ratio(g, 0.75),
        "frame outer diameter to plate side": lambda g: (
            (2 * g.ring(0.75)[0] / g.X) if g.ring(0.75)[0] else None,
            f"ring outer d {2*(g.ring(0.75)[0] or 0):.1f} / bbox X {g.X:.1f} mm"),
    }),
# ---------------------------------------------------------------- lamp housing
"de3f2362-65dd-6f36-4e02-6f03556ab24d": D(
    parts=D(
        lofted_body=D(det="body"),
        vent_slot=D(det="notch", axis=2, frac=0.5, min_depth=8.0),
        mount_holes=D(det="cavity", axis=2, frac=(0.7, 1.0), d=(3, 8), n=4),
        top_chamfer=D(det="none", why="decoration"),
    ),
    claims={
        "height to top cover width": lambda g: (g.Z / g.span(0.98)[0],
                                                f"bbox Z {g.Z:.1f} / top span {g.span(0.98)[0]:.1f} mm"),
        "top cover width to depth": lambda g: (g.span(0.98)[0] / g.span(0.98)[1],
                                               f"top span {g.span(0.98)[0]:.1f}/{g.span(0.98)[1]:.1f} mm"),
        "top width to base diameter": lambda g: (g.span(0.98)[0] / g.span(0.01)[0],
                                                 f"top span {g.span(0.98)[0]:.1f} / base span {g.span(0.01)[0]:.1f} mm"),
    }),
# ---------------------------------------------------------------- square tube
"eacaf3f2-8f03-7af3-90c0-a6301ffd2d4d": D(
    parts=D(
        square_tube=D(det="hollow", frac=0.5),
        circular_channel=D(det="cavity", axis=2, d=(25, 40), roundness=0.9, n=1),
        top_holes=D(det="cavity", axis=2, d=(5, 12), n=2),
        internal_rib=D(det="none", why="rib is interior and fused to the wall"),
    ),
    claims={
        "length to outer width": lambda g: (g.Z / g.X, f"bbox Z/X = {g.Z:.1f}/{g.X:.1f} mm"),
        "outer width to wall thickness": lambda g: ((g.X / g.wall(0.5)) if g.wall(0.5) else None,
                                                    f"bbox X {g.X:.1f} / measured wall {g.wall(0.5)} mm"),
        "channel diameter to outer width": lambda g: ((g.cav_d(2, d=(25, 40)) or 0) / g.X,
                                                      f"channel d {g.cav_d(2, d=(25,40))} / bbox X {g.X:.1f} mm"),
    }),
}


# --- helpers used by a couple of claim recipes ---------------------------------
def _grip_frac(g):
    """Fraction of the height over which the section is still grip-diameter wide."""
    import numpy as np
    top = g.span(0.05)
    if not top:
        return None
    fr = np.linspace(0.01, 0.99, 60)
    wide = [f for f in fr if (g.span(f) or (0, 0))[0] >= 0.7 * top[0]]
    return float(max(wide) - min(wide) + 1.0 / 60) if wide else None


def _cbore_ratio(g):
    ds = sorted((c["equiv_d"] for c in g.cavities(2, frac=(0.5, 1.0), d=(4, 20))), reverse=True)
    if len(ds) < 2:
        return None, f"counterbore step not resolvable ({len(ds)} cavity diameter(s) found)"
    return ds[0] / ds[1], f"cavity diameters {ds[0]:.2f} / {ds[1]:.2f} mm"


def _ring_ratio(g, frac):
    ro, ri = g.ring(frac)
    if not ro or not ri:
        return None, "no annular cross-section found"
    return ro / ri, f"ring radii {ro:.2f} / {ri:.2f} mm"
