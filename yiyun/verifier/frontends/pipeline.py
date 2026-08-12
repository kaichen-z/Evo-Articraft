"""Turn real Articraft assets and frozen prompt contracts into A1-A6 signals.

The static AST reader and deterministic name matcher in this package are adapted
from Wanglin He's ``evo-verifier`` so that the ``yiyun/`` submission remains
self-contained. Geometry checks call the installed Articraft SDK and execute the
generated model only when A6 is requested.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from ..consts import DEFAULT, Consts
from ..contracts.schema import new_contract
from ..metrics import a1, a2, a3, a4, a5, a6
from ..types import MetricResult
from .matching import assign, similarity
from .static_asset import Asset, find_model_py, load_asset


def load_prompt_contract(
    path: Path | str,
    *,
    extension_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load Wanglin's frozen contract and map explicit claims to A1-A6 fields."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    parts = [p for p in payload.get("expected_parts", ()) if p.get("source") == "explicit"]
    joints = [j for j in payload.get("expected_joints", ()) if j.get("source") == "explicit"]
    contract = new_contract(
        asset_id=str(payload.get("record_id", "")),
        required_parts=[
            {
                "id": str(part["name"]),
                "category": str(part["name"]),
                # ``null`` means that the Prompt requires the category to be
                # present but does not specify an exact instance count.
                "count": int(part["count"]) if part.get("count") is not None else None,
                "source": "prompt",
                "evidence_text": str(part.get("quote", "")),
            }
            for part in parts
        ],
        required_movables=[
            {
                "id": str(joint["child"]),
                "count": int(joint["count"]) if joint.get("count") is not None else None,
                "source": "prompt",
                "evidence_text": str(joint.get("quote", "")),
            }
            for joint in joints
            if joint.get("kind") != "fixed"
        ],
        advisory_inferences=[
            requirement
            for requirement in (*payload.get("expected_parts", ()), *payload.get("expected_joints", ()))
            if requirement.get("source") != "explicit"
        ],
    )
    if extension_path and Path(extension_path).exists():
        extension = json.loads(Path(extension_path).read_text(encoding="utf-8"))
        for key in (
            "category",
            "required_interfaces",
            "appearance_claims",
            "category_scale",
            "spatial_relations",
            "advisory_inferences",
        ):
            if key in extension:
                contract[key] = extension[key]
    return contract, payload


def static_signals(
    asset: Asset, frozen: Mapping[str, Any], contract: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Produce real A1-A3 and partial A4 signals from parsed ``model.py``."""
    part_names = tuple(asset.parts)
    moving = {joint.child for joint in asset.movable() if joint.child}
    explicit_parts = [
        part for part in frozen.get("expected_parts", ()) if part.get("source") == "explicit"
    ]
    explicit_joints = [
        joint
        for joint in frozen.get("expected_joints", ())
        if joint.get("source") == "explicit" and joint.get("kind") != "fixed"
    ]

    matched_required_parts: list[str] = []
    actual_part_counts: dict[str, int] = {}
    type_scores: list[float] = []
    matched_asset_parts: set[str] = set()
    part_assignment = assign(
        [str(expected["name"]) for expected in explicit_parts],
        part_names,
    )
    for index, expected in enumerate(explicit_parts):
        name = str(expected["name"])
        count = expected.get("count")
        wanted = int(count) if count is not None else 1
        found = part_assignment[index]
        actual_part_counts[name] = len(found)
        if len(found) >= wanted:
            matched_required_parts.append(name)
        matched_asset_parts.update(found)
        type_scores.append(
            sum(similarity(name, candidate) for candidate in found[:wanted]) / wanted
            if found else 0.0
        )

    matched_movables: list[str] = []
    matched_movable_counts: dict[str, int] = {}
    matched_moving_parts: set[str] = set()
    joint_assignment = assign(
        [str(expected["child"]) for expected in explicit_joints],
        part_names,
    )
    for index, expected in enumerate(explicit_joints):
        name = str(expected["child"])
        count = expected.get("count")
        wanted = int(count) if count is not None else 1
        found = joint_assignment[index]
        found_moving = [candidate for candidate in found if candidate in moving]
        if len(found_moving) >= wanted:
            matched_movables.append(name)
        matched_movable_counts[name] = len(found_moving)
        matched_moving_parts.update(found_moving)

    unreadable_joint_fields = sorted(
        {
            field
            for joint in asset.articulations
            for field in joint.unreadable
            if field in {"child", "kind"}
        }
    )
    missing_movable = len(matched_movables) < len(explicit_joints)
    missing_part = len(matched_required_parts) < len(explicit_parts)
    part_name_unreadable = any(note.startswith("part name unresolved:") for note in asset.notes)

    interface_results = _static_interface_results(asset, (contract or {}).get("required_interfaces") or [])
    diagonal = asset.diagonal()
    return {
        "matched_required_movables": matched_movables,
        "matched_required_movable_counts": matched_movable_counts,
        "actual_movable_ids": sorted(moving),
        "spurious_movable_ids": sorted(moving - matched_moving_parts),
        "matched_required_parts": matched_required_parts,
        "matched_required_interfaces": [
            item["id"] for item in interface_results if item["matched"]
        ],
        "interface_results": interface_results,
        "interface_measurement_partial": bool(interface_results),
        "actual_part_counts": actual_part_counts,
        "type_match_score": sum(type_scores) / len(type_scores) if type_scores else 0.0,
        "unmatched_part_names": sorted(set(part_names) - matched_asset_parts),
        "actual_scale_m": diagonal,
        # An unreadable declaration is a tool limitation, not evidence that the
        # asset omitted a required part/joint. Abstain only when it could alter
        # a currently missing requirement.
        "semantic_match_failed": bool(missing_movable and unreadable_joint_fields),
        "part_match_failed": bool(missing_part and part_name_unreadable),
        "unreadable_joint_fields": unreadable_joint_fields,
        "static_parser_complete": asset.complete,
        "static_parser_notes": list(asset.notes),
    }


