"""Command palette — VSCode-style Ctrl+Shift+P fuzzy-search popup.

A modal popup that lists every registered operation + built-in commands.
The user types a query; entries are fuzzy-matched and ranked. Pressing
Enter dispatches the highlighted entry. Pressing Escape closes the palette.

The palette is rendered each frame by the runner when ``is_open`` is True.
It does not own any state beyond the current search text and selection
index — all entries are rebuilt each frame from the live registry.

Built-in commands (non-op actions like "Toggle Wireframe", "Undo", etc.)
are defined in ``_BUILTINS`` and show up alongside registered ops.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from imgui_bundle import ImVec2, imgui

from meshlite.ops import OperationRegistry
from meshlite.utils.fuzzy import filter_and_rank

if TYPE_CHECKING:
    from meshlite.ui.runner import UIRunner


@dataclass
class _Entry:
    """One row in the command palette list."""

    display: str             # e.g. "Repair: Fill Holes"
    op_id: str | None        # if registered op
    builtin_id: str | None   # if built-in command
    description: str = ""


class CommandPalette:
    """The Ctrl+Shift+P command palette widget."""

    def __init__(self, runner: UIRunner) -> None:
        self._runner = runner
        self.is_open = False
        self._query = ""
        self._selected_idx = 0
        self._just_opened = False

        # Built-in commands that don't correspond to registered ops.
        self._builtins: dict[str, Callable[[], None]] = {}

    def setup_builtins(self) -> None:
        """Register built-in commands. Call once after runner is fully wired."""
        r = self._runner
        app = r._app
        self._builtins = {
            "builtin.open":       r.cmd_open_mesh,
            "builtin.save":       r.cmd_save_mesh,
            "builtin.clear":      lambda: (app.document.clear(), app.selection.clear()),
            "builtin.frame_all":  r.fit_camera_to_document,
            "builtin.reset_view": lambda: r.camera and r.camera.set_zoom(5.0),
            "builtin.wireframe":  lambda: setattr(r.view, "wireframe", not r.view.wireframe),
            "builtin.axes":       lambda: setattr(r.view, "show_axes", not r.view.show_axes),
            "builtin.undo":       lambda: app.command_bus.undo(),
            "builtin.redo":       lambda: app.command_bus.redo(),
        }

    def toggle(self) -> None:
        self.is_open = not self.is_open
        if self.is_open:
            self._query = ""
            self._selected_idx = 0
            self._just_opened = True

    def close(self) -> None:
        self.is_open = False

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self) -> None:
        if not self.is_open:
            return

        # Center the popup at top of screen, ~600px wide.
        vp = imgui.get_main_viewport()
        w = min(600, vp.work_size.x - 40)
        x = vp.work_pos.x + (vp.work_size.x - w) / 2
        y = vp.work_pos.y + 50
        imgui.set_next_window_pos(ImVec2(x, y), imgui.Cond_.always.value)
        imgui.set_next_window_size(ImVec2(w, 0))

        flags = (
            imgui.WindowFlags_.no_title_bar.value
            | imgui.WindowFlags_.no_resize.value
            | imgui.WindowFlags_.no_move.value
            | imgui.WindowFlags_.no_scrollbar.value
            | imgui.WindowFlags_.no_saved_settings.value
        )

        if imgui.begin("##CommandPalette", None, flags):
            self._render_content()
        imgui.end()

        # Close on Escape or click outside.
        if imgui.is_key_pressed(imgui.Key.escape):
            self.close()

    def _render_content(self) -> None:
        # Search input — auto-focus on open.
        if self._just_opened:
            imgui.set_keyboard_focus_here()
            self._just_opened = False

        changed, self._query = imgui.input_text(
            "##palette_search",
            self._query,
            imgui.InputTextFlags_.auto_select_all.value,
        )
        if changed:
            self._selected_idx = 0

        imgui.separator()

        # Build + filter entries.
        entries = self._build_entries()
        if self._query.strip():
            display_list = [e.display for e in entries]
            ranked = filter_and_rank(self._query, display_list)
            filtered = []
            display_to_entry = {e.display: e for e in entries}
            for _score, display, _indices in ranked:
                if display in display_to_entry:
                    filtered.append(display_to_entry[display])
        else:
            filtered = entries

        # Clamp selection.
        if filtered:
            self._selected_idx = max(0, min(self._selected_idx, len(filtered) - 1))
        else:
            self._selected_idx = 0

        # Arrow key navigation.
        if imgui.is_key_pressed(imgui.Key.down_arrow):
            self._selected_idx = min(self._selected_idx + 1, len(filtered) - 1)
        if imgui.is_key_pressed(imgui.Key.up_arrow):
            self._selected_idx = max(self._selected_idx - 1, 0)

        # Enter dispatches.
        enter_pressed = imgui.is_key_pressed(imgui.Key.enter) or imgui.is_key_pressed(imgui.Key.keypad_enter)

        # Render the list (capped at ~15 visible).
        max_visible = 15
        imgui.begin_child("##palette_list", ImVec2(0, min(len(filtered), max_visible) * 26 + 8))
        for i, entry in enumerate(filtered):
            is_sel = i == self._selected_idx
            if imgui.selectable(f"{entry.display}##pal_{i}", is_sel)[0] or (enter_pressed and is_sel):
                self._dispatch(entry)
                break
            if entry.description and imgui.is_item_hovered():
                imgui.set_tooltip(entry.description)
        imgui.end_child()

        if not filtered:
            imgui.text_disabled("No matches")

    # ------------------------------------------------------------------
    # Entry building
    # ------------------------------------------------------------------

    def _build_entries(self) -> list[_Entry]:
        entries: list[_Entry] = []

        # Registered operations.
        for op_cls in OperationRegistry.all():
            cat = getattr(op_cls, "category", "General")
            label = getattr(op_cls, "label", op_cls.__name__)
            desc = getattr(op_cls, "description", "")
            entries.append(_Entry(
                display=f"{cat}: {label}",
                op_id=op_cls.id,
                builtin_id=None,
                description=desc,
            ))

        # Built-in commands.
        builtin_defs = [
            ("builtin.open",       "File: Open Mesh          Ctrl+O",       "Open a mesh file from disk"),
            ("builtin.save",       "File: Save Mesh As       Ctrl+S",       "Save the selected mesh to disk"),
            ("builtin.clear",      "File: Clear All Meshes",                "Remove all meshes from the document"),
            ("builtin.frame_all",  "View: Frame All          F",            "Fit all meshes in the viewport"),
            ("builtin.reset_view", "View: Reset Camera",                    "Reset the camera to default zoom"),
            ("builtin.wireframe",  "View: Toggle Wireframe",                "Toggle wireframe rendering"),
            ("builtin.axes",       "View: Toggle Axes",                     "Toggle axis arrows visibility"),
            ("builtin.undo",       "Edit: Undo              Ctrl+Z",        "Undo the last operation"),
            ("builtin.redo",       "Edit: Redo              Ctrl+Shift+Z",  "Redo the last undone operation"),
        ]
        for bid, display, desc in builtin_defs:
            entries.append(_Entry(
                display=display,
                op_id=None,
                builtin_id=bid,
                description=desc,
            ))

        # Recent files.
        from pathlib import Path
        for path_str in self._runner._app.preferences.recent_files:
            p = Path(path_str)
            entries.append(_Entry(
                display=f"Open Recent: {p.name}",
                op_id=None,
                builtin_id=f"recent:{path_str}",
                description=str(p),
            ))

        return entries

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, entry: _Entry) -> None:
        runner = self._runner

        if entry.builtin_id is not None:
            # Recent file entries.
            if entry.builtin_id.startswith("recent:"):
                path = entry.builtin_id[len("recent:"):]
                from meshlite.ops.io.load_mesh import LoadMeshOperation
                runner._app.command_bus.run_operation(
                    LoadMeshOperation(), params={"path": path}
                )
                self.close()
                return

            handler = self._builtins.get(entry.builtin_id)
            if handler:
                handler()
            self.close()
            return

        if entry.op_id is not None and OperationRegistry.has(entry.op_id):
            cls = OperationRegistry.get(entry.op_id)
            schema = getattr(cls, "schema", None)

            # Ops with params → pending-op in Properties panel.
            if schema and len(schema) > 0:
                runner.pending_op = (cls, schema.defaults())
                self.close()
                return

            # Ops without params → dispatch immediately.
            op = cls()
            requires = getattr(op, "requires", "one_mesh")
            if requires == "none":
                runner._app.command_bus.run_operation(op)
            else:
                target = runner._app.selection.primary
                if target:
                    runner._app.command_bus.run_operation(op, target_node_id=target)
            self.close()
            return

        self.close()
