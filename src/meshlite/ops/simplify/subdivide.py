"""``SubdivideOperation`` — increase triangle density by splitting edges.

Exposes the FULL ``SubdivideSettings`` struct from meshlib. Skips only
pointer/bitset types (maintainRegion, newVerts, notFlippable, region).
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
class SubdivideOperation(Operation):
    """Subdivide mesh by splitting long edges."""

    id = "simplify.subdivide"
    label = "Subdivide"
    category = "Mesh Edit"
    description = "Increase triangle density by splitting edges"
    icon = "\uea72"
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("max_edge_len", "float", "Max edge length", default=0.0,
              min=0.0, max=100.0, step=0.01,
              help="Split edges longer than this (0 = half of current average)"),
        Param("max_edge_splits", "int", "Max edge splits", default=10000,
              min=100, max=10000000, step=1000,
              help="Safety limit on number of edge splits"),
        Param("smooth_mode", "bool", "Smooth mode", default=False,
              help="Smooth new vertex positions (interpolated) rather than just splitting"),
        Param("subdivide_border", "bool", "Subdivide border edges", default=True,
              help="Also split edges on the mesh boundary"),

        Param("show_advanced", "bool", "Show advanced", default=False),
        Param("max_tri_aspect_ratio", "float", "Max triangle aspect ratio", default=0.0,
              min=0.0, max=1000.0, step=1.0,
              visible_if=_adv,
              help="Also split triangles with aspect ratio above this (0 = disabled)"),
        Param("max_angle_change_after_flip", "float", "Max angle change after flip (rad)", default=3.14159,
              min=0.0, max=6.28, step=0.1,
              visible_if=_adv,
              help="Max dihedral angle change allowed by edge flips after subdivision"),
        Param("max_deviation_after_flip", "float", "Max deviation after flip", default=1.0,
              min=0.0, max=100.0, step=0.1,
              visible_if=_adv,
              help="Max surface deviation allowed by edge flips"),
        Param("critical_aspect_ratio_flip", "float", "Critical aspect ratio for flip", default=1000.0,
              min=1.0, max=100000.0, step=100.0,
              visible_if=_adv,
              help="Force flip edges in triangles with aspect ratio above this"),
        Param("curvature_priority", "float", "Curvature priority", default=0.0,
              min=0.0, max=1.0, step=0.1,
              visible_if=_adv,
              help="Priority for splitting edges in high-curvature areas (0 = uniform)"),
        Param("min_sharp_dihedral_angle", "float", "Min sharp dihedral angle (rad)", default=0.524,
              min=0.0, max=3.14159, step=0.05,
              visible_if=_adv,
              help="Edges with dihedral angle below this are considered sharp (~30° default)"),
        Param("project_on_original_mesh", "bool", "Project on original mesh", default=False,
              visible_if=_adv,
              help="Project new vertices back onto the original surface"),
        Param("max_splittable_tri_aspect_ratio", "float", "Max splittable tri aspect ratio", default=0.0,
              min=0.0, max=10000.0, step=10.0,
              visible_if=_adv,
              help="Don't split triangles with aspect ratio above this (0 = unlimited)"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("SubdivideOperation requires a mesh")

        mr = mesh.mr
        max_len = float(params.get("max_edge_len", 0.0))
        if max_len <= 0:
            max_len = mr.averageEdgeLength() * 0.5
        faces_before = mr.topology.numValidFaces()

        ctx.report_progress(0.05, f"subdividing (max_edge={max_len:.4f})...")

        ss = _mrm.SubdivideSettings()
        ss.maxEdgeLen = max_len
        ss.maxEdgeSplits = int(params.get("max_edge_splits", 10000))
        ss.smoothMode = bool(params.get("smooth_mode", False))
        ss.subdivideBorder = bool(params.get("subdivide_border", True))

        mtar = float(params.get("max_tri_aspect_ratio", 0.0))
        ss.maxTriAspectRatio = mtar

        ss.maxAngleChangeAfterFlip = float(params.get("max_angle_change_after_flip", 3.14159))
        ss.maxDeviationAfterFlip = float(params.get("max_deviation_after_flip", 1.0))
        ss.criticalAspectRatioFlip = float(params.get("critical_aspect_ratio_flip", 1000.0))
        ss.curvaturePriority = float(params.get("curvature_priority", 0.0))
        ss.minSharpDihedralAngle = float(params.get("min_sharp_dihedral_angle", 0.524))
        ss.projectOnOriginalMesh = bool(params.get("project_on_original_mesh", False))
        mstar = float(params.get("max_splittable_tri_aspect_ratio", 0.0))
        ss.maxSplittableTriAspectRatio = mstar if mstar > 0 else FLT_MAX

        _mrm.subdivideMesh(mr, ss)

        ctx.report_progress(1.0, "done")
        faces_after = mr.topology.numValidFaces()
        return OperationResult(
            mesh=mesh,
            info={"faces_before": faces_before, "faces_after": faces_after},
            message=f"Subdivided: {faces_before} → {faces_after} faces",
        )
