"""M5 — LoadMeshOperation + SaveMeshOperation end-to-end tests.

These dispatch the real ops through the real :class:`CommandBus` (no GUI).
After the worker completes and the bus finalizes, we check that the
document state and undo stack reflect what should have happened.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from meshlite.app_state.command_bus import CommandBus
from meshlite.app_state.document import Document
from meshlite.app_state.events import EventBus, NodeAdded, OpCompleted, OpFailed
from meshlite.app_state.history import UndoStack
from meshlite.app_state.selection_model import SelectionModel
from meshlite.app_state.task_runner import TaskRunner
from meshlite.ops.io.load_mesh import LoadMeshOperation
from meshlite.ops.io.save_mesh import SaveMeshOperation
from meshlite.utils.async_task import TaskManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus() -> CommandBus:
    events = EventBus()
    doc = Document(events)
    selection = SelectionModel(events)
    history = UndoStack()
    tm = TaskManager(max_workers=2)
    runner = TaskRunner(tm)
    return CommandBus(
        document=doc,
        selection=selection,
        history=history,
        task_runner=runner,
        events=events,
    )


def _pump(bus: CommandBus, *, max_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        bus.task_runner.update_tasks()
        bus.task_runner.drain_main_thread_queue()
        if not bus.all_active_ops():
            return
        time.sleep(0.01)
    raise TimeoutError("operation did not finalize within deadline")


# ---------------------------------------------------------------------------
# LoadMeshOperation
# ---------------------------------------------------------------------------

def test_load_mesh_creates_node(bus: CommandBus, cube_stl_path: Path) -> None:
    seen_added: list[NodeAdded] = []
    seen_completed: list[OpCompleted] = []
    bus.events.subscribe(NodeAdded, seen_added.append)
    bus.events.subscribe(OpCompleted, seen_completed.append)

    bus.run_operation(LoadMeshOperation(), params={"path": str(cube_stl_path)})
    _pump(bus)

    assert len(bus.document) == 1
    assert len(seen_added) == 1
    assert len(seen_completed) == 1

    node = bus.document.get_node(seen_added[0].node_id)
    assert node is not None
    assert node.name == "cube.stl"
    assert node.source_path == cube_stl_path.resolve()
    assert node.mesh.num_vertices == 8
    assert node.mesh.num_faces == 12
    assert node.mesh.is_watertight

    # Auto-selected by the bus.
    assert bus.selection.primary == node.id

    # Info dict round-trips through OpCompleted.
    info = seen_completed[0].info
    assert info["vertices"] == 8
    assert info["faces"] == 12
    assert info["watertight"] is True
    assert info["holes"] == 0


def test_load_mesh_missing_path_fails(bus: CommandBus) -> None:
    seen: list[OpFailed] = []
    bus.events.subscribe(OpFailed, seen.append)

    bus.run_operation(LoadMeshOperation(), params={"path": ""})
    _pump(bus)

    assert len(seen) == 1
    assert "no path" in seen[0].error.lower()
    assert len(bus.document) == 0


def test_load_mesh_unsupported_extension_fails(
    bus: CommandBus, tmp_path: Path
) -> None:
    bogus = tmp_path / "thing.xyz"
    bogus.write_text("not a mesh")
    seen: list[OpFailed] = []
    bus.events.subscribe(OpFailed, seen.append)

    bus.run_operation(LoadMeshOperation(), params={"path": str(bogus)})
    _pump(bus)

    assert len(seen) == 1
    assert ".xyz" in seen[0].error or "supported" in seen[0].error.lower()


def test_load_mesh_nonexistent_path_fails(
    bus: CommandBus, tmp_path: Path
) -> None:
    seen: list[OpFailed] = []
    bus.events.subscribe(OpFailed, seen.append)

    bus.run_operation(
        LoadMeshOperation(),
        params={"path": str(tmp_path / "missing.stl")},
    )
    _pump(bus)

    assert len(seen) == 1


# ---------------------------------------------------------------------------
# SaveMeshOperation
# ---------------------------------------------------------------------------

def test_save_mesh_round_trip(
    bus: CommandBus, cube_stl_path: Path, tmp_path: Path
) -> None:
    """Load → Save → reload yields a mesh with the same counts."""
    bus.run_operation(LoadMeshOperation(), params={"path": str(cube_stl_path)})
    _pump(bus)
    node_id = bus.selection.primary
    assert node_id is not None

    out = tmp_path / "round_trip.stl"
    bus.run_operation(
        SaveMeshOperation(),
        target_node_id=node_id,
        params={"path": str(out)},
    )
    _pump(bus)
    assert out.exists()
    assert out.stat().st_size > 0

    # Reload via the same op and check the counts match.
    bus.run_operation(LoadMeshOperation(), params={"path": str(out)})
    _pump(bus)
    assert len(bus.document) == 2
    reloaded = bus.document.all_nodes()[1]
    assert reloaded.mesh.num_vertices == 8
    assert reloaded.mesh.num_faces == 12
    assert reloaded.mesh.is_watertight


def test_save_without_target_fails(bus: CommandBus, tmp_path: Path) -> None:
    seen: list[OpFailed] = []
    bus.events.subscribe(OpFailed, seen.append)

    # No target_node_id → worker gets mesh=None → SaveMeshOperation raises.
    bus.run_operation(
        SaveMeshOperation(),
        params={"path": str(tmp_path / "out.stl")},
    )
    _pump(bus)

    assert len(seen) == 1
    assert "requires a target" in seen[0].error.lower()


def test_save_unsupported_extension_fails(
    bus: CommandBus, cube_stl_path: Path, tmp_path: Path
) -> None:
    bus.run_operation(LoadMeshOperation(), params={"path": str(cube_stl_path)})
    _pump(bus)
    node_id = bus.selection.primary
    assert node_id is not None

    seen: list[OpFailed] = []
    bus.events.subscribe(OpFailed, seen.append)
    bus.run_operation(
        SaveMeshOperation(),
        target_node_id=node_id,
        params={"path": str(tmp_path / "out.xyz")},
    )
    _pump(bus)

    assert len(seen) == 1
