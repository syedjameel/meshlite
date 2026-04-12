"""``FindSelfIntersectionsOperation`` — detect and optionally fix self-intersections.

Uses ``fixSelfIntersections`` with full ``FixSelfIntersectionSettings`` exposure.
Reports how many intersections were found/fixed.
"""

# Architecture note: ops/ is allowed to import meshlib directly for complex
# Settings struct construction. See CONTRIBUTING.md for layer rules.

from __future__ import annotations

from typing import Any

import meshlib.mrmeshpy as _mrm

from meshlite.domain.mesh_data import MeshData

from ..base import (
    Operation,
    OperationContext,
    OperationError,
    OperationResult,
    Param,
    ParamSchema,
)
from ..registry import register_operation


@register_operation
class FindSelfIntersectionsOperation(Operation):
    """Detect and fix mesh self-intersections."""

    id = "inspect.fix_self_intersections"
    label = "Fix Self-Intersections"
    category = "Inspect"
    description = "Detect and fix faces that intersect each other within the same mesh"
    icon = "\uea86"  # codicon-symbol-event
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("approach", "enum", "Approach", default="Local (Relax)",
              choices=("Local (Relax)", "Local (CutAndFill)", "Voxel-based (aggressive)"),
              help="Local methods fix intersections in-place. Voxel-based converts the "
                   "entire mesh to a distance field and back — more aggressive but changes "
                   "topology completely. Use Voxel-based for meshes where Local fails."),
        Param("voxel_size", "float", "Voxel size", default=0.0,
              min=0.0, max=10.0, step=0.01,
              help="Voxel resolution for the voxel-based approach (0 = auto from avg edge length). "
                   "Smaller = more detail preserved but slower.",
              visible_if=lambda v: "Voxel" in v.get("approach", "")),
        Param("relax_iterations", "int", "Relax iterations", default=5,
              min=1, max=100, step=1,
              help="Number of relaxation iterations (Local methods only)",
              visible_if=lambda v: "Local" in v.get("approach", "")),
        Param("subdivide_edge_len", "float", "Subdivide edge length", default=0.0,
              min=0.0, max=10.0, step=0.01,
              help="Subdivide edges before fixing (0 = no subdivision)",
              visible_if=lambda v: "Local" in v.get("approach", "")),
        Param("max_expand", "int", "Max expand", default=3,
              min=0, max=20, step=1,
              help="Maximum region expansion for fix",
              visible_if=lambda v: "Local" in v.get("approach", "")),
        Param("touch_is_intersection", "bool", "Touch is intersection", default=True,
              help="Treat touching faces as intersecting",
              visible_if=lambda v: "Local" in v.get("approach", "")),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("FindSelfIntersectionsOperation requires a mesh")

        mr = mesh.mr
        approach = params.get("approach", "Local (Relax)")

        if "Voxel" in approach:
            ctx.report_progress(0.1, "fixing via voxel conversion (aggressive)...")
            voxel_size = float(params.get("voxel_size", 0.0))
            if voxel_size <= 0:
                voxel_size = mr.averageEdgeLength() * 0.5
            _mrm.fixSelfIntersections(mr, voxel_size)
            ctx.report_progress(1.0, "done")
            return OperationResult(
                mesh=mesh,
                info={"approach": approach, "voxel_size": voxel_size},
                message=f"Self-intersections fixed (voxel-based, size={voxel_size:.4f})",
            )

        # Local approach
        ctx.report_progress(0.1, f"fixing self-intersections ({approach})...")
        sp = _mrm.SelfIntersections.Settings()
        sp.method = (
            _mrm.SelfIntersections.Settings.Method.CutAndFill
            if "CutAndFill" in approach
            else _mrm.SelfIntersections.Settings.Method.Relax
        )
        sp.relaxIterations = int(params.get("relax_iterations", 5))
        sp.subdivideEdgeLen = float(params.get("subdivide_edge_len", 0.0))
        sp.maxExpand = int(params.get("max_expand", 3))
        sp.touchIsIntersection = bool(params.get("touch_is_intersection", True))

        _mrm.localFixSelfIntersections(mr, sp)

        ctx.report_progress(1.0, "done")
        return OperationResult(
            mesh=mesh,
            info={"approach": approach},
            message=f"Self-intersections fixed ({approach})",
        )
