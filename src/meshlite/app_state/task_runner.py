"""``TaskRunner`` — bridges the worker pool to main-thread finalization.

The :class:`TaskManager` from ``utils.async_task`` runs callables on a
worker pool with progress reporting and cancellation. ``TaskRunner`` adds
two things on top:

1. **A main-thread callback queue.** When a task completes on a worker, the
   worker can't touch GL or ImGui state. Instead it pushes a callable into
   the runner's main-thread queue, which the UI loop drains every frame
   from ``before_imgui_render``.

2. **A simple submit-with-finalize API.** Callers register a worker function
   *and* a finalize function in one call. The runner takes care of dispatch,
   queueing, and cleanup.

This is the only piece that knows the dance from "task done on worker" to
"main thread runs the finalize callback". The CommandBus uses it; the M4
counter debug op uses it directly.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from meshlite.utils.async_task import AsyncTask, TaskManager, TaskStatus

_LOGGER = logging.getLogger("meshlite.task_runner")

WorkerFn = Callable[..., Any]
FinalizeFn = Callable[[AsyncTask], None]


@dataclass
class _Submission:
    task_id: str
    label: str
    on_finalize: FinalizeFn | None


class TaskRunner:
    """Submits work to a thread pool and dispatches results on the main thread."""

    def __init__(self, task_manager: TaskManager) -> None:
        self._tm = task_manager
        self._main_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._submissions: dict[str, _Submission] = {}

        # Captured at construction so the rest of the runner can sanity-check
        # who is calling main-thread methods. Tests run on the main thread of
        # the test process, so this naturally Just Works in pytest.
        self._main_thread = threading.current_thread()

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(
        self,
        label: str,
        fn: WorkerFn,
        *args: Any,
        on_finalize: FinalizeFn | None = None,
        **kwargs: Any,
    ) -> str:
        """Run ``fn(*args, **kwargs)`` on a worker thread.

        Args:
            label: Human-readable label (status bar / log).
            fn: The callable to run on the worker. The runner injects two
                extra kwargs: ``report_progress`` and ``is_canceled``.
            on_finalize: Optional callback invoked on the **main thread**
                after the task completes (success, failure, or cancellation).
                Receives the :class:`AsyncTask` so it can read ``status`` /
                ``result`` / ``error``.
        """
        self._assert_main_thread("submit")

        task_id = f"task_{int(time.time() * 1000)}_{id(fn) & 0xFFFF:04x}"
        self._tm.create_task(task_id, fn, *args, **kwargs)
        self._tm.start_task(task_id)
        self._submissions[task_id] = _Submission(task_id, label, on_finalize)
        _LOGGER.debug("submitted task %s (%s)", task_id, label)
        return task_id

    def cancel(self, task_id: str) -> bool:
        return self._tm.cancel_task(task_id)

    # ------------------------------------------------------------------
    # Main-thread callback queue
    # ------------------------------------------------------------------

    def post_to_main(self, fn: Callable[[], None]) -> None:
        """Schedule ``fn`` to run on the main thread on its next drain.

        Safe to call from any thread.
        """
        self._main_queue.put(fn)

    def drain_main_thread_queue(self) -> int:
        """Run all queued main-thread callbacks. Returns how many ran."""
        self._assert_main_thread("drain_main_thread_queue")
        count = 0
        while True:
            try:
                fn = self._main_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:                          # noqa: BLE001
                _LOGGER.exception("main-thread callback raised: %s", e)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Per-frame task tick
    # ------------------------------------------------------------------

    def update_tasks(self) -> None:
        """Advance task state machines and dispatch finalize callbacks.

        Called every frame from ``MeshLiteApp.before_imgui_render``.
        """
        self._assert_main_thread("update_tasks")
        for task_id in self._tm.update_all():
            task = self._tm.get_task(task_id)
            if task is None:
                continue
            if task.status not in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELED,
            ):
                continue

            sub = self._submissions.pop(task_id, None)
            if sub is not None and sub.on_finalize is not None:
                try:
                    sub.on_finalize(task)
                except Exception as e:                      # noqa: BLE001
                    _LOGGER.exception(
                        "finalize callback for %s raised: %s", sub.label, e
                    )
            self._tm.remove_task(task_id)

    # ------------------------------------------------------------------
    # Sundry
    # ------------------------------------------------------------------

    @property
    def active_count(self) -> int:
        return self._tm.active_task_count

    def _assert_main_thread(self, who: str) -> None:
        if threading.current_thread() is not self._main_thread:
            raise RuntimeError(
                f"TaskRunner.{who} must be called on the main thread"
            )
