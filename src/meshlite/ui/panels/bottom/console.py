"""``ConsolePanel`` — wraps ``hello_imgui.log_gui``.

The runner's event subscribers (and most of the rest of the codebase)
already write to ``hello_imgui.log()``. This panel just renders that log
buffer in a dockable window so the user can see it without dropping into
a terminal.
"""

from __future__ import annotations

from imgui_bundle import hello_imgui

from ..base_panel import BasePanel


class ConsolePanel(BasePanel):
    title = "Console"

    def render(self) -> None:
        hello_imgui.log_gui()
