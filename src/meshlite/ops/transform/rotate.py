"""``RotateOperation`` — rotate mesh around an axis by an angle."""

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
    return v.get("axis", "X") == "Custom"
def _bbox_center(v):
    return v.get("pivot", "Origin") == "BBox Center"


@register_operation
class RotateOperation(Operation):
    """Rotate the mesh around a chosen axis by a given angle in degrees."""

    id = "transform.rotate"
    label = "Rotate"
    category = "Transform"
    description = "Rotate mesh around X/Y/Z or a custom axis"
    icon = "\ueb37"  # codicon-refresh (stand-in)
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("axis", "enum", "Axis", default="X",
              choices=("X", "Y", "Z", "Custom"),
              help="Rotation axis"),
        Param("angle_degrees", "float", "Angle (degrees)", default=0.0,
              min=-360.0, max=360.0, step=1.0,
              help="Rotation angle in degrees"),
        Param("pivot", "enum", "Pivot", default="Origin",
              choices=("Origin", "BBox Center"),
              help="Point to rotate around"),
        Param("custom_axis_x", "float", "Custom axis X", default=1.0,
              min=-1.0, max=1.0, step=0.1, visible_if=_custom),
        Param("custom_axis_y", "float", "Custom axis Y", default=0.0,
              min=-1.0, max=1.0, step=0.1, visible_if=_custom),
        Param("custom_axis_z", "float", "Custom axis Z", default=0.0,
              min=-1.0, max=1.0, step=0.1, visible_if=_custom),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("RotateOperation requires a mesh")

        mr = mesh.mr
        angle = math.radians(float(params.get("angle_degrees", 0)))
        axis_name = params.get("axis", "X")

        if axis_name == "X":
            axis_vec = _mrm.Vector3f(1, 0, 0)
        elif axis_name == "Y":
            axis_vec = _mrm.Vector3f(0, 1, 0)
        elif axis_name == "Z":
            axis_vec = _mrm.Vector3f(0, 0, 1)
        else:
            axis_vec = _mrm.Vector3f(
                float(params.get("custom_axis_x", 1)),
                float(params.get("custom_axis_y", 0)),
                float(params.get("custom_axis_z", 0)),
            )

        # Normalize axis
        length = math.sqrt(axis_vec.x**2 + axis_vec.y**2 + axis_vec.z**2)
        if length < 1e-10:
            raise OperationError("Rotation axis cannot be zero-length")
        axis_vec = _mrm.Vector3f(axis_vec.x / length, axis_vec.y / length, axis_vec.z / length)

        ctx.report_progress(0.1, f"rotating {params.get('angle_degrees', 0)}° around {axis_name}...")

        # Build rotation as AffineXf3f
        pivot = params.get("pivot", "Origin")
        if pivot == "BBox Center":
            center = mr.findCenterFromBBox()
            # Translate to origin, rotate, translate back
            to_origin = _mrm.AffineXf3f.translation(_mrm.Vector3f(-center.x, -center.y, -center.z))
            from_origin = _mrm.AffineXf3f.translation(center)
            rot = _mrm.Matrix3f.rotation(axis_vec, angle)
            rot_xf = _mrm.AffineXf3f(rot, _mrm.Vector3f(0, 0, 0))
            # Combined: from_origin * rot * to_origin
            mr.transform(to_origin)
            mr.transform(rot_xf)
            mr.transform(from_origin)
        else:
            rot = _mrm.Matrix3f.rotation(axis_vec, angle)
            xf = _mrm.AffineXf3f(rot, _mrm.Vector3f(0, 0, 0))
            mr.transform(xf)

        ctx.report_progress(1.0, "done")
        return OperationResult(
            mesh=mesh,
            info={"axis": axis_name, "angle_degrees": params.get("angle_degrees", 0), "pivot": pivot},
            message=f"Rotated {params.get('angle_degrees', 0)}° around {axis_name} (pivot={pivot})",
        )
