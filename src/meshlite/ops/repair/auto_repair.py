"""``AutoRepairOperation`` — comprehensive mesh repair pipeline.

Runs three repair steps sequentially:
1. ``fixMultipleEdges`` — fixes non-manifold edges
2. ``fixMeshDegeneracies`` — fixes degenerate triangles, tiny edges, etc.
3. ``fixSelfIntersections`` — fixes self-intersecting faces

All parameters from ``FixMeshDegeneraciesParams`` and
``FixSelfIntersectionSettings`` are exposed.
"""

# Architecture note: ops/ is allowed to import meshlib directly for complex
# Settings struct construction. See CONTRIBUTING.md for layer rules.

from __future__ import annotations

import logging
from typing import Any

import meshlib.mrmeshpy as _mrm

from meshlite.domain.mesh_data import MeshData

from ..base import (
    Operation,
    OperationCanceled,
    OperationContext,
    OperationError,
    OperationResult,
    Param,
    ParamSchema,
)
from ..registry import register_operation

_LOGGER = logging.getLogger("meshlite.ops.repair")

def _adv(v):
    return v.get("show_advanced", False)


@register_operation
class AutoRepairOperation(Operation):
    """Comprehensive mesh repair: fix edges, degeneracies, and self-intersections."""

    id = "repair.auto_repair"
    label = "Auto Repair"
    category = "Repair"
    description = "Fix non-manifold edges, degenerate triangles, and self-intersections"
    icon = "\uebcf"  # codicon-wand
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        # Steps to run
        Param("fix_multiple_edges", "bool", "Fix non-manifold edges", default=True,
              help="Remove duplicate/non-manifold edges"),
        Param("fix_degeneracies", "bool", "Fix degeneracies", default=True,
              help="Fix degenerate triangles (tiny, flat, or extreme aspect ratio)"),
        Param("fix_self_intersections", "bool", "Fix self-intersections", default=True,
              help="Detect and fix self-intersecting faces"),
        Param("si_approach", "enum", "Self-intersection approach", default="Local (Relax)",
              choices=("Local (Relax)", "Local (CutAndFill)", "Voxel-based (aggressive)"),
              help="Local methods fix in-place. Voxel-based converts entire mesh to/from "
                   "distance field — more aggressive but changes topology. Use Voxel-based "
                   "when Local fails.",
              visible_if=lambda v: v.get("fix_self_intersections", True)),
        Param("si_voxel_size", "float", "SI voxel size", default=0.0,
              min=0.0, max=10.0, step=0.01,
              help="Voxel resolution (0 = auto from avg edge length)",
              visible_if=lambda v: v.get("fix_self_intersections", True) and "Voxel" in v.get("si_approach", "")),

        # FixMeshDegeneraciesParams
        Param("show_advanced", "bool", "Show advanced", default=False),
        Param("degen_critical_tri_aspect_ratio", "float", "Critical triangle aspect ratio",
              default=10000.0, min=1.0, max=100000.0, step=100.0,
              visible_if=_adv,
              help="Triangles with aspect ratio above this are fixed"),
        Param("degen_max_angle_change", "float", "Max angle change (rad)",
              default=1.047, min=0.0, max=3.14159, step=0.1,
              visible_if=_adv,
              help="Maximum dihedral angle change during degeneracy fix (~60° default)"),
        Param("degen_max_deviation", "float", "Max deviation",
              default=0.0, min=0.0, max=10.0, step=0.01,
              visible_if=_adv,
              help="Maximum surface deviation during repair (0 = unlimited)"),
        Param("degen_stabilizer", "float", "Stabilizer",
              default=1e-6, min=0.0, max=0.01, step=1e-7,
              visible_if=_adv,
              help="Small value for numerical stability during degeneracy fix"),
        Param("degen_tiny_edge_length", "float", "Tiny edge length",
              default=0.0, min=0.0, max=10.0, step=0.001,
              visible_if=_adv,
              help="Collapse edges shorter than this (0 = auto)"),

        # FixSelfIntersectionSettings
        Param("si_method", "enum", "Self-intersection method", default="Relax",
              choices=("Relax", "CutAndFill"),
              visible_if=_adv,
              help="Relax: move vertices apart. CutAndFill: cut and re-triangulate"),
        Param("si_relax_iterations", "int", "SI relax iterations",
              default=5, min=1, max=100, step=1,
              visible_if=_adv,
              help="Number of relaxation iterations for self-intersection fix"),
        Param("si_subdivide_edge_len", "float", "SI subdivide edge length",
              default=0.0, min=0.0, max=10.0, step=0.01,
              visible_if=_adv,
              help="Subdivide edges before fixing (0 = no subdivision)"),
        Param("si_max_expand", "int", "SI max expand",
              default=3, min=0, max=20, step=1,
              visible_if=_adv,
              help="Maximum expansion distance for self-intersection fix region"),
        Param("si_touch_is_intersection", "bool", "Touch is intersection",
              default=True,
              visible_if=_adv,
              help="Treat touching (but not intersecting) faces as intersections"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("AutoRepairOperation requires a mesh")

        mr = mesh.mr
        steps_done = []
        partial_failure = False

        # Step 1: Fix non-manifold edges
        if params.get("fix_multiple_edges", True):
            ctx.report_progress(0.05, "fixing non-manifold edges...")
            if ctx.is_canceled():
                raise OperationCanceled()
            _mrm.fixMultipleEdges(mr)
            steps_done.append("fixMultipleEdges")

        # Step 2: Fix degeneracies
        if params.get("fix_degeneracies", True):
            ctx.report_progress(0.3, "fixing degeneracies...")
            if ctx.is_canceled():
                raise OperationCanceled()

            dp = _mrm.FixMeshDegeneraciesParams()
            dp.criticalTriAspectRatio = float(params.get("degen_critical_tri_aspect_ratio", 10000.0))
            dp.maxAngleChange = float(params.get("degen_max_angle_change", 1.047))
            dp.maxDeviation = float(params.get("degen_max_deviation", 0.0))
            dp.stabilizer = float(params.get("degen_stabilizer", 1e-6))
            dp.tinyEdgeLength = float(params.get("degen_tiny_edge_length", 0.0))
            _mrm.fixMeshDegeneracies(mr, dp)
            steps_done.append("fixDegeneracies")

        # Step 3: Fix self-intersections
        if params.get("fix_self_intersections", True):
            ctx.report_progress(0.6, "fixing self-intersections...")
            if ctx.is_canceled():
                raise OperationCanceled()

            si_approach = params.get("si_approach", "Local (Relax)")

            try:
                if "Voxel" in si_approach:
                    voxel_size = float(params.get("si_voxel_size", 0.0))
                    if voxel_size <= 0:
                        voxel_size = mr.averageEdgeLength() * 0.5
                    _mrm.fixSelfIntersections(mr, voxel_size)
                    steps_done.append(f"fixSelfIntersections(voxel={voxel_size:.4f})")
                else:
                    sp = _mrm.SelfIntersections.Settings()
                    sp.method = (
                        _mrm.SelfIntersections.Settings.Method.CutAndFill
                        if "CutAndFill" in si_approach
                        else _mrm.SelfIntersections.Settings.Method.Relax
                    )
                    sp.relaxIterations = int(params.get("si_relax_iterations", 5))
                    sp.subdivideEdgeLen = float(params.get("si_subdivide_edge_len", 0.0))
                    sp.maxExpand = int(params.get("si_max_expand", 3))
                    sp.touchIsIntersection = bool(params.get("si_touch_is_intersection", True))
                    _mrm.localFixSelfIntersections(mr, sp)
                    steps_done.append("fixSelfIntersections")
            except Exception as e:
                partial_failure = True
                _LOGGER.warning("fixSelfIntersections failed: %s", e)
                steps_done.append(f"fixSelfIntersections(FAILED:{e})")

        ctx.report_progress(1.0, "done")
        status = "Auto repair PARTIAL (some steps failed)" if partial_failure else "Auto repair complete"
        return OperationResult(
            mesh=mesh,
            info={"steps": steps_done, "partial_failure": partial_failure},
            message=f"{status}: {', '.join(steps_done)}",
        )
