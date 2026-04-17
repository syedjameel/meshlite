"""Correctness tests for ``mesh_data_to_arrays`` — the CPU-side mesh → GPU
arrays bridge. Focused on edge cases that could produce NaN or zero-length
normals which crash the shader's ``normalize(v_normal)``.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from meshlite.render.gpu_upload import mesh_data_to_arrays


class _FakeMesh:
    """Minimal stand-in for MeshData — mesh_data_to_arrays only reads ``.mr``."""

    mr = object()


@pytest.fixture
def fake_mesh() -> _FakeMesh:
    return _FakeMesh()


def _run(verts: np.ndarray, faces: np.ndarray, mesh: _FakeMesh):
    with (
        patch("meshlite.render.gpu_upload.get_numpy_verts", return_value=verts),
        patch("meshlite.render.gpu_upload.get_numpy_faces", return_value=faces),
    ):
        return mesh_data_to_arrays(mesh)


def test_zero_area_face_yields_finite_unit_normal(fake_mesh):
    """A triangle with two identical vertices produces a zero-length cross
    product; the output normal must still be finite and non-zero so the
    shader's ``normalize`` doesn't return NaN.
    """
    verts = np.array(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        dtype=np.float32,
    )
    # Second triangle is degenerate (v0 == v1).
    faces = np.array([[0, 1, 2], [0, 0, 1]], dtype=np.int32)

    arrays = _run(verts, faces, fake_mesh)

    assert np.isfinite(arrays.normals).all()
    lens = np.linalg.norm(arrays.normals, axis=1)
    assert (lens > 0.5).all(), f"expected unit-length normals, got {lens}"


def test_well_formed_triangle_normal_is_unit(fake_mesh):
    verts = np.array(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], dtype=np.float32
    )
    faces = np.array([[0, 1, 2]], dtype=np.int32)

    arrays = _run(verts, faces, fake_mesh)

    # Face normal should be +Z for a CCW triangle in the XY plane.
    np.testing.assert_allclose(arrays.normals[0], (0.0, 0.0, 1.0), atol=1e-6)
    assert arrays.vertex_count == 3
    assert arrays.triangle_count == 1
    np.testing.assert_array_equal(arrays.indices, (0, 1, 2))


def test_rejects_malformed_verts(fake_mesh):
    with pytest.raises(ValueError, match="vertices must be"):
        _run(np.zeros((3,), dtype=np.float32),
             np.zeros((1, 3), dtype=np.int32), fake_mesh)


def test_rejects_malformed_faces(fake_mesh):
    with pytest.raises(ValueError, match="faces must be"):
        _run(np.zeros((3, 3), dtype=np.float32),
             np.zeros((3,), dtype=np.int32), fake_mesh)