def sdk_a6_signals(model_path: Path | str, *, overlap_tol: float = 0.001) -> dict[str, Any]:
    """Measure A6 with real meshes in the default pose using Articraft SDK checks."""
    module = _load_generated_model(Path(model_path))
    object_model = module.object_model
    from sdk import TestContext

    original_report = None
    run_tests = getattr(module, "run_tests", None)
    if callable(run_tests):
        try:
            original_report = run_tests()
        except Exception:
            original_report = None

    ctx = TestContext(object_model)
    for allowance in getattr(original_report, "allowed_overlaps", ()) or ():
        try:
            ctx.allow_overlap(
                object_model.get_part(allowance.link_a),
                object_model.get_part(allowance.link_b),
                elem_a=allowance.elem_a,
                elem_b=allowance.elem_b,
                reason=allowance.reason,
            )
        except Exception:
            pass

    isolated_ok = ctx.fail_if_isolated_parts()
    overlap_ok = ctx.fail_if_parts_overlap_in_current_pose(
        overlap_tol=overlap_tol,
        overlap_volume_tol=1e-10,
    )
    report = ctx.report()
    overlap_failures = [f for f in report.failures if f.name.startswith("fail_if_parts_overlap")]
    isolated_failures = [f for f in report.failures if f.name.startswith("fail_if_isolated_parts")]
    depths = [
        float(value)
        for failure in overlap_failures
        for value in re.findall(r"min_depth=([0-9.eE+-]+)", failure.details)
    ]
    pairs = [
        {"a": a, "b": b, "depth_m": depth}
        for failure in overlap_failures
        for (a, b), depth in _pairs_and_depths(failure.details)
    ]
    floating_parts: list[str] = []
    gaps: list[float] = []
    for failure in isolated_failures:
        for literal in re.findall(r"floating group (\[[^]]*\])", failure.details):
            try:
                floating_parts.extend(str(name) for name in ast.literal_eval(literal))
            except (SyntaxError, ValueError):
                pass
        gaps.extend(float(value) for value in re.findall(r"approx_gap=([0-9.eE+-]+)m", failure.details))
    floating_parts = sorted(set(floating_parts))
    part_count = max(1, len(getattr(object_model, "parts", ())))
    part_volumes, volume_errors = _part_solid_volumes(object_model)
    total_volume = sum(part_volumes.values())
    detached_volume = sum(part_volumes.get(name, 0.0) for name in floating_parts)
    volume_complete = not volume_errors and total_volume > 0
    detached_ratio = (
        detached_volume / total_volume
        if volume_complete
        else (0.0 if isolated_ok else max(1, len(floating_parts)) / part_count)
    )
    diagonal = _world_diagonal(ctx, object_model)
    return {
        "object_diagonal_m": diagonal,
        "unexpected_penetration_m": max(depths, default=0.0),
        "detached_volume_ratio": min(1.0, detached_ratio),
        "unsupported_gap_m": max(gaps, default=0.0),
        "penetrating_pairs": pairs,
        "detached_parts": floating_parts,
        "floating_parts": floating_parts,
        "allowed_overlap_ids": [],
        "a6_measurement_notes": {
            "overlap_ok": overlap_ok,
            "isolated_ok": isolated_ok,
            "overlap_tol_m": overlap_tol,
            "unsupported_gap_available": isolated_ok or bool(gaps),
            "detached_ratio_is_part_count_proxy": not volume_complete,
            "volume_measurement": "sum-of-authored-solid-volumes" if volume_complete else "part-count-fallback",
            "volume_errors": volume_errors,
            "part_volumes_m3": part_volumes,
            "detached_volume_m3": detached_volume if volume_complete else None,
        },
    }


