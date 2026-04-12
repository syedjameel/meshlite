"""Background task execution with progress reporting and cancellation.

Ported from the existing project's ``utils/async_task.py``. The only change
is dropping the ``config`` import — ``TaskManager`` now takes ``max_workers``
directly. The progress / result queue + cancel-event design is unchanged.

Usage pattern:

    tm = TaskManager(max_workers=4)
    task = tm.create_task("load_mesh_42", load_fn, "/path/to/mesh.stl")
    tm.start_task(task.task_id)

    # in your per-frame callback:
    for changed_id in tm.update_all():
        t = tm.get_task(changed_id)
        if t.status == TaskStatus.COMPLETED:
            do_something_with(t.result)
            tm.remove_task(changed_id)

The function passed to ``create_task`` is invoked with two extra kwargs
injected by the runner — ``report_progress`` and ``is_canceled``:

    def load_fn(path, *, report_progress, is_canceled):
        report_progress(0.1, "reading...")
        if is_canceled():
            return None
        ...
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class AsyncTask:
    """A function executed asynchronously with progress reporting."""

    def __init__(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> None:
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.status = TaskStatus.PENDING
        self.progress: float = 0.0
        self.progress_message: str = ""
        self.result: Any = None
        self.error: BaseException | None = None
        self.thread: threading.Thread | None = None
        self._future = None
        self._progress_queue: queue.Queue[tuple[float, str]] = queue.Queue()
        self._result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue()
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the task in a background thread."""
        if self.status == TaskStatus.RUNNING:
            return
        self._reset_state()
        self.thread = threading.Thread(target=self._run_task, daemon=True)
        self.thread.start()

    def start_with_executor(self, executor: ThreadPoolExecutor) -> None:
        """Start the task on a thread pool executor."""
        if self.status == TaskStatus.RUNNING:
            return
        self._reset_state()
        self._future = executor.submit(self._run_task)

    def _reset_state(self) -> None:
        self.status = TaskStatus.RUNNING
        self.progress = 0.0
        self.progress_message = ""
        self.result = None
        self.error = None
        self.kwargs["report_progress"] = self._report_progress
        self.kwargs["is_canceled"] = self._is_canceled

    def _run_task(self) -> None:
        try:
            result = self.func(*self.args, **self.kwargs)
            self._result_queue.put((True, result))
        except BaseException as e:  # noqa: BLE001 — we want to capture everything
            self._result_queue.put((False, e))

    # ------------------------------------------------------------------
    # Worker-thread side
    # ------------------------------------------------------------------

    def _report_progress(self, progress: float, message: str = "") -> None:
        if 0.0 <= progress <= 1.0:
            self._progress_queue.put((progress, message))

    def _is_canceled(self) -> bool:
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    # Main-thread side
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation. Worker checks via ``is_canceled``."""
        if self.status == TaskStatus.RUNNING:
            self._cancel_event.set()
            if self._future is not None:
                self._future.cancel()

    def update(self) -> bool:
        """Drain progress + result queues. Returns True if state changed."""
        if self.status != TaskStatus.RUNNING:
            return False

        state_changed = False

        # Process all available progress updates.
        while not self._progress_queue.empty():
            try:
                progress, message = self._progress_queue.get_nowait()
            except queue.Empty:
                break
            self.progress = progress
            self.progress_message = message
            state_changed = True

        # Process completion.
        if not self._result_queue.empty():
            try:
                success, payload = self._result_queue.get_nowait()
            except queue.Empty:
                return state_changed

            if self._cancel_event.is_set():
                self.status = TaskStatus.CANCELED
                if success:
                    self.result = payload
            elif success:
                self.result = payload
                self.status = TaskStatus.COMPLETED
            else:
                self.error = payload
                self.status = TaskStatus.FAILED
            state_changed = True

        return state_changed


class TaskManager:
    """Manages a pool of :class:`AsyncTask`s."""

    def __init__(self, max_workers: int = 4, *, thread_name_prefix: str = "MeshLite") -> None:
        self.tasks: dict[str, AsyncTask] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._active_task_count = 0
        self._started_tasks: set[str] = set()

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def create_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> AsyncTask:
        task = AsyncTask(task_id, func, args, kwargs)
        self.tasks[task_id] = task
        return task

    def start_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.start_with_executor(self._executor)
        self._active_task_count += 1
        self._started_tasks.add(task_id)
        return True

    def cancel_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.cancel()
        return True

    def update_all(self) -> list[str]:
        """Drain queues for every task. Returns IDs whose state changed."""
        changed: list[str] = []
        for task_id, task in list(self.tasks.items()):
            if task.update():
                changed.append(task_id)
        return changed

    def get_task(self, task_id: str) -> AsyncTask | None:
        return self.tasks.get(task_id)

    def remove_task(self, task_id: str) -> bool:
        task = self.tasks.pop(task_id, None)
        if task is None:
            return False
        if task_id in self._started_tasks:
            self._started_tasks.discard(task_id)
            self._active_task_count = max(0, self._active_task_count - 1)
        return True

    def shutdown(self) -> None:
        for task in self.tasks.values():
            if task.status == TaskStatus.RUNNING:
                task.cancel()
        self._executor.shutdown(wait=False)

    @property
    def active_task_count(self) -> int:
        return self._active_task_count
