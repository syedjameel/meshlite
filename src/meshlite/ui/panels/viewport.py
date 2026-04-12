"""``ViewportPanel`` — the 3D viewport.

Owns:
- the moderngl FBO render call (the runner owns the renderer; the panel
  just calls ``renderer.render`` once per frame with the current items)
- the toolbar strip above the FBO image (MeshInspector-inspired)
- mouse drag-to-rotate and wheel-to-zoom on the FBO image area

Does NOT own the renderer, camera, or GPU upload event subscribers — those
live on the runner because they survive panel rebuilds and need a stable
reference for the lifetime of the GL context.
"""

from __future__ import annotations

from imgui_bundle import ImVec2, imgui
from pyglm import glm

from meshlite.render import RenderItem

from .base_panel import BasePanel

# Fallback defaults — overridden at runtime by preferences.
_ROTATE_SENSITIVITY = 0.005
_ZOOM_SENSITIVITY = 0.1
_PAN_SENSITIVITY = 0.003


class ViewportPanel(BasePanel):
    """Renders the 3D viewport: toolbar + FBO image + mouse input."""

    title = "Viewport"

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
    # FBO image + mouse input
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

        # Build per-frame items from the document.
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

        self._handle_input()

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

    def _handle_input(self) -> None:
        cam = self._runner.camera
        if cam is None:
            return
        if not imgui.is_item_hovered():
            return

        prefs = self._app.preferences
        io = imgui.get_io()

        # Scroll wheel → zoom
        if io.mouse_wheel != 0.0:
            new_zoom = max(0.1, cam.zoom * (1.0 - io.mouse_wheel * prefs.zoom_sensitivity))
            cam.set_zoom(new_zoom)

        # Left-drag → orbit (rotate around target)
        if imgui.is_mouse_dragging(0):
            delta = imgui.get_mouse_drag_delta(0, lock_threshold=0.0)
            imgui.reset_mouse_drag_delta(0)
            yaw = -delta.x * prefs.rotate_sensitivity
            pitch = -delta.y * prefs.rotate_sensitivity
            qy = glm.angleAxis(yaw, glm.vec3(0, 1, 0))
            qx = glm.angleAxis(pitch, glm.vec3(1, 0, 0))
            cam.set_rotation(qy * cam.rotation * qx)

        # Right-drag → pan (screen-space shift, orbit center stays fixed)
        if imgui.is_mouse_dragging(1):
            delta = imgui.get_mouse_drag_delta(1, lock_threshold=0.0)
            imgui.reset_mouse_drag_delta(1)
            cam.pan(delta.x, delta.y)

        # Middle-drag → also pan (3-button mice)
        if imgui.is_mouse_dragging(2):
            delta = imgui.get_mouse_drag_delta(2, lock_threshold=0.0)
            imgui.reset_mouse_drag_delta(2)
            cam.pan(delta.x, delta.y)
