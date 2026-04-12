"""``CommandBus`` — the single dispatch point for operations.

Plan §3 ("Operations framework — the most critical surface") names this as
one of the five files that define the architecture. Every UI invocation of
an op (menu item, command palette, sidebar button, keybind) routes through
:meth:`CommandBus.run_operation`. The bus does in one place:

1. **Snapshot** the affected node's mesh into a :class:`HistoryEntry.before`
   (only if the op is ``undoable`` and has a target node).
2. **Dispatch** the op to the worker pool via :class:`TaskRunner`, passing
   it a *clone* of the mesh — workers never see the live document state.
3. **Finalize on the main thread**: when the worker returns, install the
   result via :meth:`Document.replace_mesh`, complete the
   :class:`HistoryEntry.after`, push it to the :class:`UndoStack`, and emit
   :class:`OpCompleted`.
4. **Track the active op** so the status bar / progress overlay can read it.

In M4 the bus accepts an :class:`Operation` instance directly. M5 will
introduce the registry and add a sibling ``run_op_id(op_id, params)`` method
that resolves the id through the registry first.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from meshlite.domain.mesh_data import MeshData
from meshlite.ops.base import (
    Operation,
    OperationCanceled,
    OperationContext,
    OperationResult,
)
from meshlite.utils.async_task import AsyncTask, TaskStatus

from .document import Document
from .events import (
    EventBus,
    OpCanceled,
    OpCompleted,
    OpFailed,
    OpStarted,
)
from .history import HistoryEntry, UndoStack
from .selection_model import SelectionModel
from .task_runner import TaskRunner

_LOGGER = logging.getLogger("meshlite.command_bus")


@dataclass
class ActiveOp:
    """The op currently in flight, for status-bar / progress-overlay reads."""

    task_id: str
    op_id: str
    label: str
    target_node_id: str | None
    started_at: float


class CommandBus:
    """Single dispatch point for mesh operations.

    Wires together: :class:`Document`, :class:`SelectionModel`,
    :class:`UndoStack`, :class:`TaskRunner`, and :class:`EventBus`.
    """

    def __init__(
        self,
        *,
        document: Document,
        selection: SelectionModel,
        history: UndoStack,
        task_runner: TaskRunner,
        events: EventBus,
    ) -> None:
        self.document = document
        self.selection = selection
        self.history = history
        self.task_runner = task_runner
        self.events = events
        self._active_ops: dict[str, ActiveOp] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_operation(
        self,
        op: Operation,
        *,
        target_node_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Dispatch an op. Returns its task id.

        The actual execution happens on a worker thread; this method only
        snapshots, kicks off the task, and returns immediately. The result
        is installed by :meth:`_finalize`, which runs on the main thread on
        a future frame.
        """
        params = dict(params or {})

        # Snapshot the live mesh (if any) for undo. Cloning is safe — M2
        # verified that ``MeshData.clone()`` is a true deep copy.
        before_snap: dict[str, MeshData] = {}
        worker_mesh: MeshData | None = None
        if target_node_id is not None:
            node = self.document.get_node(target_node_id)
            if node is None:
                raise KeyError(f"unknown target node: {target_node_id}")
            worker_mesh = node.mesh.clone()
            if op.undoable:
                before_snap[target_node_id] = node.mesh.clone()

        # Submit the worker.
        task_id = self.task_runner.submit(
            op.label,
            self._worker_entry,
            op,
            worker_mesh,
            params,
            on_finalize=lambda task: self._finalize(
                task=task,
                op=op,
                target_node_id=target_node_id,
                before_snap=before_snap,
            ),
        )

        active = ActiveOp(
            task_id=task_id,
            op_id=op.id,
            label=op.label,
            target_node_id=target_node_id,
            started_at=time.monotonic(),
        )
        self._active_ops[task_id] = active
        self.events.emit(OpStarted(task_id=task_id, op_id=op.id, label=op.label))
        _LOGGER.info("op start: %s (task=%s)", op.id, task_id)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Request cancellation of an in-flight op."""
        return self.task_runner.cancel(task_id)

    def active_op(self, task_id: str) -> ActiveOp | None:
        return self._active_ops.get(task_id)

    def all_active_ops(self) -> list[ActiveOp]:
        return list(self._active_ops.values())

    # ------------------------------------------------------------------
    # Worker side — runs on the thread pool, MUST NOT touch GL or ImGui
    # ------------------------------------------------------------------

    @staticmethod
    def _worker_entry(
        op: Operation,
        mesh: MeshData | None,
        params: dict[str, Any],
        *,
        report_progress,
        is_canceled,
    ) -> OperationResult:
        ctx = OperationContext(
            report_progress=report_progress,
            is_canceled=is_canceled,
            op_id=op.id,
        )
        return op.run(mesh, params, ctx)

    # ------------------------------------------------------------------
    # Main-thread finalization
    # ------------------------------------------------------------------

    def _finalize(
        self,
        *,
        task: AsyncTask,
        op: Operation,
        target_node_id: str | None,
        before_snap: dict[str, MeshData],
    ) -> None:
        # Sanity: this must run on the main thread.
        assert threading.current_thread() is self.task_runner._main_thread, (
            "CommandBus._finalize ran off the main thread — task runner bug"
        )

        self._active_ops.pop(task.task_id, None)

        # Failure path.
        if task.status == TaskStatus.FAILED:
            err = task.error
            if isinstance(err, OperationCanceled):
                _LOGGER.info("op canceled: %s", op.id)
                self.events.emit(OpCanceled(task_id=task.task_id, op_id=op.id))
                return
            msg = str(err) if err else "unknown error"
            _LOGGER.error("op failed: %s — %s", op.id, msg)
            self.events.emit(
                OpFailed(task_id=task.task_id, op_id=op.id, error=msg)
            )
            return

        if task.status == TaskStatus.CANCELED:
            _LOGGER.info("op canceled: %s", op.id)
            self.events.emit(OpCanceled(task_id=task.task_id, op_id=op.id))
            return

        # Completed.
        result: OperationResult | None = task.result
        if result is None:
            _LOGGER.warning("op %s returned None — treating as no-op", op.id)
            return

        # Install the result.
        # Three cases:
        #   (a) creates_node + result.mesh   → add a brand-new node
        #   (b) target_node_id + result.mesh → replace existing node's mesh
        #   (c) otherwise (e.g. save, debug) → no document mutation
        if op.creates_node and result.mesh is not None:
            new_id = self.document.add_node(
                result.mesh,
                name=result.mesh.name,
                source_path=result.mesh.source_path,
            )
            _LOGGER.debug("created node %s from %s", new_id, op.id)
            # Auto-select the freshly added node so M5's "active mesh"
            # picker doesn't need a manual click after every load.
            self.selection.set([new_id])
        elif result.mesh is not None and target_node_id is not None:
            self.document.replace_mesh(target_node_id, result.mesh)

            # Push to history (only for in-place mesh replacement, not
            # for create-node ops — those are not undoable in M5; M10 will
            # add proper add/remove undo support).
            if op.undoable and before_snap:
                # No need to clone result.mesh here — undo/redo clone
                # snapshots when applying them, and replace_mesh (above)
                # installs the reference without mutating it later.
                entry = HistoryEntry(
                    label=op.label,
                    affected_node_ids=tuple(before_snap.keys()),
                    before=before_snap,
                    after={target_node_id: result.mesh},
                )
                self.history.push(entry)

        self.events.emit(
            OpCompleted(
                task_id=task.task_id,
                op_id=op.id,
                info=result.info,
                message=result.message,
            )
        )
        _LOGGER.info("op done: %s — %s", op.id, result.message or "(no message)")

    # ------------------------------------------------------------------
    # Undo / redo (M10 will wire the keybinds; the API is here for tests)
    # ------------------------------------------------------------------

    def undo(self) -> bool:
        entry = self.history.undo()
        if entry is None:
            return False
        for node_id, snap in entry.before.items():
            if node_id in self.document:
                self.document.replace_mesh(node_id, snap.clone())
        return True

    def redo(self) -> bool:
        entry = self.history.redo()
        if entry is None:
            return False
        for node_id, snap in entry.after.items():
            if node_id in self.document:
                self.document.replace_mesh(node_id, snap.clone())
        return True
