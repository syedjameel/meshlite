"""``ActivityBar`` — VSCode-style left icon strip.

Implemented as a ``hello_imgui.EdgeToolbar`` registered against
``EdgeToolbarType.left``. Edge toolbars are non-dockable, sized in font
em units, and rendered by hello_imgui in a slot outside the dock space.
This is much cleaner than the "manual fixed-position imgui.Window"
fallback the original plan called for.

The activity bar drives the sidebar's content via
``runner.active_sidebar_mode``. Clicking a button updates the mode; the
sidebar panel reads it next frame and dispatches to the right sub-panel.
"""

from __future__ import annotations

from imgui_bundle import ImVec2, hello_imgui, imgui

from .. import icons
from ..theme import Colors
from .base_panel import BasePanel
from .sidebar import SidebarMode

# Width of the edge toolbar in font em units (~16px per em with default font).
# 3 em → ~48 px which matches VSCode's activity bar width.
ACTIVITY_BAR_SIZE_EM = 3.0

_BUTTON_SIZE = ImVec2(36, 36)


class ActivityBar(BasePanel):
    """The narrow icon-only navigation strip on the left edge."""

    title = "ActivityBar"

    # Order matters — this is the visual order of buttons in the strip.
    _MODES: list[tuple[SidebarMode, str, str]] = [
        (SidebarMode.OUTLINER,   icons.LIST_TREE,    "Outliner"),
        (SidebarMode.SEARCH,     icons.SEARCH,       "Search"),
        (SidebarMode.OPERATIONS, icons.TOOLS,        "Operations"),
        (SidebarMode.SETTINGS,   icons.SETTINGS_GEAR,"Settings"),
    ]

    def render(self) -> None:
        """Render the activity bar buttons.

        Used as the ``gui_function`` of an :class:`hello_imgui.EdgeToolbar`
        registered via ``runner_params.callbacks.add_edge_toolbar``.
        """
        runner = self._runner
        active = runner.active_sidebar_mode

        for mode, glyph, tooltip in self._MODES:
            is_active = mode == active
            label = icons.safe(glyph)

            if is_active:
                imgui.push_style_color(imgui.Col_.button, Colors.accent)
                imgui.push_style_color(imgui.Col_.button_hovered, Colors.accent)
                imgui.push_style_color(imgui.Col_.button_active, Colors.accent_dim)

            if imgui.button(f"{label}##act_{mode.value}", _BUTTON_SIZE):
                runner.active_sidebar_mode = mode

            if is_active:
                imgui.pop_style_color(3)

            if imgui.is_item_hovered():
                imgui.set_tooltip(tooltip)

    def make_options(self) -> hello_imgui.EdgeToolbarOptions:
        """Build the EdgeToolbarOptions used by the runner when registering."""
        opts = hello_imgui.EdgeToolbarOptions()
        opts.size_em = ACTIVITY_BAR_SIZE_EM
        opts.window_bg = Colors.panel_bg_2
        opts.window_padding_em = ImVec2(0.4, 0.6)
        return opts
