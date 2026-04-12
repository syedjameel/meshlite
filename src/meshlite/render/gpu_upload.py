"""Bridge from the CPU-side :class:`MeshData` to GPU-ready numpy arrays.

The render layer never imports ``meshlib`` directly. Instead, this module
flattens a :class:`MeshData` into the three numpy arrays that ``GpuMesh``
needs to upload to a moderngl VBO/IBO/VAO:

    positions: float32[N, 3]
    normals:   float32[N, 3]
    indices:   int32[M*3]   (flattened triangle list)

This is also the choke point where any future LOD / packing / interleaving
optimizations would live.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import (
    get_numpy_faces,
    get_numpy_vert_normals,
    get_numpy_verts,
)


@dataclass(frozen=True)
class MeshArrays:
    """GPU-ready numpy arrays extracted from a :class:`MeshData`."""

    positions: np.ndarray   # (N, 3) float32
    normals: np.ndarray     # (N, 3) float32
    indices: np.ndarray     # (M*3,) int32, flattened triangle list

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.indices.shape[0] // 3)


def mesh_data_to_arrays(mesh: MeshData) -> MeshArrays:
    """Extract GPU-ready numpy arrays from a :class:`MeshData`.

    Pulls vertex positions and per-vertex normals through :mod:`mrm_shim`,
    pulls face indices and flattens them, and downcasts everything to the
    dtypes that the moderngl shader inputs expect (``f4`` and ``i4``).
    """
    positions = np.ascontiguousarray(get_numpy_verts(mesh.mr), dtype=np.float32)
    normals = np.ascontiguousarray(get_numpy_vert_normals(mesh.mr), dtype=np.float32)
    faces = get_numpy_faces(mesh.mr)            # (M, 3) int32
    indices = np.ascontiguousarray(faces.reshape(-1), dtype=np.int32)

    if positions.shape != normals.shape:
        raise ValueError(
            f"position/normal shape mismatch: {positions.shape} vs {normals.shape}"
        )
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError(f"positions must be (N, 3); got {positions.shape}")

    return MeshArrays(positions=positions, normals=normals, indices=indices)
