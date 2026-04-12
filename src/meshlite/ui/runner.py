"""hello_imgui runner — owns shared GL state and the dock layout.

After M6's refactor this file does three things:

1. **Owns shared lifecycle state** that can't live on individual panels:
   the moderngl :class:`Renderer` and :class:`ArcballCamera` (constructed
   in post_init when the GL context exists), the GPU upload event
   subscribers (so any panel that adds a node automatically gets a
   ``GpuMesh``), and the op-lifecycle event subscribers.

2. **Hosts the dock layout** via ``hello_imgui.RunnerParams.docking_params``.
   The full-screen dockspace is split into Sidebar | Main | Properties
   horizontally and Main | Bottom vertically. Each :class:`DockableWindow`
   is bound to a panel instance's ``safe_render`` method.

3. **Draws the activity bar overlay** each frame from
   ``before_imgui_render``, on top of the dock space's left margin. The
   activity bar is NOT a dockable window; it's a manually-positioned
   ``imgui.Window`` with NoDocking flags.

Pre-M6 this file was 489 lines doing all of the above PLUS the viewport
rendering, the file menu, the proto-outliner, and the debug counter
button. M6 extracted the rendering bits into ``panels/viewport.py`` and
moved the proto-outliner into ``panels/sidebar_outliner.py``. Runner now
sits at ~330 LOC.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from imgui_bundle import ImVec2, hello_imgui, imgui

from meshlite.app_state.events import (
    NodeAdded,
    NodeMeshReplaced,
    NodeRemoved,
    OpCanceled,
    OpCompleted,
    OpFailed,
    OpStarted,
)
from meshlite.app_state.preferences import Preferences
from meshlite.app_state.node import DocumentNode
from meshlite.ops.io.load_mesh import LoadMeshOperation
from meshlite.ops.io.save_mesh import SaveMeshOperation
from meshlite.render import (
    ArcballCamera,
    GpuMesh,
    Renderer,
    ViewOptions,
    mesh_data_to_arrays,
)
from meshlite.utils.file_dialog import open_mesh_dialog, save_mesh_dialog

from . import fonts, theme
from .panels.activity_bar import ActivityBar
from .panels.bottom.console import ConsolePanel
from .panels.bottom.mesh_info import MeshInfoPanel
from .panels.properties import PropertiesPanel
from .panels.sidebar import SidebarMode, SidebarPanel
from .panels.status_bar import StatusBar
from .panels.top_toolbar import TopToolbarPanel
from .panels.viewport import ViewportPanel
from .widgets.command_palette import CommandPalette

if TYPE_CHECKING:
    from meshlite.app import MeshLiteApp


_LOGGER = logging.getLogger("meshlite.ui")


# ---------------------------------------------------------------------------
# Dock space names — referenced by both DockingSplit and DockableWindow defs.
# ---------------------------------------------------------------------------

_MAIN = "MainDockSpace"
_SIDEBAR = "SidebarSpace"
_PROPERTIES = "PropertiesSpace"
_BOTTOM = "BottomSpace"


class UIRunner:
    """Wraps ``hello_imgui.run`` for the meshlite application."""

    def __init__(self, app: MeshLiteApp) -> None:
        self._app = app

        # Shared GL state — constructed in post_init.
        self.renderer: Renderer | None = None
        self.camera: ArcballCamera | None = None
        self.view = ViewOptions()
        self.viewport_size: tuple[int, int] = (800, 600)
        self._post_init_done = False

        # Op-lifecycle state for status bar / progress display.
        self.last_progress: float = 0.0
        self.last_progress_msg: str = ""
        self.active_task_id: str | None = None

        # Sidebar mode (driven by ActivityBar clicks).
        self.active_sidebar_mode: SidebarMode = SidebarMode.OUTLINER

        # Pending operation — set by the sidebar Operations browser, the
        # top toolbar, or the command palette. When not None, the Properties
        # panel switches to pending-op mode and renders the ParamSchema form.
        self.pending_op: tuple[type, dict] | None = None

        # Command palette (M9).
        self.command_palette = CommandPalette(self)

        # Panel instances. Constructed here so the runner can keep stable
        # references; their content is rendered by hello_imgui via the
        # DockableWindow gui_function callbacks.
        self.viewport_panel = ViewportPanel(app, self)
        self.sidebar_panel = SidebarPanel(app, self)
        self.properties_panel = PropertiesPanel(app, self)
        self.console_panel = ConsolePanel(app, self)
        self.mesh_info_panel = MeshInfoPanel(app, self)
        self.status_bar = StatusBar(app, self)
        self.activity_bar = ActivityBar(app, self)
        self.top_toolbar = TopToolbarPanel(app, self)
        self._panels = [
            self.viewport_panel,
            self.sidebar_panel,
            self.properties_panel,
            self.console_panel,
            self.mesh_info_panel,
            self.status_bar,
            self.top_toolbar,
        ]

        self._wire_event_subscribers()

    # ------------------------------------------------------------------
    # Event subscribers
    # ------------------------------------------------------------------

    def _wire_event_subscribers(self) -> None:
        bus = self._app.events
        bus.subscribe(OpStarted, self._on_op_started)
        bus.subscribe(OpCompleted, self._on_op_completed)
        bus.subscribe(OpFailed, self._on_op_failed)
        bus.subscribe(OpCanceled, self._on_op_canceled)
        bus.subscribe(NodeAdded, self._on_node_added)
        bus.subscribe(NodeRemoved, self._on_node_removed)
        bus.subscribe(NodeMeshReplaced, self._on_node_mesh_replaced)

    # -- op lifecycle --

    def _on_op_started(self, e: OpStarted) -> None:
        self.active_task_id = e.task_id
        self.last_progress = 0.0
        self.last_progress_msg = "started"
        hello_imgui.log(hello_imgui.LogLevel.info, f"op start: {e.label} ({e.op_id})")

    def _on_op_completed(self, e: OpCompleted) -> None:
        self.active_task_id = None
        self.last_progress = 1.0
        self.last_progress_msg = e.message or "done"
        hello_imgui.log(
            hello_imgui.LogLevel.info,
            f"op done: {e.op_id} — {e.message} info={e.info}",
        )
        # Track recent files on successful mesh load.
        if e.op_id == "io.load_mesh" and e.info and "path" in e.info:
            self._app.preferences.add_recent_file(e.info["path"])

    def _on_op_failed(self, e: OpFailed) -> None:
        self.active_task_id = None
        self.last_progress_msg = f"failed: {e.error}"
        hello_imgui.log(hello_imgui.LogLevel.error, f"op failed: {e.op_id} — {e.error}")

    def _on_op_canceled(self, e: OpCanceled) -> None:
        self.active_task_id = None
        self.last_progress_msg = "canceled"
        hello_imgui.log(hello_imgui.LogLevel.warning, f"op canceled: {e.op_id}")

    # -- document → GPU upload --

    def _on_node_added(self, e: NodeAdded) -> None:
        node = self._app.document.get_node(e.node_id)
        if node is None:
            return
        self.upload_node(node)
        if self.camera is not None:
            self.fit_camera_to_document()

    def _on_node_removed(self, _e: NodeRemoved) -> None:
        # Document.remove_node already released the GpuMesh.
        pass

    def _on_node_mesh_replaced(self, e: NodeMeshReplaced) -> None:
        node = self._app.document.get_node(e.node_id)
        if node is None:
            return
        if node.gpu_mesh is not None:
            node.gpu_mesh.release()
            node.gpu_mesh = None
        node.gpu_upload_failed = False
        self.upload_node(node)

    # ------------------------------------------------------------------
    # GPU upload + camera framing — public so panels can call them
    # ------------------------------------------------------------------

    def upload_node(self, node: DocumentNode) -> None:
        if self.renderer is None or not self._post_init_done:
            return
        try:
            arrays = mesh_data_to_arrays(node.mesh)
            node.gpu_mesh = GpuMesh(self.renderer.ctx, self.renderer.prog, arrays)
            _LOGGER.info(
                "uploaded GpuMesh for node %s (%s, %d verts)",
                node.id, node.name, arrays.vertex_count,
            )
        except Exception as e:                              # noqa: BLE001
            node.gpu_upload_failed = True
            _LOGGER.exception("failed to upload node %s: %s", node.id, e)
            hello_imgui.log(
                hello_imgui.LogLevel.error,
                f"GPU upload failed for {node.name}: {e}",
            )

    def fit_camera_to_document(self) -> None:
        if self.camera is None:
            return
        nodes = list(self._app.document.visible_nodes())
        if not nodes:
            return
        # Compute the union bounding box of all visible nodes.
        from pyglm import glm
        bb_min = [float("inf")] * 3
        bb_max = [float("-inf")] * 3
        for n in nodes:
            (xn, yn, zn), (xx, yx, zx) = n.mesh.bounding_box()
            bb_min[0] = min(bb_min[0], xn)
            bb_min[1] = min(bb_min[1], yn)
            bb_min[2] = min(bb_min[2], zn)
            bb_max[0] = max(bb_max[0], xx)
            bb_max[1] = max(bb_max[1], yx)
            bb_max[2] = max(bb_max[2], zx)
        # Center the camera on the bbox center.
        center = glm.vec3(
            (bb_min[0] + bb_max[0]) / 2,
            (bb_min[1] + bb_max[1]) / 2,
            (bb_min[2] + bb_max[2]) / 2,
        )
        max_extent = max(bb_max[i] - bb_min[i] for i in range(3))
        if max_extent > 0:
            self.camera.set_target(center)
            self.camera.set_zoom(max_extent * 3.0)

    # ------------------------------------------------------------------
    # File menu commands — used by both the menu bar and the toolbar
    # ------------------------------------------------------------------

    def cmd_open_mesh(self) -> None:
        path = open_mesh_dialog()
        if path is None:
            hello_imgui.log(hello_imgui.LogLevel.info, "open canceled")
            return
        self._app.command_bus.run_operation(
            LoadMeshOperation(),
            params={"path": str(path)},
        )

    def cmd_save_mesh(self) -> None:
        node_id = self._app.selection.primary
        if node_id is None:
            hello_imgui.log(hello_imgui.LogLevel.warning, "no mesh selected to save")
            return
        node = self._app.document.get_node(node_id)
        if node is None:
            return
        path = save_mesh_dialog(default_name=node.name or "mesh.stl")
        if path is None:
            hello_imgui.log(hello_imgui.LogLevel.info, "save canceled")
            return
        self._app.command_bus.run_operation(
            SaveMeshOperation(),
            target_node_id=node_id,
            params={"path": str(path)},
        )

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _show_menu_bar(self) -> None:
        if imgui.begin_menu("File"):
            if imgui.menu_item("Open Mesh...", "Ctrl+O", False)[0]:
                self.cmd_open_mesh()

            # Open Recent submenu
            recent = self._app.preferences.recent_files
            if imgui.begin_menu("Open Recent", bool(recent)):
                from pathlib import Path
                for path_str in recent:
                    p = Path(path_str)
                    display = p.name if len(path_str) > 50 else path_str
                    exists = p.exists()
                    if not exists:
                        imgui.begin_disabled()
                    if imgui.menu_item(display, "", False)[0]:
                        self._app.command_bus.run_operation(
                            LoadMeshOperation(), params={"path": path_str}
                        )
                    if not exists:
                        imgui.end_disabled()
                    if imgui.is_item_hovered():
                        imgui.set_tooltip(path_str)
                imgui.end_menu()

            save_disabled = self._app.selection.primary is None
            if save_disabled:
                imgui.begin_disabled()
            if imgui.menu_item("Save Mesh As...", "Ctrl+S", False)[0]:
                self.cmd_save_mesh()
            if save_disabled:
                imgui.end_disabled()
            imgui.separator()
            clear_disabled = len(self._app.document) == 0
            if clear_disabled:
                imgui.begin_disabled()
            if imgui.menu_item("Clear All Meshes", "", False)[0]:
                self._app.document.clear()
                self._app.selection.clear()
                hello_imgui.log(hello_imgui.LogLevel.info, "cleared all meshes")
            if clear_disabled:
                imgui.end_disabled()
            imgui.separator()
            if imgui.menu_item("Exit", "", False)[0]:
                hello_imgui.get_runner_params().app_shall_exit = True
            imgui.end_menu()

        if imgui.begin_menu("Edit"):
            can_undo = self._app.history.can_undo()
            can_redo = self._app.history.can_redo()

            undo_label = f"Undo: {self._app.history.peek_undo_label()}" if can_undo else "Undo"
            redo_label = f"Redo: {self._app.history.peek_redo_label()}" if can_redo else "Redo"

            if not can_undo:
                imgui.begin_disabled()
            if imgui.menu_item(undo_label, "Ctrl+Z", False)[0]:
                self._app.command_bus.undo()
            if not can_undo:
                imgui.end_disabled()

            if not can_redo:
                imgui.begin_disabled()
            if imgui.menu_item(redo_label, "Ctrl+Shift+Z", False)[0]:
                self._app.command_bus.redo()
            if not can_redo:
                imgui.end_disabled()

            imgui.end_menu()

        if imgui.begin_menu("View"):
            _, self.view.wireframe = imgui.menu_item(
                "Wireframe", "", self.view.wireframe
            )
            _, self.view.show_axes = imgui.menu_item(
                "Show Axes", "", self.view.show_axes
            )
            if imgui.menu_item("Reset Camera", "", False)[0] and self.camera is not None:
                self.camera.set_zoom(5.0)
            if imgui.menu_item("Frame All", "F", False)[0]:
                self.fit_camera_to_document()
            imgui.end_menu()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _post_init(self) -> None:
        """GL context is live — build the renderer + camera + panel setup."""
        # Load persisted preferences before building renderer/camera so
        # their initial state reflects the user's saved settings.
        self._load_preferences()

        prefs = self._app.preferences
        w, h = self.viewport_size
        self.renderer = Renderer(w, h)
        self.camera = ArcballCamera(w, h, fov_deg=prefs.fov_deg)
        self._post_init_done = True

        # Apply preferences to view options.
        self._apply_preferences()

        # Catch up: upload any nodes added before post_init fired.
        for node in self._app.document.all_nodes():
            self.upload_node(node)

        # Run each panel's setup() now that GL is live.
        for panel in self._panels:
            try:
                panel.setup()
            except Exception as e:                          # noqa: BLE001
                _LOGGER.exception("panel %s setup failed: %s", panel.title, e)

        # Wire the command palette's built-in commands now that everything
        # (runner, app, renderer, camera) is fully initialized.
        self.command_palette.setup_builtins()

        # Drag-and-drop: register GLFW callback now that the window exists.
        self._setup_glfw_drop_callback()

    def _load_preferences(self) -> None:
        """Load user preferences from hello_imgui's persisted storage."""
        try:
            json_str = hello_imgui.load_user_pref("meshlite_prefs")
            if json_str:
                self._app.preferences = Preferences.from_json(json_str)
                _LOGGER.info("loaded user preferences")
        except Exception as e:                              # noqa: BLE001
            _LOGGER.warning("failed to load preferences: %s", e)

    def _apply_preferences(self) -> None:
        """Push current preferences into view options, camera, and history."""
        prefs = self._app.preferences
        self.view.wireframe = prefs.wireframe
        self.view.show_axes = prefs.show_axes
        self.view.background = prefs.background_color
        self.view.ambient_strength = prefs.ambient_strength
        self.view.specular_strength = prefs.specular_strength
        self.view.specular_exponent = prefs.specular_exponent
        if self.camera is not None:
            self.camera.fov_deg = prefs.fov_deg
            self.camera.set_viewport(self.camera.width, self.camera.height)
        self._app.history.max_depth = prefs.undo_max_depth
        self._app.history.max_total_bytes = prefs.undo_max_bytes

    def _save_preferences(self) -> None:
        """Sync runtime state back to preferences and persist."""
        prefs = self._app.preferences
        prefs.wireframe = self.view.wireframe
        prefs.show_axes = self.view.show_axes
        prefs.background_color = self.view.background
        prefs.ambient_strength = self.view.ambient_strength
        prefs.specular_strength = self.view.specular_strength
        prefs.specular_exponent = self.view.specular_exponent
        if self.camera is not None:
            prefs.fov_deg = self.camera.fov_deg
        try:
            hello_imgui.save_user_pref("meshlite_prefs", prefs.to_json())
            _LOGGER.info("saved user preferences")
        except Exception as e:                              # noqa: BLE001
            _LOGGER.warning("failed to save preferences: %s", e)

    def _on_exit(self) -> None:
        self._save_preferences()
        for panel in self._panels:
            with contextlib.suppress(Exception):
                panel.cleanup()
        for node in self._app.document.all_nodes():
            if node.gpu_mesh is not None:
                node.gpu_mesh.release()
                node.gpu_mesh = None
        if self.renderer is not None:
            self.renderer.release()
            self.renderer = None

    # ------------------------------------------------------------------
    # Global keybinds (checked each frame)
    # ------------------------------------------------------------------

    def _check_global_keybinds(self) -> None:
        io = imgui.get_io()
        ctrl = io.key_ctrl
        shift = io.key_shift

        # Ctrl+Shift+P → command palette
        if ctrl and shift and imgui.is_key_pressed(imgui.Key.p):
            self.command_palette.toggle()

        # Ctrl+Z → undo (M10 will add menu items; keybind here for M9)
        if ctrl and not shift and imgui.is_key_pressed(imgui.Key.z):
            self._app.command_bus.undo()

        # Ctrl+Shift+Z → redo
        if ctrl and shift and imgui.is_key_pressed(imgui.Key.z):
            self._app.command_bus.redo()

        # Ctrl+O → open mesh
        if ctrl and not shift and imgui.is_key_pressed(imgui.Key.o):
            self.cmd_open_mesh()

        # Ctrl+S → save mesh as
        if ctrl and not shift and imgui.is_key_pressed(imgui.Key.s):
            self.cmd_save_mesh()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _build_docking_params(self) -> hello_imgui.DockingParams:
        params = hello_imgui.DockingParams()
        # hello_imgui's persisted layout file looks for the layout named
        # "Default" by default; use it so layout state restores cleanly.
        params.layout_name = "Default"

        params.docking_splits = [
            hello_imgui.DockingSplit(_MAIN, _SIDEBAR,    imgui.Dir.left,  0.22),
            hello_imgui.DockingSplit(_MAIN, _PROPERTIES, imgui.Dir.right, 0.25),
            hello_imgui.DockingSplit(_MAIN, _BOTTOM,     imgui.Dir.down,  0.28),
        ]

        single_pane = imgui.DockNodeFlags_.auto_hide_tab_bar.value

        params.dockable_windows = [
            hello_imgui.DockableWindow(
                label_=self.viewport_panel.title,
                dock_space_name_=_MAIN,
                gui_function_=self.viewport_panel.safe_render,
                can_be_closed_=False,
            ),
            hello_imgui.DockableWindow(
                label_=self.sidebar_panel.title,
                dock_space_name_=_SIDEBAR,
                gui_function_=self.sidebar_panel.safe_render,
                can_be_closed_=False,
            ),
            hello_imgui.DockableWindow(
                label_=self.properties_panel.title,
                dock_space_name_=_PROPERTIES,
                gui_function_=self.properties_panel.safe_render,
                can_be_closed_=False,
            ),
            hello_imgui.DockableWindow(
                label_=self.console_panel.title,
                dock_space_name_=_BOTTOM,
                gui_function_=self.console_panel.safe_render,
            ),
            hello_imgui.DockableWindow(
                label_=self.mesh_info_panel.title,
                dock_space_name_=_BOTTOM,
                gui_function_=self.mesh_info_panel.safe_render,
            ),
        ]
        # Single-pane dock spaces (sidebar / properties / viewport) hide
        # their tab bar so they look like regular panels, not tabbed groups.
        for w in params.dockable_windows:
            if w.dock_space_name == _BOTTOM:
                continue            # bottom keeps tabs (Console + Mesh Info)
            w.imgui_window_flags = imgui.WindowFlags_.no_collapse.value
        params.main_dock_space_node_flags = (
            imgui.DockNodeFlags_.passthru_central_node.value | single_pane
        )

        return params

    def run(
        self,
        *,
        post_init: Callable[[], None] | None = None,
        before_imgui_render: Callable[[], None] | None = None,
    ) -> None:
        params = hello_imgui.RunnerParams()
        params.app_window_params.window_title = "MeshLite"
        params.app_window_params.window_geometry.size = (1600, 900)

        params.imgui_window_params.show_menu_bar = True
        params.imgui_window_params.show_status_bar = True
        params.imgui_window_params.default_imgui_window_type = (
            hello_imgui.DefaultImGuiWindowType.provide_full_screen_dock_space
        )

        params.fps_idling.enable_idling = True

        # Dock layout
        params.docking_params = self._build_docking_params()

        # Theme + fonts (callbacks fire before the first frame)
        params.callbacks.load_additional_fonts = fonts.load_fonts
        params.callbacks.setup_imgui_style = theme.apply_vscode_dark

        # Menu bar
        params.callbacks.show_menus = self._show_menu_bar

        # Status bar
        params.callbacks.show_status = self.status_bar.render_status

        # Activity bar — left edge toolbar (non-dockable)
        params.callbacks.add_edge_toolbar(
            hello_imgui.EdgeToolbarType.left,
            self.activity_bar.safe_render,
            self.activity_bar.make_options(),
        )

        # Top tools toolbar — MeshInspector-style horizontal strip with all
        # operations grouped by category. Sits between the menu bar and the
        # dock space (M6.5).
        top_opts = hello_imgui.EdgeToolbarOptions()
        top_opts.size_em = 2.6
        from .theme import Colors as _C
        top_opts.window_bg = _C.panel_bg_2
        top_opts.window_padding_em = ImVec2(0.4, 0.3)
        params.callbacks.add_edge_toolbar(
            hello_imgui.EdgeToolbarType.top,
            self.top_toolbar.safe_render,
            top_opts,
        )

        if before_imgui_render is not None:
            params.callbacks.before_imgui_render = before_imgui_render

        # The command palette renders as an overlay AFTER dockable windows
        # so it draws on top. Ctrl+Shift+P keybind is also checked here.
        def _post_render() -> None:
            self._check_global_keybinds()
            self.command_palette.render()

        params.callbacks.post_render_dockable_windows = _post_render

        # post_init: build renderer THEN call the app's post_init.
        def _combined_post_init() -> None:
            self._post_init()
            if post_init is not None:
                post_init()

        params.callbacks.post_init = _combined_post_init
        params.callbacks.before_exit = self._on_exit

        # GLFW drop callback is registered in _post_init (after window exists).

        hello_imgui.run(params)

    # ------------------------------------------------------------------
    # Drag-and-drop via GLFW drop callback (ctypes)
    # ------------------------------------------------------------------

    _glfw_drop_cb_ref = None  # prevent GC of the ctypes callback

    def _setup_glfw_drop_callback(self) -> None:
        """Register a GLFW file-drop callback via ctypes.

        Called from ``post_init`` (not ``post_init_add_platform_backend_callbacks``)
        so the GLFW window is fully ready. Uses the same ``libglfw.so.3`` that
        imgui_bundle links against — loaded via the exact path from ``ldd``.
        """
        import ctypes
        from pathlib import Path

        try:
            win_addr = hello_imgui.get_glfw_window_address()
            if not win_addr:
                _LOGGER.info("drag-and-drop: no GLFW window — skipping")
                return

            # Load the exact versioned libglfw.so.3 that imgui_bundle links.
            # dlopen returns the same handle since it's already loaded.
            import imgui_bundle
            ib_dir = Path(imgui_bundle.__file__).parent
            lib_path = ib_dir / "libglfw.so.3"
            if not lib_path.exists():
                _LOGGER.info("drag-and-drop: libglfw.so.3 not found — skipping")
                return
            glfw_lib = ctypes.cdll.LoadLibrary(str(lib_path))

            # typedef void (*GLFWdropfun)(GLFWwindow*, int, const char*[])
            DROPFUN = ctypes.CFUNCTYPE(
                None,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_char_p),
            )

            # Set proper argtypes so ctypes marshals correctly.
            glfw_lib.glfwSetDropCallback.argtypes = [ctypes.c_void_p, DROPFUN]
            glfw_lib.glfwSetDropCallback.restype = DROPFUN

            def _on_drop(_window, count, paths):
                try:
                    for i in range(count):
                        raw = paths[i]
                        path_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                        _LOGGER.info("drag-and-drop: %s", path_str)
                        hello_imgui.log(
                            hello_imgui.LogLevel.info,
                            f"loading dropped file: {path_str}",
                        )
                        self._app.command_bus.run_operation(
                            LoadMeshOperation(), params={"path": path_str}
                        )
                except Exception:                           # noqa: BLE001
                    _LOGGER.exception("drag-and-drop callback error")

            # prevent GC — must be a class-level ref
            UIRunner._glfw_drop_cb_ref = DROPFUN(_on_drop)

            glfw_lib.glfwSetDropCallback(
                ctypes.c_void_p(win_addr),
                UIRunner._glfw_drop_cb_ref,
            )
            _LOGGER.info("drag-and-drop: GLFW drop callback registered")

        except Exception:                                   # noqa: BLE001
            _LOGGER.exception("drag-and-drop: failed to set up")
