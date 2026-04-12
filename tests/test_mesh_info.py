"""M7 — mesh info computation tests.

Exercises :func:`meshlite.domain.mesh_info.compute` against the cube
fixture (known geometry) and verifies that ``DocumentNode.info_cache``
invalidation works.
"""

from __future__ import annotations

import pytest

from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mesh_info import MeshInfo, compute
from meshlite.domain.mrm_shim import make_cube


def _make_open_cylinder():
    """Helper: build an open-ended cylinder (2 holes, not watertight)."""
    import meshlib.mrmeshpy as mrm
    return mrm.makeOpenCylinder(radius=0.5, z1=-0.5, z2=0.5)


# ---------------------------------------------------------------------------
# Cube — known geometry (unit cube, 8 verts, 12 faces)
# ---------------------------------------------------------------------------


@pytest.fixture
def cube_info() -> MeshInfo:
    mesh = MeshData(mr=make_cube(), name="cube")
    return compute(mesh)


def test_cube_topology(cube_info: MeshInfo) -> None:
    assert cube_info.num_vertices == 8
    assert cube_info.num_faces == 12
    assert cube_info.num_holes == 0
    assert cube_info.is_watertight is True
    assert cube_info.connected_components == 1


def test_cube_geometry(cube_info: MeshInfo) -> None:
    assert cube_info.surface_area == pytest.approx(6.0)
    assert cube_info.volume == pytest.approx(1.0)
    assert cube_info.average_edge_length == pytest.approx(1.138, abs=0.01)


def test_cube_bounding_box(cube_info: MeshInfo) -> None:
    assert cube_info.bbox_min == pytest.approx((-0.5, -0.5, -0.5))
    assert cube_info.bbox_max == pytest.approx((0.5, 0.5, 0.5))
    assert cube_info.bbox_dimensions == pytest.approx((1.0, 1.0, 1.0))
    assert cube_info.bbox_center == pytest.approx((0.0, 0.0, 0.0))


def test_mesh_info_is_frozen() -> None:
    mesh = MeshData(mr=make_cube(), name="cube")
    info = compute(mesh)
    with pytest.raises(AttributeError):
        info.num_vertices = 999


# ---------------------------------------------------------------------------
# Open cylinder — not watertight (2 holes at each end)
# ---------------------------------------------------------------------------


def test_open_cylinder_is_not_watertight() -> None:
    mesh = MeshData(mr=_make_open_cylinder(), name="open_cyl")
    info = compute(mesh)
    assert info.is_watertight is False
    assert info.num_holes == 2
    assert info.num_vertices > 0
    assert info.num_faces > 0
    assert info.connected_components == 1


# ---------------------------------------------------------------------------
# Info cache invalidation on Document.replace_mesh
# ---------------------------------------------------------------------------


def test_info_cache_invalidated_on_replace() -> None:
    """Document.replace_mesh sets ``node.info_cache = None``."""
    from meshlite.app_state.document import Document
    from meshlite.app_state.events import EventBus

    events = EventBus()
    doc = Document(events)
    cube = MeshData(mr=make_cube(), name="cube")
    node_id = doc.add_node(cube, name="cube")

    node = doc.get_node(node_id)
    node.info_cache = compute(cube)
    assert node.info_cache is not None

    cyl = MeshData(mr=_make_open_cylinder(), name="cylinder")
    doc.replace_mesh(node_id, cyl)
    assert node.info_cache is None, "info_cache must be invalidated on mesh replacement"
