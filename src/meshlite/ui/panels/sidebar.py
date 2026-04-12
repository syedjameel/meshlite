"""``SidebarPanel`` — container that swaps body content based on activity bar mode.

The activity bar (a separate, non-dockable widget) controls
``runner.active_sidebar_mode``. The sidebar panel reads that mode each frame
and dispatches to the right sub-panel's ``render`` method. This mirrors how
VSCode's sidebar works internally — one container, swappable views.

Sub-panels live in ``sidebar_outliner.py``, ``sidebar_search.py``,
``sidebar_operations.py``, ``sidebar_settings.py``. The container constructs
each one in ``setup`` and keeps them around — they're cheap and stateful
(e.g. the search box keeps its query).
"""

from __future__ import annotations

from enum import Enum

from imgui_bundle import imgui

from .base_panel import BasePanel
from .sidebar_operations import SidebarOperationsPanel
from .sidebar_outliner import SidebarOutlinerPanel
from .sidebar_search import SidebarSearchPanel
from .sidebar_settings import SidebarSettingsPanel


class SidebarMode(Enum):
    OUTLINER = "outliner"
    SEARCH = "search"
    OPERATIONS = "operations"
    SETTINGS = "settings"


class SidebarPanel(BasePanel):
    title = "Sidebar"

    def __init__(self, app, runner) -> None:
        super().__init__(app, runner)
        self._sub_panels = {
            SidebarMode.OUTLINER: SidebarOutlinerPanel(app, runner),
            SidebarMode.SEARCH: SidebarSearchPanel(app, runner),
            SidebarMode.OPERATIONS: SidebarOperationsPanel(app, runner),
            SidebarMode.SETTINGS: SidebarSettingsPanel(app, runner),
        }

    def setup(self) -> None:
        for sub in self._sub_panels.values():
            sub.setup()

    def cleanup(self) -> None:
        for sub in self._sub_panels.values():
            sub.cleanup()

    def render(self) -> None:
        mode = self._runner.active_sidebar_mode
        sub = self._sub_panels.get(mode)
        if sub is None:
            imgui.text(f"Unknown sidebar mode: {mode}")
            return

        # Section header — bold-ish title bar inside the panel.
        imgui.text(sub.title.upper())
        imgui.separator()
        imgui.spacing()

        sub.safe_render()
