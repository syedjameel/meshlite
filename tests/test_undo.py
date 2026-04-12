"""M4 — synthetic undo / redo tests.

Exercises :class:`UndoStack`, :class:`HistoryEntry`, and
:class:`CommandBus.undo`/``.redo`` against an in-memory document. No GL,
no worker threads — just snapshots.

The "real" undo round-trip across a worker-dispatched op lands in M10.
"""

from __future__ import annotations

import pytest

from meshlite.app_state.command_bus import CommandBus
from meshlite.app_state.document import Document
from meshlite.app_state.events import EventBus, NodeMeshReplaced
from meshlite.app_state.history import HistoryEntry, UndoStack
from meshlite.app_state.selection_model import SelectionModel
from meshlite.app_state.task_runner import TaskRunner
from meshlite.domain.mesh_data import MeshData
from meshlite.domain.mrm_shim import make_arrow, make_cube
from meshlite.utils.async_task import TaskManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cube() -> MeshData:
    return MeshData(mr=make_cube(), name="cube")


@pytest.fixture
def arrow() -> MeshData:
    return MeshData(mr=make_arrow((0, 0, 0), (1, 0, 0)), name="arrow")


@pytest.fixture
def doc_with_cube(cube: MeshData) -> tuple[Document, EventBus, str]:
    events = EventBus()
    doc = Document(events)
    node_id = doc.add_node(cube, name="cube")
    return doc, events, node_id


@pytest.fixture
def command_bus() -> CommandBus:
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


# ---------------------------------------------------------------------------
# UndoStack basic mechanics
# ---------------------------------------------------------------------------

def test_undostack_starts_empty() -> None:
    s = UndoStack()
    assert not s.can_undo()
    assert not s.can_redo()
    assert s.undo() is None
    assert s.redo() is None
    assert len(s) == 0


def test_push_then_undo_redo(cube: MeshData, arrow: MeshData) -> None:
    s = UndoStack()
    entry = HistoryEntry(
        label="Replace cube with arrow",
        affected_node_ids=("n1",),
        before={"n1": cube},
        after={"n1": arrow},
    )
    s.push(entry)
    assert s.can_undo()
    assert not s.can_redo()
    assert len(s) == 1
    assert s.peek_undo_label() == "Replace cube with arrow"

    popped = s.undo()
    assert popped is entry
    assert not s.can_undo()
    assert s.can_redo()
    assert s.peek_redo_label() == "Replace cube with arrow"

    redone = s.redo()
    assert redone is entry
    assert s.can_undo()
    assert not s.can_redo()


def test_push_clears_redo_stack(cube: MeshData, arrow: MeshData) -> None:
    s = UndoStack()
    e1 = HistoryEntry("op1", ("n1",), {"n1": cube}, {"n1": arrow})
    e2 = HistoryEntry("op2", ("n1",), {"n1": arrow}, {"n1": cube})
    s.push(e1)
    s.undo()
    assert s.can_redo()
    s.push(e2)
    assert not s.can_redo(), "pushing should clear redo stack"


def test_push_without_after_raises(cube: MeshData) -> None:
    s = UndoStack()
    entry = HistoryEntry("noop", ("n1",), {"n1": cube})  # after is empty
    with pytest.raises(ValueError):
        s.push(entry)


# ---------------------------------------------------------------------------
# Bounded growth
# ---------------------------------------------------------------------------

def test_max_depth_evicts_oldest(cube: MeshData) -> None:
    s = UndoStack(max_depth=3)
    for i in range(5):
        e = HistoryEntry(f"op{i}", ("n1",), {"n1": cube}, {"n1": cube})
        s.push(e)
    assert len(s) == 3
    # The 3 newest are op2, op3, op4. Top is op4.
    assert s.peek_undo_label() == "op4"
    s.undo()
    assert s.peek_undo_label() == "op3"
    s.undo()
    assert s.peek_undo_label() == "op2"
    s.undo()
    assert not s.can_undo(), "op0 and op1 must have been evicted"


