"""``DecimateOperation`` — reduce triangle count via edge collapse.

Exposes the FULL ``DecimateSettings`` struct from meshlib. Internal/pointer
params (bdVerts, edgesToCollapse, notFlippable, partFaces, region, twinMap,
vertForms) are skipped — they're C++ output/bitset types the UI can't
represent. Every user-tunable scalar, bool, and enum is exposed.

Advanced params hidden behind a "Show advanced" toggle so the default view
is clean.
"""

# Architecture note: ops/ is allowed to import meshlib directly for complex
# Settings struct construction. See CONTRIBUTING.md for layer rules.

from __future__ import annotations

from typing import Any

import meshlib.mrmeshpy as _mrm

from meshlite.domain.mesh_data import MeshData

from ..base import (
    FLT_MAX,
    Operation,
    OperationContext,
    OperationError,
    OperationResult,
    Param,
    ParamSchema,
)
from ..registry import register_operation


def _adv(v):
    return v.get("show_advanced", False)


@register_operation
class DecimateOperation(Operation):
    """Reduce mesh triangle count by collapsing edges."""

    id = "simplify.decimate"
    label = "Decimate"
    category = "Mesh Edit"
    description = "Reduce triangle count while preserving shape"
    icon = "\uebd2"
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        # --- Primary params (always visible) ---
        Param("ratio", "float", "Target ratio", default=0.5,
              min=0.01, max=0.99, step=0.05,
              help="Fraction of original faces to keep (0.5 = half)"),
        Param("strategy", "enum", "Strategy", default="MinimizeError",
              choices=("MinimizeError", "ShortestEdgeFirst"),
              help="MinimizeError: collapse edges that introduce least error. "
                   "ShortestEdgeFirst: collapse shortest edges first"),
        Param("max_error", "float", "Max error", default=0.001,
              min=0.0, max=10.0, step=0.001,
              help="Maximum geometric deviation from original surface"),
        Param("max_triangle_aspect_ratio", "float", "Max triangle aspect ratio", default=20.0,
              min=1.0, max=100.0, step=1.0,
              help="Refuse collapses that would create triangles with aspect ratio above this"),
        Param("optimize_vertex_pos", "bool", "Optimize vertex positions", default=True,
              help="After collapsing an edge, move the remaining vertex to minimize error"),

        # --- Advanced params ---
        Param("show_advanced", "bool", "Show advanced", default=False),

        Param("max_deleted_vertices", "int", "Max deleted vertices", default=2147483647,
              min=0, max=2147483647, step=1000,
              visible_if=_adv,
              help="Maximum number of vertices to delete"),
        Param("max_edge_len", "float", "Max edge length", default=0.0,
              min=0.0, max=1000.0, step=0.1,
              visible_if=_adv,
              help="Do not collapse edges longer than this (0 = unlimited)"),
        Param("max_bd_shift", "float", "Max boundary shift", default=0.0,
              min=0.0, max=1000.0, step=0.1,
              visible_if=_adv,
              help="Maximum shift of boundary vertices (0 = unlimited)"),
        Param("max_angle_change", "float", "Max angle change (rad)", default=-1.0,
              min=-1.0, max=3.14159, step=0.1,
              visible_if=_adv,
              help="Max change in dihedral angle at edges (-1 = disabled)"),
        Param("critical_tri_aspect_ratio", "float", "Critical tri aspect ratio", default=10000.0,
              min=1.0, max=100000.0, step=100.0,
              visible_if=_adv,
              help="Triangles with aspect ratio above this are removed regardless"),
        Param("tiny_edge_length", "float", "Tiny edge length", default=-1.0,
              min=-1.0, max=10.0, step=0.01,
              visible_if=_adv,
              help="Edges shorter than this are collapsed first (-1 = auto)"),
        Param("stabilizer", "float", "Stabilizer", default=0.001,
              min=0.0, max=1.0, step=0.0001,
              visible_if=_adv,
              help="Small value added to prevent numerical instability"),
        Param("touch_bd_verts", "bool", "Touch boundary vertices", default=True,
              visible_if=_adv,
              help="Allow collapsing edges that touch boundary vertices"),
        Param("touch_near_bd_edges", "bool", "Touch near-boundary edges", default=True,
              visible_if=_adv,
              help="Allow collapsing edges near the boundary"),
        Param("collapse_near_not_flippable", "bool", "Collapse near not-flippable", default=False,
              visible_if=_adv,
              help="Allow collapsing edges near not-flippable edges"),
        Param("angle_weighted_dist_to_plane", "bool", "Angle-weighted distance to plane", default=False,
              visible_if=_adv,
              help="Use angle-weighted distance to plane for error metric"),
        Param("pack_mesh", "bool", "Pack mesh after decimation", default=False,
              visible_if=_adv,
              help="Compact vertex/face arrays after decimation (removes gaps)"),
        Param("decimate_between_parts", "bool", "Decimate between parts", default=True,
              visible_if=_adv,
              help="Allow decimation across part boundaries"),
        Param("subdivide_parts", "int", "Subdivide parts", default=1,
              min=1, max=64, step=1,
              visible_if=_adv,
              help="Number of sub-parts for parallel decimation"),
        Param("min_faces_in_part", "int", "Min faces in part", default=0,
              min=0, max=100000, step=100,
              visible_if=_adv,
              help="Minimum faces per part for partitioned decimation"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("DecimateOperation requires a mesh")

        mr = mesh.mr
        faces_before = mr.topology.numValidFaces()
        ratio = float(params.get("ratio", 0.5))

        ctx.report_progress(0.05, f"decimating {faces_before} faces...")

        ds = _mrm.DecimateSettings()

        # Strategy
        strat_str = params.get("strategy", "MinimizeError")
        ds.strategy = (
            _mrm.DecimateStrategy.ShortestEdgeFirst
            if strat_str == "ShortestEdgeFirst"
            else _mrm.DecimateStrategy.MinimizeError
        )

        # Primary
        ds.maxDeletedFaces = int(faces_before * (1.0 - ratio))
        ds.maxError = float(params.get("max_error", 0.001))
        ds.maxTriangleAspectRatio = float(params.get("max_triangle_aspect_ratio", 20.0))
        ds.optimizeVertexPos = bool(params.get("optimize_vertex_pos", True))

        # Advanced
        mdv = params.get("max_deleted_vertices", 2147483647)
        ds.maxDeletedVertices = int(mdv) if mdv is not None else 2147483647

        mel = float(params.get("max_edge_len", 0.0))
        ds.maxEdgeLen = mel if mel > 0 else FLT_MAX

        mbs = float(params.get("max_bd_shift", 0.0))
        ds.maxBdShift = mbs if mbs > 0 else FLT_MAX

        ds.maxAngleChange = float(params.get("max_angle_change", -1.0))
        ds.criticalTriAspectRatio = float(params.get("critical_tri_aspect_ratio", 10000.0))
        ds.tinyEdgeLength = float(params.get("tiny_edge_length", -1.0))
        ds.stabilizer = float(params.get("stabilizer", 0.001))
        ds.touchBdVerts = bool(params.get("touch_bd_verts", True))
        ds.touchNearBdEdges = bool(params.get("touch_near_bd_edges", True))
        ds.collapseNearNotFlippable = bool(params.get("collapse_near_not_flippable", False))
        ds.angleWeightedDistToPlane = bool(params.get("angle_weighted_dist_to_plane", False))
        ds.packMesh = bool(params.get("pack_mesh", False))
        ds.decimateBetweenParts = bool(params.get("decimate_between_parts", True))
        ds.subdivideParts = int(params.get("subdivide_parts", 1))
        ds.minFacesInPart = int(params.get("min_faces_in_part", 0))

        result = _mrm.decimateMesh(mr, ds)

        ctx.report_progress(1.0, "done")
        faces_after = mr.topology.numValidFaces()
        return OperationResult(
            mesh=mesh,
            info={
                "faces_before": faces_before, "faces_after": faces_after,
                "faces_deleted": result.facesDeleted, "verts_deleted": result.vertsDeleted,
                "error_introduced": result.errorIntroduced,
            },
            message=f"Decimated: {faces_before} → {faces_after} faces ({result.facesDeleted} removed, err={result.errorIntroduced:.6f})",
        )