def run_asset(
    model_path: Path | str,
    *,
    contract_path: Path | str | None = None,
    extension_path: Path | str | None = None,
    a4_signals_path: Path | str | None = None,
    include_a6: bool = True,
    consts: Consts = DEFAULT,
) -> dict[str, MetricResult]:
    """Run the currently supported real frontends and all A1-A6 heads."""
    model_path = Path(model_path)
    asset = load_asset(model_path)
    if contract_path:
        contract, frozen = load_prompt_contract(contract_path, extension_path=extension_path)
    else:
        contract, frozen = new_contract(asset_id=asset.record_id), {}
        if extension_path and Path(extension_path).exists():
            extension = json.loads(Path(extension_path).read_text(encoding="utf-8"))
            for key in (
                "category", "required_interfaces", "appearance_claims", "category_scale",
                "spatial_relations", "advisory_inferences",
            ):
                if key in extension:
                    contract[key] = extension[key]
    signals = static_signals(asset, frozen, contract)
    if a4_signals_path and Path(a4_signals_path).exists():
        signals.update(json.loads(Path(a4_signals_path).read_text(encoding="utf-8")))
    if include_a6:
        try:
            signals.update(sdk_a6_signals(model_path))
        except Exception as exc:
            signals["geometry_query_failed"] = True
            signals["geometry_query_error"] = f"{type(exc).__name__}: {exc}"
    if contract.get("spatial_relations"):
        try:
            signals.update(sdk_a5_signals(model_path, contract))
        except Exception as exc:
            signals["relation_query_failed"] = True
            signals["relation_query_error"] = f"{type(exc).__name__}: {exc}"
    return {
        module.METRIC: module.score(signals, contract, consts)
        for module in (a1, a2, a3, a4, a5, a6)
    }


def find_record_model(data_dir: Path | str, record_id: str) -> Path:
    return find_model_py(data_dir, record_id)


def _load_generated_model(path: Path) -> ModuleType:
    name = f"yiyun_generated_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _world_diagonal(ctx: Any, object_model: Any) -> float:
    boxes = [ctx.part_world_aabb(part) for part in object_model.parts]
    boxes = [box for box in boxes if box is not None]
    if not boxes:
        raise RuntimeError("no world AABBs available")
    low = [min(float(box[0][axis]) for box in boxes) for axis in range(3)]
    high = [max(float(box[1][axis]) for box in boxes) for axis in range(3)]
    diagonal = math.dist(low, high)
    if diagonal <= 0:
        raise RuntimeError("non-positive object diagonal")
    return diagonal


def _pairs_and_depths(details: str) -> list[tuple[tuple[str, str], float]]:
    pattern = re.compile(
        r"pair=\('([^']+)','([^']+)'\).*?min_depth=([0-9.eE+-]+)"
    )
    return [((a, b), float(depth)) for a, b, depth in pattern.findall(details)]


_INTERFACE_WORDS = {
    "hinge": ("hinge", "barrel", "leaf", "pin"),
    "pivot": ("pivot", "pin", "boss", "collar"),
    "axle": ("axle", "shaft", "spindle", "pin"),
    "bearing": ("bearing", "bushing", "bush", "sleeve", "collar"),
    "bushing": ("bushing", "bush", "sleeve", "collar"),
    "rail": ("rail", "runner", "track", "slide"),
    "guide": ("guide", "rail", "runner", "track", "channel"),
    "slot": ("slot", "groove", "channel"),
    "collar": ("collar", "sleeve", "boss"),
    "bracket": ("bracket", "cheek", "yoke", "support"),
    "mount": ("mount", "bracket", "plate", "boss"),
    "contact": ("contact", "pad", "seat", "stop"),
}


