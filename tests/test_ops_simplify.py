"""Tests for simplify operations: decimate, remesh, subdivide."""

from __future__ import annotations

import time

import pytest

from meshlite.app_state.command_bus import CommandBus
from meshlite.app_state.document import Document
from meshlite.app_state.events import EventBus
from meshlite.app_state.history import UndoStack
from meshlite.app_state.selection_model import SelectionModel
from meshlite.app_state.task_runner import TaskRunner
from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import make_cube
from meshlite.ops.simplify.decimate import DecimateOperation
from meshlite.ops.simplify.remesh import RemeshOperation
from meshlite.ops.simplify.subdivide import SubdivideOperation
from meshlite.utils.async_task import TaskManager


@pytest.fixture
def bus() -> CommandBus:
    events = EventBus()
    return CommandBus(
        document=Document(events), selection=SelectionModel(events),
        history=UndoStack(), task_runner=TaskRunner(TaskManager(2)), events=events,
    )


def _pump(bus, max_s=5.0):
    deadline = time.monotonic() + max_s
    while time.monotonic() < deadline:
        bus.task_runner.update_tasks()
        bus.task_runner.drain_main_thread_queue()
        if not bus.all_active_ops():
            return
        time.sleep(0.01)


def _add_cube(bus) -> str:
    nid = bus.document.add_node(MeshData(mr=make_cube(), name="cube"), name="cube")
    bus.selection.set([nid])
    return nid


def test_subdivide_increases_faces(bus):
    nid = _add_cube(bus)
    faces_before = bus.document.get_node(nid).mesh.num_faces
    bus.run_operation(SubdivideOperation(), target_node_id=nid,
                      params={"max_edge_len": 0.5, "max_edge_splits": 10000})
    _pump(bus)
    faces_after = bus.document.get_node(nid).mesh.num_faces
    assert faces_after > faces_before


def test_subdivide_undo(bus):
    nid = _add_cube(bus)
    faces_before = bus.document.get_node(nid).mesh.num_faces
    bus.run_operation(SubdivideOperation(), target_node_id=nid,
                      params={"max_edge_len": 0.5, "max_edge_splits": 10000})
    _pump(bus)
    assert bus.undo()
    assert bus.document.get_node(nid).mesh.num_faces == faces_before


def test_remesh_changes_faces(bus):
    nid = _add_cube(bus)
    bus.run_operation(RemeshOperation(), target_node_id=nid,
                      params={"target_edge_len": 0.3})
    _pump(bus)
    node = bus.document.get_node(nid)
    assert node.mesh.num_faces > 12  # remesh with smaller edge length should add faces


def test_decimate_reduces_faces(bus):
    """Decimate a subdivided cube to verify face reduction."""
    nid = _add_cube(bus)
    # First subdivide to get more faces
    bus.run_operation(SubdivideOperation(), target_node_id=nid,
                      params={"max_edge_len": 0.3, "max_edge_splits": 50000})
    _pump(bus)
    faces_before = bus.document.get_node(nid).mesh.num_faces
    assert faces_before > 50

    # Now decimate aggressively
    bus.run_operation(DecimateOperation(), target_node_id=nid,
                      params={"ratio": 0.1, "strategy": "ShortestEdgeFirst", "max_error": 10.0})
    _pump(bus)
    faces_after = bus.document.get_node(nid).mesh.num_faces
    assert faces_after < faces_before, f"decimate failed to reduce: {faces_before} → {faces_after}"
