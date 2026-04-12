"""M2 — domain layer + MeshLib smoke test.

Covers:
- Loading an STL via :func:`meshlite.domain.load`
- Save/reload round trip preserves vertex and face counts
- ``MeshData.clone()`` is a TRUE DEEP COPY (load-bearing for snapshot undo;
  see Risks #2 in the plan). If this test ever regresses, the entire undo
  strategy needs to switch to numpy-roundtrip cloning.
- Error paths: missing file, unsupported extension
- Sanity: unit-cube geometry queries return expected values
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meshlite.domain import MeshData, UnsupportedMeshFormatError, load, save
from meshlite.domain.mrm_shim import make_cube

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_load_cube_returns_meshdata(cube_stl_path: Path) -> None:
    mesh = load(cube_stl_path)
    assert isinstance(mesh, MeshData)
    assert mesh.num_vertices == 8
    assert mesh.num_faces == 12
    assert mesh.is_watertight
    assert mesh.num_holes == 0
    assert mesh.source_path == cube_stl_path.resolve()
    assert mesh.name == "cube.stl"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "does_not_exist.stl")


def test_load_unsupported_extension_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "mesh.xyz"
    bogus.write_text("not a mesh")
    with pytest.raises(UnsupportedMeshFormatError):
        load(bogus)


# ---------------------------------------------------------------------------
# Save / round trip
# ---------------------------------------------------------------------------

def test_save_then_reload_round_trip(cube_stl_path: Path, tmp_path: Path) -> None:
    original = load(cube_stl_path)
    out = tmp_path / "round_trip.stl"
    written = save(original, out)
    assert written.exists()
    assert written.stat().st_size > 0

    reloaded = load(out)
    assert reloaded.num_vertices == original.num_vertices
    assert reloaded.num_faces == original.num_faces
    assert reloaded.is_watertight == original.is_watertight
    assert reloaded.surface_area == pytest.approx(original.surface_area)
    assert reloaded.volume == pytest.approx(original.volume)


def test_save_unsupported_extension_raises(tmp_path: Path) -> None:
    mesh = MeshData(mr=make_cube(), name="cube")
    with pytest.raises(UnsupportedMeshFormatError):
        save(mesh, tmp_path / "out.xyz")


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    mesh = MeshData(mr=make_cube(), name="cube")
    out = tmp_path / "deeply" / "nested" / "dir" / "cube.stl"
    save(mesh, out)
    assert out.exists()


# ---------------------------------------------------------------------------
# Clone semantics — LOAD-BEARING for undo strategy (Risks #2 in the plan)
# ---------------------------------------------------------------------------

def test_clone_is_deep_copy_against_transform() -> None:
    """If the clone shared state, transforming it would also transform the original."""
    import meshlib.mrmeshpy as mrm  # local import — only the test pierces the abstraction

    original = MeshData(mr=make_cube(), name="cube")
    original_area = original.surface_area
    original_bbox = original.bounding_box()

    clone = original.clone()
    xf = mrm.AffineXf3f.translation(mrm.Vector3f(100.0, 200.0, 300.0))
    clone.mr.transform(xf)

    # Original must be untouched.
    assert original.surface_area == pytest.approx(original_area)
    assert original.bounding_box() == original_bbox

    # Clone must reflect the mutation.
    clone_bbox = clone.bounding_box()
    assert clone_bbox != original_bbox
    assert clone_bbox[0][0] == pytest.approx(original_bbox[0][0] + 100.0)


def test_clone_is_deep_copy_against_numpy_inspection() -> None:
    """Belt-and-suspenders: round-trip both meshes through numpy and compare."""
    import numpy as np

    from meshlite.domain.mrm_shim import get_numpy_verts

    original = MeshData(mr=make_cube(), name="cube")
    verts_before = get_numpy_verts(original.mr).copy()

    clone = original.clone()
    # Mutate the clone in a way that touches every vertex.
    import meshlib.mrmeshpy as mrm
    clone.mr.transform(mrm.AffineXf3f.translation(mrm.Vector3f(1.0, 2.0, 3.0)))

    verts_after = get_numpy_verts(original.mr)
    assert np.array_equal(verts_before, verts_after), (
        "MeshData.clone() is not a deep copy — undo strategy in the plan "
        "(snapshot-based via .clone()) is unsafe. Fall back to "
        "numpy-roundtrip cloning."
    )


def test_clone_metadata_is_independent() -> None:
    """Mutating clone metadata must not affect the original."""
    original = MeshData(mr=make_cube(), name="original.stl")
    clone = original.clone()
    clone.name = "mutated.stl"
    assert original.name == "original.stl"


# ---------------------------------------------------------------------------
# Geometry sanity (the unit cube has known values)
# ---------------------------------------------------------------------------

def test_unit_cube_bounding_box() -> None:
    mesh = MeshData(mr=make_cube(), name="cube")
    bb_min, bb_max = mesh.bounding_box()
    assert bb_min == pytest.approx((-0.5, -0.5, -0.5))
    assert bb_max == pytest.approx((0.5, 0.5, 0.5))


def test_unit_cube_area_and_volume() -> None:
    mesh = MeshData(mr=make_cube(), name="cube")
    assert mesh.surface_area == pytest.approx(6.0)
    assert mesh.volume == pytest.approx(1.0)
