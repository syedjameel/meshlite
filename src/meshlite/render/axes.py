"""X / Y / Z axis arrows for the viewport.

The existing project built axes by composing trimesh cylinders + cones with
manual rotations. We don't depend on trimesh anymore — instead we use
``mrmeshpy.makeArrow`` directly (one call per axis), which is both simpler
and more accurate to the intent (the resulting arrow points exactly from
``base`` to ``tip``).

Each axis is uploaded to the GPU as its own ``GpuMesh`` so the renderer can
issue them with different colors in a single pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import moderngl
from pyglm import glm

from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import make_arrow

from .gpu_mesh import GpuMesh
from .gpu_upload import mesh_data_to_arrays

# RGB convention: X=red, Y=green, Z=blue. Same as Blender, Maya, ROS.
X_COLOR: tuple[float, float, float] = (1.0, 0.25, 0.25)
Y_COLOR: tuple[float, float, float] = (0.25, 1.0, 0.25)
Z_COLOR: tuple[float, float, float] = (0.3, 0.5, 1.0)


@dataclass
class AxisArrow:
    name: str                                  # "X", "Y", "Z"
    gpu_mesh: GpuMesh
    color: tuple[float, float, float]
    transform: glm.mat4                        # local model matrix (currently identity)


def build_axes(
    ctx: moderngl.Context,
    prog: moderngl.Program,
    *,
    length: float = 1.0,
) -> list[AxisArrow]:
    """Build the three R/G/B axis arrows as GPU meshes.

    Each arrow runs from the origin to ``length`` along its axis. The
    renderer scales them at draw time so they remain visible regardless of
    the loaded scene's bounding box.
    """
    arrows: list[AxisArrow] = []
    for name, direction, color in (
        ("X", (length, 0.0, 0.0), X_COLOR),
        ("Y", (0.0, length, 0.0), Y_COLOR),
        ("Z", (0.0, 0.0, length), Z_COLOR),
    ):
        mr = make_arrow((0.0, 0.0, 0.0), direction)
        mesh_data = MeshData(mr=mr, name=f"axis_{name.lower()}")
        arrays = mesh_data_to_arrays(mesh_data)
        gpu = GpuMesh(ctx, prog, arrays)
        arrows.append(
            AxisArrow(name=name, gpu_mesh=gpu, color=color, transform=glm.mat4(1.0))
        )
    return arrows


def release_axes(arrows: list[AxisArrow]) -> None:
    """Free the GPU resources backing all axis arrows."""
    for a in arrows:
        a.gpu_mesh.release()
