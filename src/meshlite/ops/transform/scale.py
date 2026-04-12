"""``ScaleOperation`` — scale mesh uniformly or per-axis."""

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


def _uniform(v):
    return v.get("uniform", True)
def _non_uniform(v):
    return not v.get("uniform", True)
def _bbox_pivot(v):
    return v.get("pivot", "Origin") == "BBox Center"


@register_operation
class ScaleOperation(Operation):
    """Scale the mesh uniformly or per-axis."""

    id = "transform.scale"
    label = "Scale"
    category = "Transform"
    description = "Scale the mesh uniformly or with independent X/Y/Z factors"
    icon = "\ueb95"  # codicon-expand-all
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("uniform", "bool", "Uniform scale", default=True,
              help="Use the same factor for all axes"),
        Param("factor", "float", "Scale factor", default=1.0,
              min=0.001, max=1000.0, step=0.1,
              visible_if=_uniform,
              help="Uniform scale factor (1.0 = no change)"),
        Param("x", "float", "X factor", default=1.0,
              min=0.001, max=1000.0, step=0.1,
              visible_if=_non_uniform),
        Param("y", "float", "Y factor", default=1.0,
              min=0.001, max=1000.0, step=0.1,
              visible_if=_non_uniform),
        Param("z", "float", "Z factor", default=1.0,
              min=0.001, max=1000.0, step=0.1,
              visible_if=_non_uniform),
        Param("pivot", "enum", "Pivot", default="Origin",
              choices=("Origin", "BBox Center"),
              help="Point to scale from"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("ScaleOperation requires a mesh")

        mr = mesh.mr
        uniform = bool(params.get("uniform", True))
        if uniform:
            f = float(params.get("factor", 1.0))
            sx, sy, sz = f, f, f
        else:
            sx = float(params.get("x", 1.0))
            sy = float(params.get("y", 1.0))
            sz = float(params.get("z", 1.0))

        ctx.report_progress(0.1, f"scaling ({sx}, {sy}, {sz})...")

        # Build scale transform
        scale_mat = _mrm.Matrix3f()
        scale_mat.x = _mrm.Vector3f(sx, 0, 0)
        scale_mat.y = _mrm.Vector3f(0, sy, 0)
        scale_mat.z = _mrm.Vector3f(0, 0, sz)

        pivot = params.get("pivot", "Origin")
        if pivot == "BBox Center":
            center = mr.findCenterFromBBox()
            to_origin = _mrm.AffineXf3f.translation(_mrm.Vector3f(-center.x, -center.y, -center.z))
            from_origin = _mrm.AffineXf3f.translation(center)
            scale_xf = _mrm.AffineXf3f(scale_mat, _mrm.Vector3f(0, 0, 0))
            mr.transform(to_origin)
            mr.transform(scale_xf)
            mr.transform(from_origin)
        else:
            xf = _mrm.AffineXf3f(scale_mat, _mrm.Vector3f(0, 0, 0))
            mr.transform(xf)

        ctx.report_progress(1.0, "done")
        return OperationResult(
            mesh=mesh,
            info={"sx": sx, "sy": sy, "sz": sz, "pivot": pivot},
            message=f"Scaled by ({sx}, {sy}, {sz}) pivot={pivot}",
        )
