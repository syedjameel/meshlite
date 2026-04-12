"""``BooleanOperation`` — CSG boolean (Union / Intersection / Difference).

Single operation class with an ``operation_type`` enum param. Requires two
meshes: the primary selection (mesh A) and a second mesh selected via the
``node_picker`` param widget (mesh B). The result replaces mesh A.

Exposes the FULL ``BooleanParameters`` struct from meshlib (excluding
internal pointer/output types).

NOTE: The op accesses the document directly (via params["mesh_b_id"]) to
read mesh B. This is acceptable because boolean ops inherently need
multi-mesh access; the architecture allows params to carry arbitrary data.
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

_OP_MAP = {
    "Union": _mrm.BooleanOperation.Union,
    "Intersection": _mrm.BooleanOperation.Intersection,
    "Difference A-B": _mrm.BooleanOperation.DifferenceAB,
    "Difference B-A": _mrm.BooleanOperation.DifferenceBA,
}

def _adv(v):
    return v.get("show_advanced", False)


@register_operation
class BooleanOp(Operation):
    """CSG boolean operation between two meshes."""

    id = "boolean.boolean"
    label = "Boolean"
    category = "Boolean"
    description = "Union / Intersection / Difference between two meshes"
    icon = "\ueafe"  # codicon-git-merge
    requires = "one_mesh"
    creates_node = True    # result is a NEW mesh, not a replacement of A
    undoable = False       # creates_node ops don't support undo yet
    schema = ParamSchema((
        Param("operation_type", "enum", "Operation", default="Union",
              choices=tuple(_OP_MAP.keys()),
              help="CSG operation type"),
        Param("mesh_b_id", "node_picker", "Second mesh (B)", default="",
              help="Select the second mesh for the boolean operation"),

        Param("show_advanced", "bool", "Show advanced", default=False),
        Param("force_cut", "bool", "Force cut", default=False,
              visible_if=_adv,
              help="Force cutting of mesh surfaces even where they only touch"),
        Param("merge_all_non_intersecting", "bool", "Merge non-intersecting components", default=False,
              visible_if=_adv,
              help="Include components of mesh B that don't intersect mesh A"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("BooleanOp requires a target mesh (mesh A)")

        mesh_b_id = params.get("mesh_b_id", "")
        if not mesh_b_id:
            raise OperationError(
                "Boolean operations require a second mesh. "
                "Select mesh B from the dropdown in the Properties panel."
            )

        # Access mesh B from the document via the stored node_id.
        # This is passed through params by the Properties panel.
        # The CommandBus clones mesh A for the worker. Mesh B we read directly
        # from the document — it's read-only, the worker doesn't modify it.
        # This is safe because meshlib's boolean takes both meshes by const ref.
        mesh_b_data = params.get("_mesh_b_data")
        if mesh_b_data is None:
            raise OperationError(
                f"Internal error: mesh B data not found for node {mesh_b_id}. "
                "The Properties panel should inject it before dispatch."
            )

        op_name = params.get("operation_type", "Union")
        op_enum = _OP_MAP.get(op_name)
        if op_enum is None:
            raise OperationError(f"Unknown boolean operation: {op_name}")

        ctx.report_progress(0.1, f"computing {op_name}...")

        bp = _mrm.BooleanParameters()
        bp.forceCut = bool(params.get("force_cut", False))
        bp.mergeAllNonIntersectingComponents = bool(params.get("merge_all_non_intersecting", False))

        result = _mrm.boolean(mesh.mr, mesh_b_data.mr, op_enum, bp)

        if result.errorString:
            # Provide actionable suggestions alongside the meshlib error.
            suggestions = []
            err = result.errorString
            if "not closed" in err or "inside and outside" in err:
                suggestions.append("Ensure both meshes are watertight (use Fill Holes first)")
            if "self-intersect" in err or "Bad contour" in err:
                suggestions.append("Run Auto Repair or Fix Self-Intersections on both meshes")
            if "not consistent" in err:
                suggestions.append("Run Remove Duplicates to fix orientation")

            msg = f"Boolean {op_name} failed: {err}"
            if suggestions:
                msg += "\n\nSuggested fixes:\n" + "\n".join(f"  - {s}" for s in suggestions)
            raise OperationError(msg)

        if result.mesh is None:
            raise OperationError(f"Boolean {op_name} produced no output mesh")

        ctx.report_progress(1.0, "done")
        out = MeshData(mr=result.mesh, name=f"{op_name.lower()}_result",
                       source_path=mesh.source_path)
        return OperationResult(
            mesh=out,
            info={"operation": op_name, "verts": out.num_vertices, "faces": out.num_faces},
            message=f"Boolean {op_name}: {out.num_vertices} verts, {out.num_faces} faces",
        )
