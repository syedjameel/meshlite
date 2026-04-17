"""Bridge from the CPU-side :class:`MeshData` to GPU-ready numpy arrays.

The render layer never imports ``meshlib`` directly. Instead, this module
flattens a :class:`MeshData` into the three numpy arrays that ``GpuMesh``
needs to upload to a moderngl VBO/IBO/VAO:

    positions: float32[M*3, 3]       (each triangle has its own 3 vertices)
    normals:   float32[M*3, 3]       (face normal replicated to each vertex)
    indices:   int32[M*3]            (sequential 0..M*3-1)

**Why per-face expansion (vs. merged per-vertex normals):**
MeshLib internally merges coincident vertices. Its ``computePerVertNormals``
averages the incident face normals at each shared vertex, which makes
sharp-edged CAD meshes (e.g. a cube) look rounded/blurred. The reference
meshviewer uses trimesh on STLs, which keeps faces unmerged, so every
"vertex normal" equals its face normal → crisp flat shading. We replicate
that representation here: each triangle becomes 3 unique vertices, each
carrying the face normal computed from ``cross((v1-v0), (v2-v0))``.

For smoothly tessellated meshes (thousands of small triangles across a
curved surface), adjacent face normals are nearly equal, so the result
still looks smooth when viewed at distance — same as trimesh on such meshes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import get_numpy_faces, get_numpy_verts

_LOGGER = logging.getLogger(__name__)

# Degenerate faces get this unit normal so the shader receives finite
# input. A zero-length normal would become NaN through ``normalize`` and
# produce black or garbled pixels on the affected triangles.
_DEGENERATE_FACE_NORMAL = np.array((0.0, 0.0, 1.0), dtype=np.float32)


@dataclass(frozen=True)
class MeshArrays:
    """GPU-ready numpy arrays extracted from a :class:`MeshData`."""

    positions: np.ndarray   # (M*3, 3) float32 — per-triangle expanded
    normals: np.ndarray     # (M*3, 3) float32 — face normal replicated
    indices: np.ndarray     # (M*3,)  int32   — sequential triangle list

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.indices.shape[0] // 3)


def mesh_data_to_arrays(mesh: MeshData) -> MeshArrays:
    """Extract GPU-ready numpy arrays from a :class:`MeshData`.

    Produces a **per-face-expanded** representation: each triangle is
    assigned its own 3 vertices (no sharing) so per-vertex face normals
    give crisp flat shading. See module docstring for rationale.
    """
    verts = np.asarray(get_numpy_verts(mesh.mr), dtype=np.float32)   # (N, 3)
    faces = np.asarray(get_numpy_faces(mesh.mr), dtype=np.int32)     # (M, 3)

    if verts.ndim != 2 or verts.shape[1] != 3:
        raise ValueError(f"vertices must be (N, 3); got {verts.shape}")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f"faces must be (M, 3); got {faces.shape}")

    # Expand each triangle into 3 unique vertices.
    expanded_positions = verts[faces].reshape(-1, 3)                  # (M*3, 3)

    # Face normals via cross product on the (merged) vertex positions.
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
    safe = (lens > 1e-12).squeeze(-1)
    normalized = np.divide(
        face_normals, lens, where=lens > 1e-12, out=np.zeros_like(face_normals)
    )
    normalized[~safe] = _DEGENERATE_FACE_NORMAL
    face_normals = normalized.astype(np.float32)
    degenerate_count = int(np.count_nonzero(~safe))
    if degenerate_count:
        _LOGGER.warning(
            "mesh_data_to_arrays: %d degenerate face(s) out of %d have "
            "zero-area normals; using placeholder unit vector",
            degenerate_count, faces.shape[0],
        )

    # Replicate each face normal for its 3 vertices (M,3) -> (M*3,3).
    expanded_normals = np.repeat(face_normals, 3, axis=0)

    # Sequential indices — each triangle uses 3 consecutive unique vertices.
    indices = np.arange(expanded_positions.shape[0], dtype=np.int32)

    return MeshArrays(
        positions=np.ascontiguousarray(expanded_positions, dtype=np.float32),
        normals=np.ascontiguousarray(expanded_normals, dtype=np.float32),
        indices=indices,
    )
