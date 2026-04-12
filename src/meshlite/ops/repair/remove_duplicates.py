"""``RemoveDuplicatesOperation`` — fix non-manifold/duplicate edges + disoriented faces.

Runs ``fixMultipleEdges`` to remove duplicate/non-manifold edges, then
optionally detects and flips disoriented faces.
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
class RemoveDuplicatesOperation(Operation):
    """Fix non-manifold edges and optionally flip disoriented faces."""

    id = "repair.remove_duplicates"
    label = "Remove Duplicates"
    category = "Repair"
    description = "Fix non-manifold/duplicate edges and disoriented faces"
    icon = "\ueabe"  # codicon-circuit-board
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("fix_multiple_edges", "bool", "Fix non-manifold edges", default=True,
              help="Remove duplicate edges sharing the same two vertices"),
        Param("fix_disoriented_faces", "bool", "Detect disoriented faces", default=True,
              help="Check for faces whose normals are inconsistent with neighbors"),
        Param("flip_orientation", "bool", "Flip entire mesh orientation", default=False,
              help="Flip all normals (use when mesh appears inside-out). Only applies "
                   "when disoriented faces are detected",
              visible_if=lambda v: v.get("fix_disoriented_faces", True)),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("RemoveDuplicatesOperation requires a mesh")

        mr = mesh.mr
        fixes = []

        if params.get("fix_multiple_edges", True):
            ctx.report_progress(0.2, "fixing non-manifold edges...")
            _mrm.fixMultipleEdges(mr)
            fixes.append("non-manifold edges")

        if params.get("fix_disoriented_faces", True):
            ctx.report_progress(0.5, "detecting disoriented faces...")
            disoriented = _mrm.findDisorientedFaces(mr)
            count = disoriented.count() if hasattr(disoriented, 'count') else 0
            if count > 0 and params.get("flip_orientation", False):
                # Flip the entire mesh orientation (all normals) — this is the
                # correct approach when most faces are consistently oriented but
                # the mesh as a whole is inside-out.
                mr.topology.flipOrientation()
                fixes.append(f"flipped orientation ({count} disoriented faces detected)")
            elif count > 0:
                fixes.append(f"{count} disoriented faces detected (enable 'Flip orientation' to fix)")
            else:
                fixes.append("0 disoriented faces")

        ctx.report_progress(1.0, "done")
        return OperationResult(
            mesh=mesh,
            info={"fixes": fixes},
            message=f"Fixed: {', '.join(fixes)}",
        )
