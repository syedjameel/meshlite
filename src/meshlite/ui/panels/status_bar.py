"""``StatusBar`` — content for ``runner_params.callbacks.show_status``.

Not a ``DockableWindow``. ``hello_imgui`` reserves a status bar slot at
the bottom of the window when ``imgui_window_params.show_status_bar`` is
True; the ``show_status`` callback fills the contents.

Layout (left → right):
- mesh count + selected node name + active op label/spinner
- right-justified: FPS, frame time, GL vendor (M11)
"""

from __future__ import annotations

from imgui_bundle import imgui

from .. import icons
from .base_panel import BasePanel


class StatusBar(BasePanel):
    title = "StatusBar"

    def render(self) -> None:
        # Required by BasePanel; status bar uses render_status instead.
        raise NotImplementedError("StatusBar uses render_status, not render")

    def render_status(self) -> None:
        runner = self._runner
        app = self._app

        # Mesh count
        n = len(app.document)
        imgui.text(f"{icons.safe(icons.LIST_TREE)} {n}")
        imgui.same_line()
        imgui.text(" | ")
        imgui.same_line()

        # Selected node name
        primary = app.selection.primary
        if primary is not None:
            node = app.document.get_node(primary)
            if node is not None:
                name = node.name
                if len(name) > 30:
                    name = name[:27] + "..."
                imgui.text(f"{icons.safe(icons.FILE)} {name}")
            else:
                imgui.text_disabled("no selection")
        else:
            imgui.text_disabled("no selection")
        imgui.same_line()
        imgui.text(" | ")
        imgui.same_line()

        # Active op label
        if runner.active_task_id is not None:
            task = app.task_manager.get_task(runner.active_task_id)
            if task is not None:
                pct = int(task.progress * 100)
                msg = task.progress_message or "running"
                imgui.text(f"{icons.safe(icons.PLAY)} {msg} ({pct}%)")
        else:
            imgui.text_disabled("idle")

        # Right-justified: FPS + frame time.
        win_w = imgui.get_window_width()
        fps = imgui.get_io().framerate
        fps_text = f"{fps:5.1f} FPS  {1000.0/max(fps,0.1):5.1f} ms"
        text_w = imgui.calc_text_size(fps_text).x
        imgui.same_line(win_w - text_w - 12)
        imgui.text_disabled(fps_text)
