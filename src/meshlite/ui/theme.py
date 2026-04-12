"""VSCode "Dark+" theme for ImGui.

Applied via ``runner_params.callbacks.setup_imgui_style``. The palette is
modeled on the colors VSCode itself uses, with one minor concession to
ImGui's flat-color limitations: where VSCode uses subtle gradients we use
solid colors with a small alpha bump for hover states.

Color reference (from VSCode source / DefaultColors.ts):

    background           #1E1E1E
    panel / sidebar bg   #252526
    title bar bg         #3C3C3C  (active editor)
    tab inactive         #2D2D2D
    tab active           #1E1E1E
    accent (focus blue)  #007ACC
    selection bg         #264F78  (with 60% alpha when not focused)
    text                 #CCCCCC
    text muted           #9D9D9D
    border / separator   #3C3C3C
    error red            #F48771
    warning yellow       #CCA700

The theme also tightens padding/rounding to match VSCode's denser look —
ImGui's defaults are quite spacious by comparison.
"""

from __future__ import annotations

from imgui_bundle import imgui


def _rgba(hex_str: str, alpha: float = 1.0) -> imgui.ImVec4:
    """Convert ``"#RRGGBB"`` (or ``"RRGGBB"``) into an ``ImVec4``."""
    s = hex_str.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_str!r}")
    r = int(s[0:2], 16) / 255.0
    g = int(s[2:4], 16) / 255.0
    b = int(s[4:6], 16) / 255.0
    return imgui.ImVec4(r, g, b, alpha)


# ---------------------------------------------------------------------------
# Palette constants — exposed so other UI code (activity bar highlight,
# selection styling, etc.) can read the same colors.
# ---------------------------------------------------------------------------

class Colors:
    background = _rgba("#1E1E1E")
    panel_bg = _rgba("#252526")
    panel_bg_2 = _rgba("#2D2D2D")
    title_bg = _rgba("#3C3C3C")
    accent = _rgba("#007ACC")
    accent_dim = _rgba("#0E639C")
    selection = _rgba("#264F78")
    selection_dim = _rgba("#264F78", 0.5)
    text = _rgba("#CCCCCC")
    text_muted = _rgba("#9D9D9D")
    text_disabled = _rgba("#6F6F6F")
    border = _rgba("#3C3C3C")
    separator = _rgba("#3C3C3C")
    error = _rgba("#F48771")
    warning = _rgba("#CCA700")
    hover_overlay = imgui.ImVec4(1.0, 1.0, 1.0, 0.06)
    active_overlay = imgui.ImVec4(1.0, 1.0, 1.0, 0.12)


# ---------------------------------------------------------------------------
# Style application
# ---------------------------------------------------------------------------

