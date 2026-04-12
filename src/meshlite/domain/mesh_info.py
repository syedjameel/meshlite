"""Compute comprehensive mesh statistics.

:func:`compute` takes a :class:`MeshData` and returns a frozen
:class:`MeshInfo` dataclass with every stat the Mesh Info panel and the
Properties panel want to display.

This is a pure function — no caching, no events, no side effects. The
caller (typically the UI via ``node.info_cache``) decides when to invoke it
and stores the result.

Performance: for a mesh with 100 K faces, all stats compute in < 50 ms
on typical hardware. The most expensive call is ``connected_components_count``
which builds a union-find over the face adjacency graph. If performance
becomes an issue for very large meshes, this function can be dispatched via
the TaskRunner; for M7 we keep it synchronous.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import mrm_shim
from .mesh_data import MeshData


@dataclass(frozen=True)
class MeshInfo:
    """Comprehensive statistics for one mesh.

    All fields are populated eagerly by :func:`compute`. None of them are
    expensive enough to warrant lazy computation.
    """

    # Topology
    num_vertices: int
    num_faces: int
    num_holes: int
    is_watertight: bool
    connected_components: int

    # Geometry (bounding box)
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    bbox_dimensions: tuple[float, float, float]
    bbox_center: tuple[float, float, float]

    # Geometry (aggregate)
    surface_area: float
    volume: float
    average_edge_length: float


def compute(mesh: MeshData) -> MeshInfo:
    """Compute all mesh statistics and return them as a frozen :class:`MeshInfo`.

    Delegates to :mod:`mrm_shim` for every MeshLib call so this module never
    imports ``meshlib`` directly.
    """
    mr = mesh.mr

    bb_min, bb_max = mrm_shim.bounding_box(mr)
    dims = (
        bb_max[0] - bb_min[0],
        bb_max[1] - bb_min[1],
        bb_max[2] - bb_min[2],
    )

    return MeshInfo(
        num_vertices=mrm_shim.num_vertices(mr),
        num_faces=mrm_shim.num_faces(mr),
        num_holes=mrm_shim.num_holes(mr),
        is_watertight=mrm_shim.is_watertight(mr),
        connected_components=mrm_shim.connected_components_count(mr),
        bbox_min=bb_min,
        bbox_max=bb_max,
        bbox_dimensions=dims,
        bbox_center=mrm_shim.center_from_bbox(mr),
        surface_area=mrm_shim.surface_area(mr),
        volume=mrm_shim.volume(mr),
        average_edge_length=mrm_shim.average_edge_length(mr),
    )
