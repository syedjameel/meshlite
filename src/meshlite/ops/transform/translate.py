"""``TranslateOperation`` — translate mesh by a vector."""

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
class TranslateOperation(Operation):
    """Move the mesh by a translation vector (X, Y, Z)."""

    id = "transform.translate"
    label = "Translate"
    category = "Transform"
    description = "Move the mesh by an offset in X, Y, Z"
    icon = "\uebd5"  # codicon-compass
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("x", "float", "X offset", default=0.0, min=-10000.0, max=10000.0, step=0.1),
        Param("y", "float", "Y offset", default=0.0, min=-10000.0, max=10000.0, step=0.1),
        Param("z", "float", "Z offset", default=0.0, min=-10000.0, max=10000.0, step=0.1),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("TranslateOperation requires a mesh")
        x, y, z = float(params.get("x", 0)), float(params.get("y", 0)), float(params.get("z", 0))
        ctx.report_progress(0.1, f"translating ({x}, {y}, {z})...")
        xf = _mrm.AffineXf3f.translation(_mrm.Vector3f(x, y, z))
        mesh.mr.transform(xf)
        ctx.report_progress(1.0, "done")
        return OperationResult(mesh=mesh, info={"x": x, "y": y, "z": z},
                               message=f"Translated by ({x}, {y}, {z})")
