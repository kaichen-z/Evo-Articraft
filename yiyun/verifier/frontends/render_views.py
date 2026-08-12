"""Render the default pose from eight fixed viewpoints for A4 evidence."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def render_eight_views(model: Any, output_dir: Path | str, *, size: int = 512) -> list[Path]:
    """Render a model with authored materials from eight azimuths.

    Geometry is assembled from the same SDK visual solids used by the compiler;
    no reference image is introduced.  The camera uses a fixed elevation and
    45-degree azimuth steps, making the evidence reproducible.
    """
    import trimesh
    from sdk import TestContext

    ctx = TestContext(model)
    meshes = []
    for part in model.parts:
        part_tf = ctx._world_tfs().get(str(part.name))  # SDK FK result
        if part_tf is None:
            continue
        for visual in part.visuals:
            mesh = _geometry_mesh(visual.geometry, getattr(part, "assets", None))
            mesh.apply_transform(_origin_matrix(visual.origin))
            mesh.apply_transform(part_tf)
            rgba = _material_rgba(visual.material, model)
            mesh.visual.face_colors = [int(round(255 * value)) for value in rgba]
            meshes.append(mesh)
    if not meshes:
        raise RuntimeError("model has no renderable visual geometry")
    combined = trimesh.util.concatenate(meshes)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    return _matplotlib_render(combined, output, size=size)


def _geometry_mesh(geometry: Any, assets: Any):
    import trimesh
    from sdk import Box, Cylinder, Mesh, Sphere

    if isinstance(geometry, Box):
        return trimesh.creation.box(extents=geometry.size)
    if isinstance(geometry, Cylinder):
        return trimesh.creation.cylinder(radius=geometry.radius, height=geometry.length, sections=32)
    if isinstance(geometry, Sphere):
        return trimesh.creation.icosphere(subdivisions=2, radius=geometry.radius)
    if not isinstance(geometry, Mesh):
        raise TypeError(f"unsupported geometry {type(geometry).__name__}")
    if geometry.source_geometry is not None:
        mesh = _geometry_mesh(geometry.source_geometry, assets)
        if geometry.source_transform is not None:
            mesh.apply_transform(geometry.source_transform)
    else:
        from sdk._core.v0.assets import resolve_mesh_path

        path = Path(geometry.materialized_path) if geometry.materialized_path else resolve_mesh_path(
            geometry.filename, assets=assets
        )
        mesh = trimesh.load_mesh(path, force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            raise TypeError(f"expected Trimesh at {path}")
        mesh = mesh.copy()
    if geometry.scale is not None:
        mesh.apply_scale(geometry.scale)
    return mesh


def _origin_matrix(origin: Any):
    import trimesh

    matrix = trimesh.transformations.euler_matrix(*origin.rpy, axes="sxyz")
    matrix[:3, 3] = origin.xyz
    return matrix


def _material_rgba(material: Any, model: Any) -> tuple[float, float, float, float]:
    if isinstance(material, str):
        material = next(
            (candidate for candidate in getattr(model, "materials", ()) if candidate.name == material),
            None,
        )
    rgba = getattr(material, "rgba", None)
    if rgba is None:
        return (0.68, 0.70, 0.74, 1.0)
    values = tuple(float(value) for value in rgba)
    return values if len(values) == 4 else (*values, 1.0)


def _matplotlib_render(mesh: Any, output: Path, *, size: int) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    bounds = mesh.bounds
    centre = tuple((float(bounds[0][i]) + float(bounds[1][i])) / 2 for i in range(3))
    diagonal = math.dist(tuple(bounds[0]), tuple(bounds[1]))
    if diagonal <= 0:
        raise RuntimeError("non-positive render bounds")
    vertices = mesh.vertices[mesh.faces]
    colours = mesh.visual.face_colors.astype(float) / 255.0
    if len(vertices) > 120_000:
        step = math.ceil(len(vertices) / 120_000)
        vertices, colours = vertices[::step], colours[::step]
    paths: list[Path] = []
    for index in range(8):
        figure = plt.figure(figsize=(size / 100, size / 100), dpi=100, facecolor="#f5f5f5")
        axis = figure.add_subplot(111, projection="3d", proj_type="ortho")
        collection = Poly3DCollection(
            vertices, facecolors=colours, edgecolors="none", linewidths=0,
        )
        axis.add_collection3d(collection)
        half = diagonal * 0.58
        axis.set_xlim(centre[0] - half, centre[0] + half)
        axis.set_ylim(centre[1] - half, centre[1] + half)
        axis.set_zlim(centre[2] - half, centre[2] + half)
        axis.set_box_aspect((1, 1, 1))
        axis.view_init(elev=24, azim=index * 45)
        axis.set_axis_off()
        axis.set_facecolor("#f5f5f5")
        figure.subplots_adjust(0, 0, 1, 1)
        target = output / f"view_{index:02d}.png"
        figure.savefig(target, dpi=100, facecolor=figure.get_facecolor())
        plt.close(figure)
        paths.append(target)
    return paths
