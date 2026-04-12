"""``TopToolbarPanel`` — MeshInspector-style horizontal tools toolbar.

Lives at the top edge of the window via ``hello_imgui.EdgeToolbar`` with
``EdgeToolbarType.top``. Sits between the menu bar (File / View / …) and
the dock space.

Layout: a single horizontal row of icon buttons grouped by category, with
visual separators between groups. Mirrors the way MeshInspector lays out
its main toolbar.

Group structure (left → right):

    [File]   Open  SaveAs  Clear
    [View]   FrameAll  Reset  Wireframe  Axes
    [Inspect]  MeshInfo  Measure
    [Mesh Repair]  FillHoles  AutoRepair
    [Mesh Edit]    Decimate  Smooth  Remesh  Subdivide
    [Boolean]      Union  Intersect  Subtract
    [Transform]    Translate  Rotate  Scale  Mirror

Behaviors:

- **Real registered ops** (currently LoadMesh + SaveMesh) dispatch through
  the CommandBus.
- **Stub buttons** for ops not yet implemented log "{label} — coming in
  M{n}" via ``hello_imgui.log`` so the user can see the plan.
- **Context-awareness**: buttons gray out when their `requires` isn't
  satisfied (e.g. SaveAs disabled when no selection).
- **Dynamic**: as new operations are registered (M8 onwards), this panel
  picks them up via :meth:`OperationRegistry.has` and replaces the matching
  stub with the real button automatically.

In M11 polish this becomes customizable (drag/drop reorder, hide/show via
a three-dot menu like MeshInspector). For M6.5 it's hard-coded.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from imgui_bundle import ImVec2, hello_imgui, imgui

from meshlite.ops import Operation, OperationRegistry

from .. import icons
from ..theme import Colors
from .base_panel import BasePanel

# Width of one toolbar button. Square buttons keep the rhythm consistent.
_BUTTON_SIZE = ImVec2(34, 34)


@dataclass(frozen=True)
class _Tool:
    """One button on the top toolbar."""

    label: str               # short text shown in tooltip + log message
    icon: str                # codicon (or fallback) char
    op_id: str | None = None # if set: dispatch this registered op
    coming_in: str = ""      # e.g. "M8" — used in stub log messages
    requires_selection: bool = False  # gray out if no node selected


@dataclass
class _Group:
    """A visual group of tools separated from neighbors by a vertical bar."""

    name: str
    tools: list[_Tool]


# ---------------------------------------------------------------------------
# Toolbar layout — declarative. Edit here to add/remove buttons.
# ---------------------------------------------------------------------------


def _build_groups() -> list[_Group]:
    return [
        _Group("File", [
            _Tool("Open Mesh",   icons.FILE_OPEN, op_id="io.load_mesh"),
            _Tool("Save As",     icons.SAVE_AS,   op_id="io.save_mesh", requires_selection=True),
            _Tool("Clear All",   icons.CLEAR_ALL, op_id="builtin.clear_all"),
        ]),
        _Group("View", [
            _Tool("Frame All",   icons.SCREEN_FULL, op_id="builtin.frame_all"),
            _Tool("Reset View",  icons.REFRESH,     op_id="builtin.reset_view"),
            _Tool("Wireframe",   icons.PRIMITIVE_SQUARE, op_id="builtin.wireframe"),
            _Tool("Show Axes",   icons.COMPASS,     op_id="builtin.show_axes"),
        ]),
        _Group("Inspect", [
            _Tool("Mesh Info",              icons.GRAPH,        op_id="builtin.mesh_info", requires_selection=True),
            _Tool("Fix Self-Intersections", icons.SYMBOL_EVENT, op_id="inspect.fix_self_intersections", requires_selection=True),
            _Tool("Measure",                icons.SYMBOL_RULER, coming_in="needs point-picking UI", requires_selection=True),
        ]),
        _Group("Mesh Repair", [
            _Tool("Fill Holes",        icons.SHIELD,        op_id="repair.fill_holes",        requires_selection=True),
            _Tool("Auto Repair",       icons.WAND,          op_id="repair.auto_repair",       requires_selection=True),
            _Tool("Remove Duplicates", icons.CIRCUIT_BOARD, op_id="repair.remove_duplicates", requires_selection=True),
        ]),
        _Group("Mesh Edit", [
            _Tool("Decimate",   icons.LAYERS,           op_id="simplify.decimate",  requires_selection=True),
            _Tool("Smooth",     icons.PULSE,            op_id="smooth.laplacian",   requires_selection=True),
            _Tool("Remesh",     icons.LAYERS_ACTIVE,    op_id="simplify.remesh",    requires_selection=True),
            _Tool("Subdivide",  icons.PRIMITIVE_SQUARE, op_id="simplify.subdivide", requires_selection=True),
        ]),
        _Group("Boolean", [
            _Tool("Boolean",    icons.GIT_MERGE,        op_id="boolean.boolean",    requires_selection=True),
        ]),
        _Group("Transform", [
            _Tool("Translate",  icons.COMPASS,      op_id="transform.translate", requires_selection=True),
            _Tool("Rotate",     icons.REFRESH,      op_id="transform.rotate",    requires_selection=True),
            _Tool("Scale",      icons.EXPAND_ALL,   op_id="transform.scale",     requires_selection=True),
            _Tool("Mirror",     icons.MIRROR,       op_id="transform.mirror",    requires_selection=True),
            _Tool("Align",      icons.TELESCOPE,    coming_in="needs ICP multi-mesh UI", requires_selection=True),
        ]),
    ]


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class TopToolbarPanel(BasePanel):
    """The MeshInspector-style top tools toolbar."""

    title = "TopToolbar"

    def __init__(self, app, runner) -> None:
        super().__init__(app, runner)
        self._groups = _build_groups()
        # Built-in handlers indexed by op_id for the synthetic builtin.* ops.
        self._builtins: dict[str, Callable[[], None]] = {
            "builtin.clear_all": self._clear_all,
            "builtin.frame_all": self._frame_all,
            "builtin.reset_view": self._reset_view,
            "builtin.wireframe": self._toggle_wireframe,
            "builtin.show_axes": self._toggle_axes,
            "builtin.mesh_info": self._show_mesh_info,
        }

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self) -> None:
        for i, group in enumerate(self._groups):
            if i > 0:
                self._draw_separator()
            self._draw_group(group)

    def _draw_separator(self) -> None:
        # Vertical bar between groups.
        imgui.same_line()
        imgui.text_disabled("|")
        imgui.same_line()

    def _draw_group(self, group: _Group) -> None:
        for j, tool in enumerate(group.tools):
            if j > 0:
                imgui.same_line()
            self._draw_tool(tool)

    def _draw_tool(self, tool: _Tool) -> None:
        app = self._app

        # Three states for a tool button:
        #   1. real registered op       → dispatch via CommandBus
        #   2. builtin (e.g. wireframe) → call the local handler
        #   3. stub                     → log "coming in {milestone}"
        is_real_op = (
            tool.op_id is not None
            and not tool.op_id.startswith("builtin.")
            and OperationRegistry.has(tool.op_id)
        )
        is_builtin = tool.op_id in self._builtins
        is_stub = not is_real_op and not is_builtin

        # Disabled if requires_selection and nothing selected.
        disabled = tool.requires_selection and app.selection.primary is None

        # Stubs render dimmer to make their status obvious.
        if is_stub:
            imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(0.55, 0.55, 0.55, 1.0))
        if disabled:
            imgui.begin_disabled()

        glyph = icons.safe(tool.icon)
        clicked = imgui.button(f"{glyph}##tool_{tool.label}", _BUTTON_SIZE)

        if disabled:
            imgui.end_disabled()
        if is_stub:
            imgui.pop_style_color()

        # Tooltip — always shown, even when disabled, so users can read it.
        if imgui.is_item_hovered():
            self._draw_tooltip(tool, is_real_op, is_builtin, is_stub, disabled)

        if clicked and not disabled:
            self._handle_click(tool, is_real_op, is_builtin, is_stub)

    def _draw_tooltip(
        self,
        tool: _Tool,
        is_real: bool,
        is_builtin: bool,
        is_stub: bool,
        disabled: bool,
    ) -> None:
        imgui.begin_tooltip()
        imgui.text(tool.label)
        if disabled:
            imgui.text_disabled("(no selection)")
        elif is_stub:
            imgui.text_colored(
                Colors.warning,
                f"coming in {tool.coming_in}",
            )
        elif is_real and tool.op_id is not None:
            cls = OperationRegistry.get(tool.op_id)
            if cls.description:
                imgui.text_disabled(cls.description)
        imgui.end_tooltip()

    def _handle_click(
        self,
        tool: _Tool,
        is_real: bool,
        is_builtin: bool,
        is_stub: bool,
    ) -> None:
        if is_real and tool.op_id is not None:
            self._dispatch_op(tool)
            return

        if is_builtin and tool.op_id is not None:
            handler = self._builtins.get(tool.op_id)
            if handler:
                handler()
            return

        # Stub — just log so the user can see the future plan.
        coming = tool.coming_in or "later"
        hello_imgui.log(
            hello_imgui.LogLevel.info,
            f"{tool.label}: coming in {coming}",
        )

    # ------------------------------------------------------------------
    # Real op dispatch
    # ------------------------------------------------------------------

    def _dispatch_op(self, tool: _Tool) -> None:
        """Dispatch a real registered op via the runner's existing helpers.

        For ops that need a file dialog (Open/Save) we delegate to the
        runner's `cmd_open_mesh` / `cmd_save_mesh` so the dialog logic
        stays in one place. For ops that have a non-empty ParamSchema, we
        set ``runner.pending_op`` so the Properties panel renders the
        parameter form with a Run button (same flow as clicking the op in
        the sidebar Operations browser). For ops with no parameters and
        no dialog, we dispatch immediately.
        """
        runner = self._runner
        if tool.op_id == "io.load_mesh":
            runner.cmd_open_mesh()
            return
        if tool.op_id == "io.save_mesh":
            runner.cmd_save_mesh()
            return

        cls = OperationRegistry.get(tool.op_id)
        schema = getattr(cls, "schema", None)

        # If the op has parameters, route through the Properties panel form.
        if schema and len(schema) > 0:
            runner.pending_op = (cls, schema.defaults())
            return

        # No parameters — dispatch immediately.
        op: Operation = cls()
        if op.requires == "none":
            self._app.command_bus.run_operation(op)
        else:
            target = self._app.selection.primary
            self._app.command_bus.run_operation(op, target_node_id=target)

    # ------------------------------------------------------------------
    # Builtin handlers (view + clear)
    # ------------------------------------------------------------------

    def _clear_all(self) -> None:
        self._app.document.clear()
        self._app.selection.clear()
        hello_imgui.log(hello_imgui.LogLevel.info, "cleared all meshes")

    def _frame_all(self) -> None:
        self._runner.fit_camera_to_document()

    def _reset_view(self) -> None:
        if self._runner.camera is not None:
            self._runner.camera.set_zoom(5.0)

    def _toggle_wireframe(self) -> None:
        self._runner.view.wireframe = not self._runner.view.wireframe

    def _toggle_axes(self) -> None:
        self._runner.view.show_axes = not self._runner.view.show_axes

    def _show_mesh_info(self) -> None:
        """Refresh info cache for the selected node.

        The Mesh Info bottom tab and the Properties panel both read
        ``node.info_cache``. Setting it to ``None`` forces a recompute on
        the next frame those panels render.

        NOTE: We deliberately do NOT call ``imgui.set_window_focus("Mesh
        Info")`` here — calling it from within an edge toolbar callback
        causes a segfault in some imgui_bundle versions (the dockable
        window's internal ID may not be valid during the edge toolbar
        render pass). The user can click the Mesh Info tab themselves.
        """
        node_id = self._app.selection.primary
        if node_id is None:
            return
        node = self._app.document.get_node(node_id)
        if node is None:
            return
        node.info_cache = None
        hello_imgui.log(
            hello_imgui.LogLevel.info,
            f"Mesh Info refreshed for {node.name}",
        )
