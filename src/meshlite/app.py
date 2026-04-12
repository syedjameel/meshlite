"""MeshLiteApp — the top-level application object.

Constructs the app's stateless managers (events, document, selection,
history, task runner, command bus) on the main thread, then hands control
to the UI runner. The renderer is intentionally NOT constructed in
``__init__`` because it needs a live OpenGL context — that happens in
``post_init``, which ``hello_imgui`` fires once the window and GL context
are ready.

Init order matters (Plan §7):

    1. Stateless managers — events, history, task_manager
    2. Document, Selection (depend only on events)
    3. CommandBus (depends on all of the above)
    4. UIRunner constructed but not started
    5. ``hello_imgui.run`` starts → loads fonts → creates GL context
    6. ``post_init`` fires → Renderer created → AppReady emitted
    7. UI panels begin rendering
"""

from __future__ import annotations

import logging

from meshlite.app_state import (
    AppReady,
    CommandBus,
    Document,
    EventBus,
    Preferences,
    SelectionModel,
    TaskRunner,
    UndoStack,
)
from meshlite.ops import OperationRegistry
from meshlite.ui.runner import UIRunner
from meshlite.utils.async_task import TaskManager


class MeshLiteApp:
    """Top-level meshlite application."""

    def __init__(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )
        self.logger = logging.getLogger("meshlite.app")

        # 1. Stateless managers.
        self.events = EventBus()
        self.preferences = Preferences()
        self.history = UndoStack(
            max_depth=self.preferences.undo_max_depth,
            max_total_bytes=self.preferences.undo_max_bytes,
        )
        self.task_manager = TaskManager(max_workers=4)
        self.task_runner = TaskRunner(self.task_manager)

        # 2. Document + selection.
        self.document = Document(self.events)
        self.selection = SelectionModel(self.events)

        # 3. CommandBus — single dispatch point.
        self.command_bus = CommandBus(
            document=self.document,
            selection=self.selection,
            history=self.history,
            task_runner=self.task_runner,
            events=self.events,
        )

        # 4. Renderer is constructed in post_init (needs GL context).
        self.renderer = None

        # 5. UI runner — constructed but not started.
        self.ui_runner = UIRunner(app=self)

    # ------------------------------------------------------------------
    # Lifecycle callbacks fired by hello_imgui
    # ------------------------------------------------------------------

    def post_init(self) -> None:
        """Called by hello_imgui once the window + GL context are ready.

        The :class:`UIRunner` constructs the :class:`Renderer` itself in its
        own ``post_init`` (because the renderer is owned by the UI layer).
        Here we run the ops auto-discovery so the registry is fully
        populated before any UI tries to enumerate operations, then emit
        ``AppReady`` so other subscribers know everything is up.
        """
        op_count = OperationRegistry.discover()
        self.logger.info("operation registry: %d op(s) discovered", op_count)
        self.events.emit(AppReady())
        self.logger.info("meshlite ready")

    def before_imgui_render(self) -> None:
        """Called by hello_imgui each frame, before ImGui builds its draw data.

        Drains the main-thread callback queue (so completed worker tasks
        can install their results into the document) and ticks the task
        runner so progress reports flow into the active op state.
        """
        self.task_runner.drain_main_thread_queue()
        self.task_runner.update_tasks()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self.ui_runner.run(
                post_init=self.post_init,
                before_imgui_render=self.before_imgui_render,
            )
        finally:
            self.task_manager.shutdown()


def main() -> None:
    """Entry point exposed via ``[project.scripts]`` in pyproject.toml."""
    MeshLiteApp().run()