def _static_interface_results(asset: Asset, requirements: list[dict]) -> list[dict[str, Any]]:
    """Name-level physical-interface evidence; deliberately marked partial.

    The model source exposes named visual solids, so this can prove that an
    explicit rail/hinge/bracket-like solid was authored.  It cannot prove from
    names alone that the solid has a mechanically valid shape; callers retain
    partial coverage for that reason.
    """
    all_names: list[tuple[str, str]] = []
    for part in asset.parts.values():
        all_names.append((part.name, part.name))
        all_names.extend((shape.name, part.name) for shape in part.shapes if shape.name)
    results: list[dict[str, Any]] = []
    for requirement in requirements:
        interface_type = str(requirement.get("interface_type", ""))
        words = _INTERFACE_WORDS.get(interface_type, (interface_type,))
        moving_match = assign([str(requirement.get("moving_part", ""))], asset.parts)[0]
        support_names = [str(value) for value in requirement.get("support_parts", ())]
        support_matches = {
            candidate
            for candidates in assign(support_names, asset.parts).values()
            for candidate in candidates
        }
        relevant_parts = set(moving_match) | support_matches
        named_solids = sorted(
            name for name, owner in all_names
            if (not relevant_parts or owner in relevant_parts)
            and any(word in name.lower().replace("-", "_") for word in words)
        )
        connected_joint = any(
            joint.child in moving_match
            and (not support_matches or joint.parent in support_matches)
            for joint in asset.articulations
        )
        results.append({
            "id": str(requirement.get("id", "")),
            "matched": bool(named_solids and connected_joint),
            "named_interface_geometry": named_solids,
            "moving_part_matches": moving_match,
            "support_part_matches": sorted(support_matches),
            "joint_connects_parties": connected_joint,
            "measurement": "named-solid-plus-joint",
        })
    return results


