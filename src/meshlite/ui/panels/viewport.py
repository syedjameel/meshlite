"""``ViewportPanel`` — the 3D viewport.

Owns:
- the moderngl FBO render call (the runner owns the renderer; the panel
  just calls ``renderer.render`` once per frame with the current items)
- the toolbar strip above the FBO image (MeshInspector-inspired)
- mouse drag-to-rotate, right-drag-to-pan, and wheel-to-zoom on the FBO image

Input ordering: the panel predicts the FBO image rect using
``imgui.get_cursor_screen_pos()`` *before* calling ``imgui.image()``, then
handles input, then renders. This ensures the camera matrix reflects the
current frame's mouse state (no 1-frame lag).

Drag handling: the panel tracks its own ``_rotating``/``_panning`` state
and calls ``cam.drag(mx, my)`` every frame while the button is held —
regardless of whether the cursor has left the viewport. This avoids
ImGui's built-in drag threshold (6px default) and hover-gating.

Does NOT own the renderer, camera, or GPU upload event subscribers — those
live on the runner because they survive panel rebuilds and need a stable
reference for the lifetime of the GL context.
"""

from __future__ import annotations

from imgui_bundle import ImVec2, imgui

from meshlite.render import RenderItem

from .base_panel import BasePanel


class ViewportPanel(BasePanel):
    """Renders the 3D viewport: toolbar + FBO image + mouse input."""

    title = "Viewport"

    def __init__(self, app, runner) -> None:
        super().__init__(app, runner)
        # Predicted FBO image rect (updated each frame before render).
        self._image_rect_min = ImVec2(0.0, 0.0)
        self._image_hovered = False
        # Persistent drag state — independent of ImGui's hover/threshold logic.
        self._rotating = False
        self._panning = False
        self._last_pan = (0.0, 0.0)

    def render(self) -> None:
        runner = self._runner
        if runner.renderer is None or runner.camera is None:
            imgui.text("Renderer not initialized")
            return

        self._render_toolbar()
        self._render_viewport_image()

    # ------------------------------------------------------------------
    # Local viewport toolbar — progress display for the active op
    # ------------------------------------------------------------------

    def _render_toolbar(self) -> None:
        runner = self._runner
        if runner.active_task_id is not None:
            task = self._app.task_manager.get_task(runner.active_task_id)
            if task is not None:
                runner.last_progress = task.progress
                if task.progress_message:
                    runner.last_progress_msg = task.progress_message
            imgui.progress_bar(
                runner.last_progress,
                ImVec2(180, 0),
                runner.last_progress_msg,
            )

    # ------------------------------------------------------------------
    # Input → render → display (order matters: input first, no 1-frame lag)
    # ------------------------------------------------------------------

    def _render_viewport_image(self) -> None:
        runner = self._runner

        # Resize the renderer to fill the panel content region.
        avail = imgui.get_content_region_avail()
        w, h = max(1, int(avail.x)), max(1, int(avail.y))
        if (w, h) != runner.viewport_size:
            runner.viewport_size = (w, h)
            runner.renderer.resize(w, h)
            runner.camera.set_viewport(w, h)

        # Predict where imgui.image() will place the FBO image — the next
        # widget's top-left is the current cursor position in screen space.
        self._image_rect_min = imgui.get_cursor_screen_pos()
        mouse = imgui.get_mouse_pos()
        self._image_hovered = (
            self._image_rect_min.x <= mouse.x < self._image_rect_min.x + w
            and self._image_rect_min.y <= mouse.y < self._image_rect_min.y + h
        )

        # Handle input BEFORE render so this frame uses the updated camera.
        self._handle_input(w, h)

        # Render with the (possibly updated) camera matrix.
        items, scene_scale = self._build_render_items()
        runner.renderer.render(
            items, runner.camera, runner.view, scene_scale=scene_scale
        )

        imgui.image(
            imgui.ImTextureRef(runner.renderer.texture_glo),
            ImVec2(float(w), float(h)),
            ImVec2(0, 1),
            ImVec2(1, 0),
        )

        # Frame All hotkey works while the viewport is focused.
        if imgui.is_window_focused() and imgui.is_key_pressed(imgui.Key.f):
            runner.fit_camera_to_document()

    def _build_render_items(self) -> tuple[list[RenderItem], float]:
        runner = self._runner
        items: list[RenderItem] = []
        scene_scale = 1.0
        selection = self._app.selection.selected
        for node in self._app.document.visible_nodes():
            if node.gpu_mesh is None:
                if node.gpu_upload_failed:
                    continue
                runner.upload_node(node)
                if node.gpu_mesh is None:
                    continue
            prefs = self._app.preferences
            items.append(
                RenderItem(
                    gpu_mesh=node.gpu_mesh,
                    model=node.transform.to_mat4(),
                    color=prefs.mesh_color,
                    selected=node.id in selection,
                    selected_color=prefs.selected_mesh_color,
                )
            )
            (xn, yn, zn), (xx, yx, zx) = node.mesh.bounding_box()
            scene_scale = max(scene_scale, xx - xn, yx - yn, zx - zn)
        return items, scene_scale

    # ------------------------------------------------------------------
    # Mouse input — explicit drag state mimics GLFW callbacks
    # ------------------------------------------------------------------

    def _handle_input(self, w: int, h: int) -> None:
        cam = self._runner.camera
        if cam is None:
            return

        mouse = imgui.get_mouse_pos()
        mx = mouse.x - self._image_rect_min.x
        my = mouse.y - self._image_rect_min.y
        io = imgui.get_io()

        # Release events can be missed when the mouse is released outside
        # the ImGui window (Alt-Tab mid-drag, drag off-window). Without a
        # recovery path, _rotating / _panning stay stuck and the next
        # click misbehaves. Reconcile state against the real button state.
        if self._rotating and not imgui.is_mouse_down(0):
            cam.end_drag()
            self._rotating = False
        if self._panning and not (imgui.is_mouse_down(1) or imgui.is_mouse_down(2)):
            self._panning = False

        # --- Left button: arcball rotate ---
        if imgui.is_mouse_clicked(0) and self._image_hovered:
            # Snap the pivot to the visible mesh center BEFORE starting
            # the drag — this absorbs any pan/zoom drift so rotation always
            # orbits around what the user is actually looking at. The
            # preserve_view variant adjusts pan to keep the image identical.
            self._runner.recenter_pivot_on_visible()
            self._rotating = True
            cam.begin_drag(mx, my)
        if imgui.is_mouse_released(0) and self._rotating:
            cam.end_drag()
            self._rotating = False
        if self._rotating and imgui.is_mouse_down(0):
            cam.drag(mx, my)

        # --- Right/middle button: pan ---
        for btn in (1, 2):
            if imgui.is_mouse_clicked(btn) and self._image_hovered:
                self._panning = True
                self._last_pan = (mx, my)
            if imgui.is_mouse_released(btn) and self._panning:
                self._panning = False
            if self._panning and imgui.is_mouse_down(btn):
                dx = mx - self._last_pan[0]
                dy = my - self._last_pan[1]
                if dx != 0.0 or dy != 0.0:
                    cam.pan(dx, dy)
                    self._last_pan = (mx, my)

        # --- Scroll wheel: zoom toward cursor (only when hovered) ---
        if self._image_hovered and io.mouse_wheel != 0.0:
            ray = cam.screen_ray(mx, my, w, h)
            cam.zoom_towards_cursor(io.mouse_wheel, ray)