def test_max_total_bytes_evicts_oldest(cube: MeshData) -> None:
    # Each entry is roughly cube heap bytes ×2 (before + after). Set the cap
    # so only one entry can fit.
    one = HistoryEntry("op", ("n",), {"n": cube}, {"n": cube})
    one_size = one.estimated_bytes()
    s = UndoStack(max_depth=999, max_total_bytes=int(one_size * 1.5))
    for i in range(4):
        s.push(HistoryEntry(f"op{i}", ("n",), {"n": cube}, {"n": cube}))
    assert len(s) == 1
    assert s.peek_undo_label() == "op3"


# ---------------------------------------------------------------------------
# Document mesh replacement + event emission
# ---------------------------------------------------------------------------

def test_document_replace_mesh_emits_event(
    doc_with_cube: tuple[Document, EventBus, str], arrow: MeshData
) -> None:
    doc, events, node_id = doc_with_cube
    seen: list[str] = []
    events.subscribe(NodeMeshReplaced, lambda e: seen.append(e.node_id))

    doc.replace_mesh(node_id, arrow)
    assert seen == [node_id]
    assert doc.get_node(node_id).mesh is arrow


def test_document_replace_invalidates_info_cache(
    doc_with_cube: tuple[Document, EventBus, str], arrow: MeshData
) -> None:
    doc, _events, node_id = doc_with_cube
    node = doc.get_node(node_id)
    node.info_cache = "stale"
    doc.replace_mesh(node_id, arrow)
    assert node.info_cache is None


def test_document_replace_unknown_node_raises(
    doc_with_cube: tuple[Document, EventBus, str], arrow: MeshData
) -> None:
    doc, _events, _node_id = doc_with_cube
    with pytest.raises(KeyError):
        doc.replace_mesh("not-a-node", arrow)


# ---------------------------------------------------------------------------
# CommandBus.undo / .redo round-trip across snapshots
# ---------------------------------------------------------------------------

def test_command_bus_undo_redo_round_trip(
    command_bus: CommandBus, cube: MeshData, arrow: MeshData
) -> None:
    """Push a HistoryEntry by hand, then exercise CommandBus.undo / .redo.

    Doesn't go through run_operation — that requires a worker, which is
    covered by the runtime smoke test in M4 and the real round trip in M10.
    """
    bus = command_bus
    node_id = bus.document.add_node(cube, name="cube")

    # Manually install the post-op state and a corresponding history entry.
    bus.document.replace_mesh(node_id, arrow)
    bus.history.push(
        HistoryEntry(
            label="manual swap",
            affected_node_ids=(node_id,),
            before={node_id: cube.clone()},
            after={node_id: arrow.clone()},
        )
    )
    assert bus.document.get_node(node_id).mesh is arrow

    assert bus.undo() is True
    assert bus.document.get_node(node_id).mesh.surface_area == pytest.approx(
        cube.surface_area
    )
    assert bus.history.can_redo()

    assert bus.redo() is True
    assert bus.document.get_node(node_id).mesh.surface_area == pytest.approx(
        arrow.surface_area
    )

    # Nothing left to redo.
    assert bus.redo() is False


def test_command_bus_undo_when_empty(command_bus: CommandBus) -> None:
    assert command_bus.undo() is False
    assert command_bus.redo() is False


# ---------------------------------------------------------------------------
# Selection model + EventBus sanity (these underpin the M6+ UI panels)
# ---------------------------------------------------------------------------

def test_selection_set_and_clear_emits_once() -> None:
    events = EventBus()
    selection = SelectionModel(events)
    seen: list = []
    from meshlite.app_state.events import SelectionChanged
    events.subscribe(SelectionChanged, lambda e: seen.append(e))

    selection.set(["a", "b"])
    assert len(seen) == 1
    assert selection.primary in {"a", "b"}
    assert selection.selected == frozenset({"a", "b"})

    selection.clear()
    assert len(seen) == 2
    assert selection.primary is None
    assert selection.selected == frozenset()

    # Idempotent — clearing an empty selection should not emit again.
    selection.clear()
    assert len(seen) == 2


def test_selection_toggle() -> None:
    events = EventBus()
    selection = SelectionModel(events)
    selection.toggle("x")
    assert "x" in selection.selected
    selection.toggle("x")
    assert "x" not in selection.selected
