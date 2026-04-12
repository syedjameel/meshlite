"""M8 — FillHolesOperation end-to-end tests.

Exercises the full pipeline: dispatch via CommandBus on a holed fixture,
pump tasks, verify the mesh is watertight after fill. Tests undo restores
the original (not watertight). Tests the different metric choices.
"""

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
from meshlite.ops.io.load_mesh import LoadMeshOperation
from meshlite.ops.repair.fill_holes import FillHolesOperation
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


def _pump(bus: CommandBus, *, max_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        bus.task_runner.update_tasks()
        bus.task_runner.drain_main_thread_queue()
        if not bus.all_active_ops():
            return
        time.sleep(0.01)
    raise TimeoutError("operations did not finalize within deadline")


def _load_and_select(bus: CommandBus, path: Path) -> str:
    """Load a mesh and return its node_id (already auto-selected by bus)."""
    bus.run_operation(LoadMeshOperation(), params={"path": str(path)})
    _pump(bus)
    node_id = bus.selection.primary
    assert node_id is not None
    return node_id


# ---------------------------------------------------------------------------
# Fill holes — basic
# ---------------------------------------------------------------------------

def test_fill_holes_makes_watertight(bus: CommandBus, open_cyl_path: Path) -> None:
    node_id = _load_and_select(bus, open_cyl_path)
    node = bus.document.get_node(node_id)
    assert not node.mesh.is_watertight
    assert node.mesh.num_holes == 2

    seen: list[OpCompleted] = []
    bus.events.subscribe(OpCompleted, seen.append)

    bus.run_operation(
        FillHolesOperation(),
        target_node_id=node_id,
        params={"metric": "Universal", "max_subdivisions": 20},
    )
    _pump(bus)

    assert len(seen) == 1
    assert seen[0].info["filled"] == 2
    assert seen[0].info["watertight"] is True

    node = bus.document.get_node(node_id)
    assert node.mesh.is_watertight
    assert node.mesh.num_holes == 0


def test_fill_holes_on_already_watertight(bus: CommandBus) -> None:
    """Filling holes on a mesh with no holes should return it unchanged."""
    cube = MeshData(mr=make_cube(), name="cube")
    node_id = bus.document.add_node(cube, name="cube")
    bus.selection.set([node_id])

    seen: list[OpCompleted] = []
    bus.events.subscribe(OpCompleted, seen.append)

    bus.run_operation(
        FillHolesOperation(),
        target_node_id=node_id,
        params={"metric": "Universal", "max_subdivisions": 20},
    )
    _pump(bus)

    assert len(seen) == 1
    assert seen[0].info["filled"] == 0
    assert "already watertight" in seen[0].message.lower()


# ---------------------------------------------------------------------------
# Undo/redo round trip
# ---------------------------------------------------------------------------

def test_fill_holes_undo_restores_original(
    bus: CommandBus, open_cyl_path: Path
) -> None:
    node_id = _load_and_select(bus, open_cyl_path)
    node = bus.document.get_node(node_id)
    original_holes = node.mesh.num_holes
    assert original_holes > 0

    bus.run_operation(
        FillHolesOperation(),
        target_node_id=node_id,
        params={"metric": "Universal"},
    )
    _pump(bus)

    assert bus.document.get_node(node_id).mesh.is_watertight
    assert bus.history.can_undo()

    # Undo → back to holed state.
    assert bus.undo() is True
    node = bus.document.get_node(node_id)
    assert not node.mesh.is_watertight
    assert node.mesh.num_holes == original_holes

    # Redo → watertight again.
    assert bus.redo() is True
    assert bus.document.get_node(node_id).mesh.is_watertight


# ---------------------------------------------------------------------------
# Different metrics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metric", ["Default", "Universal", "Edge Length", "Circumscribed"])
def test_fill_holes_with_each_metric(
    bus: CommandBus, open_cyl_path: Path, metric: str
) -> None:
    node_id = _load_and_select(bus, open_cyl_path)

    bus.run_operation(
        FillHolesOperation(),
        target_node_id=node_id,
        params={"metric": metric},
    )
    _pump(bus)

    node = bus.document.get_node(node_id)
    assert node.mesh.is_watertight, f"metric {metric!r} failed to make mesh watertight"


# ---------------------------------------------------------------------------
# Info cache invalidation after fill
# ---------------------------------------------------------------------------

def test_info_cache_invalidated_after_fill(
    bus: CommandBus, open_cyl_path: Path
) -> None:
    """After fill-holes replaces the mesh, info_cache must be None."""
    node_id = _load_and_select(bus, open_cyl_path)
    node = bus.document.get_node(node_id)
    # Prime the cache.
    from meshlite.domain.mesh_info import compute
    node.info_cache = compute(node.mesh)
    assert node.info_cache is not None

    bus.run_operation(
        FillHolesOperation(),
        target_node_id=node_id,
    )
    _pump(bus)

    # After the op, the bus called Document.replace_mesh which resets cache.
    assert bus.document.get_node(node_id).info_cache is None
