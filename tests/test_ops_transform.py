"""Tests for transform operations: translate, rotate, scale, mirror."""

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
from meshlite.ops.transform.mirror import MirrorOperation
from meshlite.ops.transform.rotate import RotateOperation
from meshlite.ops.transform.scale import ScaleOperation
from meshlite.ops.transform.translate import TranslateOperation
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


def test_translate_shifts_bbox(bus):
    nid = _add_cube(bus)
    bus.run_operation(TranslateOperation(), target_node_id=nid, params={"x": 10.0, "y": 0.0, "z": 0.0})
    _pump(bus)
    bb = bus.document.get_node(nid).mesh.bounding_box()
    assert bb[0][0] == pytest.approx(9.5)
    assert bb[1][0] == pytest.approx(10.5)


def test_translate_undo(bus):
    nid = _add_cube(bus)
    bb_before = bus.document.get_node(nid).mesh.bounding_box()
    bus.run_operation(TranslateOperation(), target_node_id=nid, params={"x": 5.0, "y": 0.0, "z": 0.0})
    _pump(bus)
    assert bus.undo()
    bb_after_undo = bus.document.get_node(nid).mesh.bounding_box()
    for i in range(2):
        for j in range(3):
            assert bb_after_undo[i][j] == pytest.approx(bb_before[i][j], abs=0.01)


def test_rotate_changes_bbox(bus):
    nid = _add_cube(bus)
    bus.run_operation(RotateOperation(), target_node_id=nid,
                      params={"axis": "Z", "angle_degrees": 45.0, "pivot": "Origin"})
    _pump(bus)
    node = bus.document.get_node(nid)
    # After 45° rotation around Z, the bbox should be wider
    bb = node.mesh.bounding_box()
    assert bb[1][0] - bb[0][0] > 1.0  # wider than original 1.0


def test_scale_doubles_bbox(bus):
    nid = _add_cube(bus)
    bus.run_operation(ScaleOperation(), target_node_id=nid,
                      params={"uniform": True, "factor": 2.0, "pivot": "Origin"})
    _pump(bus)
    bb = bus.document.get_node(nid).mesh.bounding_box()
    assert bb[0][0] == pytest.approx(-1.0)
    assert bb[1][0] == pytest.approx(1.0)


def test_mirror_flips_bbox(bus):
    nid = _add_cube(bus)
    # Translate cube to x=5 first
    bus.run_operation(TranslateOperation(), target_node_id=nid, params={"x": 5.0, "y": 0.0, "z": 0.0})
    _pump(bus)
    # Mirror through YZ plane
    bus.run_operation(MirrorOperation(), target_node_id=nid,
                      params={"plane": "YZ (X=0)", "offset": 0.0})
    _pump(bus)
    bb = bus.document.get_node(nid).mesh.bounding_box()
    # After mirror, the cube should be at x ≈ -5
    assert bb[0][0] == pytest.approx(-5.5, abs=0.1)
