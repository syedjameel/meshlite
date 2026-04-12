"""Tests for repair operations: auto_repair, remove_duplicates, find_self_intersections."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from meshlite.app_state.command_bus import CommandBus
from meshlite.app_state.document import Document
from meshlite.app_state.events import EventBus, OpCompleted
from meshlite.app_state.history import UndoStack
from meshlite.app_state.selection_model import SelectionModel
from meshlite.app_state.task_runner import TaskRunner
from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import make_cube
from meshlite.ops.inspect.find_self_intersections import FindSelfIntersectionsOperation
from meshlite.ops.repair.auto_repair import AutoRepairOperation
from meshlite.ops.repair.remove_duplicates import RemoveDuplicatesOperation
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


def test_auto_repair_on_clean_cube(bus):
    """Auto repair should succeed without errors on a clean cube."""
    nid = _add_cube(bus)
    seen: list[OpCompleted] = []
    bus.events.subscribe(OpCompleted, seen.append)

    bus.run_operation(AutoRepairOperation(), target_node_id=nid)
    _pump(bus)

    assert len(seen) == 1
    assert "fixMultipleEdges" in seen[0].info.get("steps", [])


def test_remove_duplicates_on_clean_cube(bus):
    """Remove duplicates should detect 0 disoriented faces on a clean cube."""
    nid = _add_cube(bus)
    seen: list[OpCompleted] = []
    bus.events.subscribe(OpCompleted, seen.append)

    bus.run_operation(RemoveDuplicatesOperation(), target_node_id=nid)
    _pump(bus)

    assert len(seen) == 1
    assert "0 disoriented" in seen[0].message


def test_fix_self_intersections_on_clean_cube(bus):
    """Fix self-intersections should succeed on a clean cube (nothing to fix)."""
    nid = _add_cube(bus)
    seen: list[OpCompleted] = []
    bus.events.subscribe(OpCompleted, seen.append)

    bus.run_operation(FindSelfIntersectionsOperation(), target_node_id=nid,
                      params={"approach": "Local (Relax)"})
    _pump(bus)

    assert len(seen) == 1


def test_auto_repair_on_open_cylinder(bus, open_cyl_path: Path):
    """Auto repair should work on an open cylinder without crashing."""
    from meshlite.ops.io.load_mesh import LoadMeshOperation
    bus.run_operation(LoadMeshOperation(), params={"path": str(open_cyl_path)})
    _pump(bus)
    nid = bus.selection.primary

    seen: list[OpCompleted] = []
    bus.events.subscribe(OpCompleted, seen.append)

    bus.run_operation(AutoRepairOperation(), target_node_id=nid)
    _pump(bus)

    assert len(seen) == 1
