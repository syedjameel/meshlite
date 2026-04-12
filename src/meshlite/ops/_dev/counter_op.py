"""``CounterOp`` — runtime smoke test for the M4 task pipeline.

Not a real mesh operation. It sleeps in steps and reports progress, so we
can prove the full chain works end-to-end:

    UI button (main thread)
        → CommandBus.run_operation
        → TaskRunner.submit  →  worker pool
        → CounterOp.run (worker thread, sleeps + reports progress)
        → main_queue.put(finalize)
        → drain_main_thread_queue (next frame)
        → CommandBus._finalize  →  OpCompleted event
        → UI subscriber logs the message

The op takes no mesh and produces no mesh, so its result is purely
informational. ``undoable=False`` since there's nothing to undo.
"""

from __future__ import annotations

import time
from typing import Any

from meshlite.domain.mesh_data import MeshData

from ..base import Operation, OperationCanceled, OperationContext, OperationResult


class CounterOp(Operation):
    """Sleep in N steps, reporting progress at each."""

    id = "_dev.counter"
    label = "Debug: Counter"
    undoable = False

    def __init__(self, *, steps: int = 5, step_seconds: float = 0.1) -> None:
        self.steps = steps
        self.step_seconds = step_seconds

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        # Allow caller to override via params, otherwise use instance defaults.
        steps = int(params.get("steps", self.steps))
        step_seconds = float(params.get("step_seconds", self.step_seconds))

        ctx.report_progress(0.0, "starting...")
        for i in range(steps):
            if ctx.is_canceled():
                raise OperationCanceled()
            time.sleep(step_seconds)
            ctx.report_progress(
                (i + 1) / steps,
                f"tick {i + 1}/{steps}",
            )

        return OperationResult(
            mesh=None,
            info={"ticks": steps, "elapsed_s": steps * step_seconds},
            message=f"counter completed {steps} ticks",
        )
