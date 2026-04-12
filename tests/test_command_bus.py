"""M4 — CommandBus end-to-end integration tests.

These exercise the full UI-less worker → main-thread roundtrip:

    main thread:
        bus.run_operation(op)
            → TaskRunner.submit
            → TaskManager.start_task
                worker thread:
                    op.run(...)
                    main_queue.put(finalize)

    main thread (test polls):
        bus.task_runner.update_tasks()  ← drains TaskManager
        bus.task_runner.drain_main_thread_queue()  ← runs finalize

The runtime smoke test in the GUI uses the same code path; this test
proves it works without needing a window.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from meshlite.app_state.command_bus import CommandBus
from meshlite.app_state.document import Document
from meshlite.app_state.events import (
    EventBus,
    OpCanceled,
    OpCompleted,
    OpFailed,
    OpStarted,
)
from meshlite.app_state.history import UndoStack
from meshlite.app_state.selection_model import SelectionModel
from meshlite.app_state.task_runner import TaskRunner
from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import make_arrow, make_cube
from meshlite.ops._dev.counter_op import CounterOp
from meshlite.ops.base import (
    Operation,
    OperationCanceled,
    OperationContext,
    OperationError,
    OperationResult,
)
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
    """Tick the bus until no tasks are active or until ``max_seconds`` elapse."""
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        bus.task_runner.update_tasks()
        bus.task_runner.drain_main_thread_queue()
        if not bus.all_active_ops():
            return
        time.sleep(0.01)
    raise TimeoutError("operations did not finalize within deadline")


# ---------------------------------------------------------------------------
# Counter op end-to-end (no mesh, undoable=False)
# ---------------------------------------------------------------------------

def test_counter_op_end_to_end(bus: CommandBus) -> None:
    seen_started: list[OpStarted] = []
    seen_completed: list[OpCompleted] = []
    bus.events.subscribe(OpStarted, seen_started.append)
    bus.events.subscribe(OpCompleted, seen_completed.append)

    task_id = bus.run_operation(CounterOp(steps=3, step_seconds=0.0))
    assert task_id
    assert seen_started, "OpStarted should be emitted synchronously from run_operation"
    assert seen_started[0].op_id == "_dev.counter"

    _pump(bus)

    assert len(seen_completed) == 1
    completed = seen_completed[0]
    assert completed.op_id == "_dev.counter"
    assert completed.info["ticks"] == 3
    assert "completed" in completed.message

    # No history pushed (counter is undoable=False).
    assert not bus.history.can_undo()


# ---------------------------------------------------------------------------
# Mesh-mutating op — installs result + pushes history
# ---------------------------------------------------------------------------

class _ReplaceWithArrowOp(Operation):
    """Test op: ignore the input mesh, return a brand-new arrow."""

    id = "_test.replace_with_arrow"
    label = "Replace with arrow"
    undoable = True

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        ctx.report_progress(0.5, "building arrow...")
        arrow = MeshData(mr=make_arrow((0, 0, 0), (2, 0, 0)), name="arrow")
        return OperationResult(mesh=arrow, message="replaced with arrow")


def test_mesh_op_replaces_node_and_pushes_history(bus: CommandBus) -> None:
    cube = MeshData(mr=make_cube(), name="cube")
    node_id = bus.document.add_node(cube, name="cube")
    original_area = cube.surface_area

    bus.run_operation(_ReplaceWithArrowOp(), target_node_id=node_id)
    _pump(bus)

    new_node = bus.document.get_node(node_id)
    assert new_node is not None
    assert new_node.mesh.name == "arrow"
    assert new_node.mesh.surface_area != pytest.approx(original_area)

    # History should have one entry now.
    assert bus.history.can_undo()
    assert bus.history.peek_undo_label() == "Replace with arrow"

    # Undo restores the original cube area.
    assert bus.undo() is True
    assert bus.document.get_node(node_id).mesh.surface_area == pytest.approx(
        original_area
    )

    # Redo brings the arrow back.
    assert bus.redo() is True
    assert bus.document.get_node(node_id).mesh.surface_area != pytest.approx(
        original_area
    )


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------

class _FailingOp(Operation):
    id = "_test.failing"
    label = "Always fails"
    undoable = False

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        raise OperationError("kaboom")


def test_failing_op_emits_op_failed(bus: CommandBus) -> None:
    seen: list[OpFailed] = []
    bus.events.subscribe(OpFailed, seen.append)

    bus.run_operation(_FailingOp())
    _pump(bus)

    assert len(seen) == 1
    assert seen[0].op_id == "_test.failing"
    assert "kaboom" in seen[0].error
    # No history entry because the op never produced a result.
    assert not bus.history.can_undo()


# ---------------------------------------------------------------------------
# Cancellation path
# ---------------------------------------------------------------------------

class _CancelableOp(Operation):
    id = "_test.cancelable"
    label = "Cancelable"
    undoable = False

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        for _ in range(100):
            if ctx.is_canceled():
                raise OperationCanceled()
            time.sleep(0.005)
        return OperationResult(mesh=None, message="completed normally")


def test_cancelable_op_can_be_canceled(bus: CommandBus) -> None:
    seen: list[OpCanceled] = []
    bus.events.subscribe(OpCanceled, seen.append)

    task_id = bus.run_operation(_CancelableOp())
    # Tick once so the worker has a chance to start, then cancel.
    bus.task_runner.update_tasks()
    bus.task_runner.drain_main_thread_queue()
    bus.cancel(task_id)
    _pump(bus)

    assert len(seen) == 1
    assert seen[0].op_id == "_test.cancelable"
