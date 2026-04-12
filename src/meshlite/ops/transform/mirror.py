"""``MirrorOperation`` — reflect mesh through a plane."""

# Architecture note: ops/ is allowed to import meshlib directly for complex
# Settings struct construction. See CONTRIBUTING.md for layer rules.

from __future__ import annotations

import math
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


def _custom(v):
    return v.get("plane", "YZ (X=0)") == "Custom"


@register_operation
class MirrorOperation(Operation):
    """Reflect the mesh through a plane."""

    id = "transform.mirror"
    label = "Mirror"
    category = "Transform"
    description = "Reflect mesh through XY, XZ, YZ, or a custom plane"
    icon = "\uea69"  # codicon-mirror
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("plane", "enum", "Plane", default="YZ (X=0)",
              choices=("YZ (X=0)", "XZ (Y=0)", "XY (Z=0)", "Custom"),
              help="Predefined mirror plane or custom normal+offset"),
        Param("offset", "float", "Plane offset", default=0.0,
              min=-10000.0, max=10000.0, step=0.1,
              help="Distance of the plane from the origin along its normal"),
        Param("custom_nx", "float", "Custom normal X", default=1.0,
              min=-1.0, max=1.0, step=0.1, visible_if=_custom),
        Param("custom_ny", "float", "Custom normal Y", default=0.0,
              min=-1.0, max=1.0, step=0.1, visible_if=_custom),
        Param("custom_nz", "float", "Custom normal Z", default=0.0,
              min=-1.0, max=1.0, step=0.1, visible_if=_custom),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("MirrorOperation requires a mesh")

        plane_name = params.get("plane", "YZ (X=0)")
        offset = float(params.get("offset", 0.0))

        if plane_name == "YZ (X=0)":
            normal = _mrm.Vector3f(1, 0, 0)
        elif plane_name == "XZ (Y=0)":
            normal = _mrm.Vector3f(0, 1, 0)
        elif plane_name == "XY (Z=0)":
            normal = _mrm.Vector3f(0, 0, 1)
        else:
            nx = float(params.get("custom_nx", 1))
            ny = float(params.get("custom_ny", 0))
            nz = float(params.get("custom_nz", 0))
            length = math.sqrt(nx*nx + ny*ny + nz*nz)
            if length < 1e-10:
                raise OperationError("Mirror plane normal cannot be zero-length")
            normal = _mrm.Vector3f(nx / length, ny / length, nz / length)

        ctx.report_progress(0.1, f"mirroring through {plane_name}...")

        plane = _mrm.Plane3f()
        plane.n = normal
        plane.d = offset
        mesh.mr.mirror(plane)

        ctx.report_progress(1.0, "done")
        return OperationResult(
            mesh=mesh,
            info={"plane": plane_name, "offset": offset},
            message=f"Mirrored through {plane_name} (offset={offset})",
        )
