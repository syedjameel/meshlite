"""``RemeshOperation`` — uniform edge-length remeshing.

Exposes the FULL ``RemeshSettings`` struct from meshlib. Skips only
pointer/bitset types (notFlippable, region).
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
class RemeshOperation(Operation):
    """Remesh to uniform edge length."""

    id = "simplify.remesh"
    label = "Remesh"
    category = "Mesh Edit"
    description = "Remesh to achieve uniform edge lengths"
    icon = "\uebd4"
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("target_edge_len", "float", "Target edge length", default=0.0,
              min=0.0, max=100.0, step=0.01,
              help="Target edge length (0 = auto from current average)"),
        Param("final_relax_iters", "int", "Final relax iterations", default=0,
              min=0, max=50, step=1,
              help="Number of Laplacian smoothing passes after remeshing"),
        Param("final_relax_no_shrinkage", "bool", "Relax without shrinkage", default=False,
              help="Prevent volume shrinkage during final relaxation"),
        Param("use_curvature", "bool", "Curvature-adaptive", default=False,
              help="Adapt edge length based on local curvature (shorter in curved areas)"),
        Param("frozen_boundary", "bool", "Frozen boundary", default=False,
              help="Do not modify boundary edges"),

        Param("show_advanced", "bool", "Show advanced", default=False),
        Param("max_angle_change_after_flip", "float", "Max angle change after flip (rad)", default=0.524,
              min=0.0, max=3.14159, step=0.05,
              visible_if=_adv,
              help="Max dihedral angle change allowed by edge flips (~30° default)"),
        Param("max_bd_shift", "float", "Max boundary shift", default=0.0,
              min=0.0, max=1000.0, step=0.1,
              visible_if=_adv,
              help="Max shift of boundary vertices (0 = unlimited)"),
        Param("max_edge_splits", "int", "Max edge splits", default=10000000,
              min=1000, max=100000000, step=100000,
              visible_if=_adv,
              help="Safety limit on total number of edge splits"),
        Param("max_splittable_tri_aspect_ratio", "float", "Max splittable tri aspect ratio", default=0.0,
              min=0.0, max=10000.0, step=10.0,
              visible_if=_adv,
              help="Don't split triangles with aspect ratio above this (0 = unlimited)"),
        Param("project_on_original_mesh", "bool", "Project on original mesh", default=False,
              visible_if=_adv,
              help="Project new vertices back onto the original surface"),
        Param("pack_mesh", "bool", "Pack mesh after remesh", default=False,
              visible_if=_adv,
              help="Compact vertex/face arrays after remeshing"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("RemeshOperation requires a mesh")

        mr = mesh.mr
        target = float(params.get("target_edge_len", 0.0))
        if target <= 0:
            target = mr.averageEdgeLength()
        faces_before = mr.topology.numValidFaces()

        ctx.report_progress(0.05, f"remeshing (target={target:.4f})...")

        rs = _mrm.RemeshSettings()
        rs.targetEdgeLen = target
        rs.finalRelaxIters = int(params.get("final_relax_iters", 0))
        rs.finalRelaxNoShrinkage = bool(params.get("final_relax_no_shrinkage", False))
        rs.useCurvature = bool(params.get("use_curvature", False))
        rs.frozenBoundary = bool(params.get("frozen_boundary", False))
        rs.maxAngleChangeAfterFlip = float(params.get("max_angle_change_after_flip", 0.524))
        mbs = float(params.get("max_bd_shift", 0.0))
        rs.maxBdShift = mbs if mbs > 0 else FLT_MAX
        rs.maxEdgeSplits = int(params.get("max_edge_splits", 10000000))
        mstar = float(params.get("max_splittable_tri_aspect_ratio", 0.0))
        rs.maxSplittableTriAspectRatio = mstar if mstar > 0 else FLT_MAX
        rs.projectOnOriginalMesh = bool(params.get("project_on_original_mesh", False))
        rs.packMesh = bool(params.get("pack_mesh", False))

        _mrm.remesh(mr, rs)

        ctx.report_progress(1.0, "done")
        faces_after = mr.topology.numValidFaces()
        return OperationResult(
            mesh=mesh,
            info={"faces_before": faces_before, "faces_after": faces_after,
                  "target_edge_len": target},
            message=f"Remeshed: {faces_before} → {faces_after} faces (edge len ≈ {target:.4f})",
        )