def sdk_a5_signals(model_path: Path | str, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Measure directly representable A5 relations from default-pose geometry."""
    module = _load_generated_model(Path(model_path))
    object_model = module.object_model
    from sdk import TestContext

    ctx = TestContext(object_model)
    parts = {str(part.name): part for part in object_model.parts}
    boxes = {name: ctx.part_world_aabb(part) for name, part in parts.items()}
    diagonal = _world_diagonal(ctx, object_model)
    results: list[dict[str, Any]] = []
    for relation in contract.get("spatial_relations") or []:
        subject_matches = assign([str(relation.get("subject", ""))], parts)[0]
        object_names = [str(value) for value in relation.get("objects", ())]
        object_matches = [assign([name], parts)[0] for name in object_names]
        item: dict[str, Any] = {
            "id": str(relation.get("id", "")),
            "subject_matches": subject_matches,
            "object_matches": object_matches,
        }
        if not subject_matches or any(not matches for matches in object_matches):
            item["measurement_error"] = "semantic part match missing"
            results.append(item)
            continue
        measurements = [
            _measure_relation(
                str(relation.get("relation", "")), boxes[subject],
                [boxes[name] for matches in object_matches for name in matches], diagonal,
            )
            for subject in subject_matches if boxes.get(subject) is not None
        ]
        for component in ("position", "orientation", "side", "neighborhood"):
            values = [
                float(component_value)
                for measurement in measurements
                if (component_value := measurement.get(component)) is not None
            ]
            if values:
                item[component] = sum(values) / len(values)
        item["measurement"] = "default-pose-world-aabb"
        results.append(item)
    return {"relation_results": results}


def _measure_relation(
    relation: str, subject: Any, objects: list[Any], diagonal: float
) -> dict[str, float]:
    if subject is None or not objects or any(obj is None for obj in objects):
        return {}
    def centre(box: Any) -> tuple[float, float, float]:
        return tuple((float(box[0][i]) + float(box[1][i])) / 2 for i in range(3))  # type: ignore[return-value]
    sc = centre(subject)
    oc = [centre(obj) for obj in objects]
    tol = max(1e-9, 0.02 * diagonal)
    gap = min(_aabb_distance(subject, obj) for obj in objects)
    nearby = math.exp(-gap / tol)
    axis_sign = {
        "right_of": (0, 1), "left_of": (0, -1),
        "in_front_of": (1, 1), "behind": (1, -1),
        "above": (2, 1), "below": (2, -1),
    }
    if relation in axis_sign:
        axis, sign = axis_sign[relation]
        delta = sign * (sc[axis] - oc[0][axis])
        score = 1.0 / (1.0 + math.exp(-delta / tol))
        return {"position": score, "side": score}
    if relation == "between" and len(oc) >= 2:
        a, b = oc[0], oc[1]
        ab = tuple(b[i] - a[i] for i in range(3))
        denom = sum(value * value for value in ab)
        if denom <= 1e-18:
            return {"position": 0.0}
        t = sum((sc[i] - a[i]) * ab[i] for i in range(3)) / denom
        closest = tuple(a[i] + max(0.0, min(1.0, t)) * ab[i] for i in range(3))
        distance = math.dist(sc, closest)
        return {"position": math.exp(-distance / max(tol, math.sqrt(denom) * 0.15)) if 0 <= t <= 1 else 0.0}
    if relation in {"inside", "contains", "surrounds"}:
        inner, outer = (subject, objects[0]) if relation == "inside" else (objects[0], subject)
        margins = [min(float(inner[0][i]) - float(outer[0][i]), float(outer[1][i]) - float(inner[1][i])) for i in range(3)]
        return {"position": min(1.0, max(0.0, min(margins) / tol + 1.0))}
    if relation in {"adjacent_to", "attached_to", "at_end_of"}:
        return {"position": nearby, "neighborhood": nearby}
    if relation in {"centered_on", "aligned_with"}:
        distance = math.dist(sc, oc[0])
        return {"position": math.exp(-distance / max(tol, 0.1 * diagonal))}
    if relation == "overlaps":
        return {"neighborhood": _aabb_iou(subject, objects[0])}
    return {}


def _aabb_distance(a: Any, b: Any) -> float:
    squared = 0.0
    for axis in range(3):
        delta = max(0.0, float(b[0][axis]) - float(a[1][axis]), float(a[0][axis]) - float(b[1][axis]))
        squared += delta * delta
    return math.sqrt(squared)


def _aabb_iou(a: Any, b: Any) -> float:
    overlap = 1.0
    for axis in range(3):
        overlap *= max(0.0, min(float(a[1][axis]), float(b[1][axis])) - max(float(a[0][axis]), float(b[0][axis])))
    va = math.prod(float(a[1][i]) - float(a[0][i]) for i in range(3))
    vb = math.prod(float(b[1][i]) - float(b[0][i]) for i in range(3))
    union = va + vb - overlap
    return overlap / union if union > 0 else 0.0


def _part_solid_volumes(object_model: Any) -> tuple[dict[str, float], list[str]]:
    """Measure authored solid volume per rigid part.

    Collision solids are preferred when explicitly supplied; otherwise visual
    solids are used, matching the SDK compiler's collision-from-visual path.
    Volumes of authored solids are summed within a part.  This is exact for
    non-overlapping primitives/watertight meshes and reports an error instead
    of silently assigning volume to unreadable meshes.
    """
    volumes: dict[str, float] = {}
    errors: list[str] = []
    for part in getattr(object_model, "parts", ()):
        items = list(getattr(part, "collisions", ()) or getattr(part, "visuals", ()) or ())
        subtotal = 0.0
        complete = True
        for item in items:
            try:
                subtotal += _solid_volume(item.geometry, getattr(part, "assets", None))
            except Exception as exc:
                complete = False
                errors.append(f"{part.name}/{getattr(item, 'name', None) or '?'}: {type(exc).__name__}: {exc}")
        if complete and subtotal > 0:
            volumes[str(part.name)] = subtotal
    return volumes, errors


def _solid_volume(geometry: Any, assets: Any) -> float:
    from sdk import Box, Cylinder, Mesh, Sphere

    if isinstance(geometry, Box):
        return abs(math.prod(float(value) for value in geometry.size))
    if isinstance(geometry, Cylinder):
        return math.pi * float(geometry.radius) ** 2 * abs(float(geometry.length))
    if isinstance(geometry, Sphere):
        return 4.0 * math.pi * abs(float(geometry.radius)) ** 3 / 3.0
    if not isinstance(geometry, Mesh):
        raise TypeError(f"unsupported geometry {type(geometry).__name__}")
    if geometry.source_geometry is not None:
        volume = _solid_volume(geometry.source_geometry, assets)
        if geometry.source_transform is not None:
            matrix = geometry.source_transform
            determinant = (
                matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
                - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
                + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
            )
            volume *= abs(float(determinant))
        if geometry.scale is not None:
            volume *= abs(math.prod(float(value) for value in geometry.scale))
        return volume
    from sdk._core.v0.assets import resolve_mesh_path
    import trimesh

    path = Path(geometry.materialized_path) if geometry.materialized_path else resolve_mesh_path(
        geometry.filename, assets=assets
    )
    mesh = trimesh.load_mesh(path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or not mesh.is_watertight:
        raise ValueError(f"mesh is not a watertight solid: {path}")
    if geometry.scale is not None:
        mesh = mesh.copy()
        mesh.apply_scale(geometry.scale)
    volume = abs(float(mesh.volume))
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError(f"mesh has non-positive volume: {path}")
    return volume