def apply_vscode_dark() -> None:
    """Apply the VSCode "Dark+" palette to the current ImGui style.

    Call this from ``runner_params.callbacks.setup_imgui_style`` so it runs
    once after fonts have loaded but before the first frame.
    """
    style = imgui.get_style()
    c = Colors

    # ----- Spacing & rounding (denser than ImGui defaults) -----
    style.window_padding = imgui.ImVec2(8, 8)
    style.frame_padding = imgui.ImVec2(6, 4)
    style.item_spacing = imgui.ImVec2(6, 4)
    style.item_inner_spacing = imgui.ImVec2(4, 4)
    style.indent_spacing = 16
    style.scrollbar_size = 12
    style.grab_min_size = 10

    style.window_rounding = 0.0     # VSCode uses square panels
    style.child_rounding = 0.0
    style.frame_rounding = 2.0
    style.popup_rounding = 2.0
    style.scrollbar_rounding = 2.0
    style.grab_rounding = 2.0
    style.tab_rounding = 0.0

    style.window_border_size = 1.0
    style.child_border_size = 0.0
    style.frame_border_size = 0.0
    style.popup_border_size = 1.0
    style.tab_border_size = 0.0

    # ----- Colors -----
    set_color = style.set_color_

    # Text
    set_color(imgui.Col_.text, c.text)
    set_color(imgui.Col_.text_disabled, c.text_disabled)
    set_color(imgui.Col_.text_selected_bg, c.selection)

    # Backgrounds
    set_color(imgui.Col_.window_bg, c.background)
    set_color(imgui.Col_.child_bg, c.panel_bg)
    set_color(imgui.Col_.popup_bg, c.panel_bg_2)
    set_color(imgui.Col_.menu_bar_bg, c.panel_bg)

    # Borders / separators
    set_color(imgui.Col_.border, c.border)
    set_color(imgui.Col_.border_shadow, imgui.ImVec4(0, 0, 0, 0))
    set_color(imgui.Col_.separator, c.separator)
    set_color(imgui.Col_.separator_hovered, c.accent_dim)
    set_color(imgui.Col_.separator_active, c.accent)

    # Title bars / docking
    set_color(imgui.Col_.title_bg, c.panel_bg_2)
    set_color(imgui.Col_.title_bg_active, c.panel_bg)
    set_color(imgui.Col_.title_bg_collapsed, c.panel_bg_2)
    set_color(imgui.Col_.docking_preview, c.accent)
    set_color(imgui.Col_.docking_empty_bg, c.background)

    # Frame controls (input boxes, sliders, combos)
    set_color(imgui.Col_.frame_bg, c.panel_bg_2)
    set_color(imgui.Col_.frame_bg_hovered, c.title_bg)
    set_color(imgui.Col_.frame_bg_active, c.accent_dim)

    # Buttons
    set_color(imgui.Col_.button, c.panel_bg_2)
    set_color(imgui.Col_.button_hovered, c.title_bg)
    set_color(imgui.Col_.button_active, c.accent_dim)

    # Headers (selectables, collapsing headers, tree nodes)
    set_color(imgui.Col_.header, c.panel_bg_2)
    set_color(imgui.Col_.header_hovered, c.title_bg)
    set_color(imgui.Col_.header_active, c.selection)

    # Scrollbars
    set_color(imgui.Col_.scrollbar_bg, c.background)
    set_color(imgui.Col_.scrollbar_grab, c.title_bg)
    set_color(imgui.Col_.scrollbar_grab_hovered, c.text_muted)
    set_color(imgui.Col_.scrollbar_grab_active, c.text)

    # Sliders / check marks
    set_color(imgui.Col_.check_mark, c.accent)
    set_color(imgui.Col_.slider_grab, c.accent)
    set_color(imgui.Col_.slider_grab_active, c.text)

    # Resize grips
    set_color(imgui.Col_.resize_grip, imgui.ImVec4(0, 0, 0, 0))
    set_color(imgui.Col_.resize_grip_hovered, c.accent_dim)
    set_color(imgui.Col_.resize_grip_active, c.accent)

    # Tabs (dockable panels)
    set_color(imgui.Col_.tab, c.panel_bg_2)
    set_color(imgui.Col_.tab_hovered, c.background)
    set_color(imgui.Col_.tab_selected, c.background)
    set_color(imgui.Col_.tab_selected_overline, c.accent)
    set_color(imgui.Col_.tab_dimmed, c.panel_bg_2)
    set_color(imgui.Col_.tab_dimmed_selected, c.background)

    # Plot
    set_color(imgui.Col_.plot_lines, c.accent)
    set_color(imgui.Col_.plot_lines_hovered, c.text)
    set_color(imgui.Col_.plot_histogram, c.accent)
    set_color(imgui.Col_.plot_histogram_hovered, c.text)

    # Modal dim
    set_color(imgui.Col_.modal_window_dim_bg, imgui.ImVec4(0, 0, 0, 0.55))
    set_color(imgui.Col_.nav_windowing_dim_bg, imgui.ImVec4(0, 0, 0, 0.55))
    set_color(imgui.Col_.nav_cursor, c.accent)
