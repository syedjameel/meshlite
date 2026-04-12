"""``SidebarSettingsPanel`` — user preferences UI.

Reads and writes ``app.preferences`` live. All changes take effect
immediately because consumers read from preferences each frame.
Preferences are persisted automatically on exit via hello_imgui's
user pref API.
"""

from __future__ import annotations

from imgui_bundle import imgui

from meshlite import __version__
from meshlite.app_state.preferences import Preferences
from meshlite.ops import OperationRegistry

from .base_panel import BasePanel

_HEADER = imgui.ImVec4(0.7, 0.7, 0.7, 1.0)


class SidebarSettingsPanel(BasePanel):
    title = "Settings"

    def render(self) -> None:
        prefs = self._app.preferences
        self._section_viewport(prefs)
        self._section_rendering(prefs)
        self._section_camera(prefs)
        self._section_history(prefs)
        self._section_about()
        self._section_reset(prefs)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _section_viewport(self, prefs: Preferences) -> None:
        if imgui.collapsing_header("Viewport", imgui.TreeNodeFlags_.default_open.value):
            changed, v = imgui.slider_float(
                "Rotate sensitivity", prefs.rotate_sensitivity, 0.001, 0.05, "%.4f"
            )
            if changed:
                prefs.rotate_sensitivity = v

            changed, v = imgui.slider_float(
                "Zoom sensitivity", prefs.zoom_sensitivity, 0.01, 0.5, "%.3f"
            )
            if changed:
                prefs.zoom_sensitivity = v

            changed, v = imgui.slider_float(
                "Pan sensitivity", prefs.pan_sensitivity, 0.001, 0.05, "%.4f"
            )
            if changed:
                prefs.pan_sensitivity = v

    def _section_rendering(self, prefs: Preferences) -> None:
        if imgui.collapsing_header("Rendering", imgui.TreeNodeFlags_.default_open.value):
            # Background color (RGBA)
            changed, color = imgui.color_edit4(
                "Background", list(prefs.background_color)
            )
            if changed:
                prefs.background_color = tuple(color)
                self._runner.view.background = prefs.background_color

            # Mesh color (RGB)
            changed, color = imgui.color_edit3("Mesh color", list(prefs.mesh_color))
            if changed:
                prefs.mesh_color = tuple(color)

            # Selected mesh color (RGB)
            changed, color = imgui.color_edit3(
                "Selected color", list(prefs.selected_mesh_color)
            )
            if changed:
                prefs.selected_mesh_color = tuple(color)

            imgui.spacing()
            imgui.text_colored(_HEADER, "Lighting")

            changed, v = imgui.slider_float(
                "Ambient", prefs.ambient_strength, 0.0, 1.0, "%.2f"
            )
            if changed:
                prefs.ambient_strength = v
                self._runner.view.ambient_strength = v

            changed, v = imgui.slider_float(
                "Specular strength", prefs.specular_strength, 0.0, 1.0, "%.2f"
            )
            if changed:
                prefs.specular_strength = v
                self._runner.view.specular_strength = v

            changed, v = imgui.slider_float(
                "Specular exponent", prefs.specular_exponent, 1.0, 128.0, "%.0f"
            )
            if changed:
                prefs.specular_exponent = v
                self._runner.view.specular_exponent = v

    def _section_camera(self, prefs: Preferences) -> None:
        if imgui.collapsing_header("Camera"):
            changed, v = imgui.slider_float(
                "Field of view", prefs.fov_deg, 10.0, 120.0, "%.1f deg"
            )
            if changed:
                prefs.fov_deg = v
                cam = self._runner.camera
                if cam is not None:
                    cam.fov_deg = v
                    cam.set_viewport(cam.width, cam.height)

    def _section_history(self, prefs: Preferences) -> None:
        if imgui.collapsing_header("History"):
            changed, v = imgui.slider_int(
                "Undo depth", prefs.undo_max_depth, 1, 200
            )
            if changed:
                prefs.undo_max_depth = v
                self._app.history.max_depth = v

            # Display as GB for readability.
            gb = prefs.undo_max_bytes / (1024 ** 3)
            changed, gb = imgui.slider_float("Memory cap (GB)", gb, 0.1, 8.0, "%.1f")
            if changed:
                prefs.undo_max_bytes = int(gb * 1024 ** 3)
                self._app.history.max_total_bytes = prefs.undo_max_bytes

    def _section_about(self) -> None:
        if imgui.collapsing_header("About"):
            imgui.text(f"meshlite {__version__}")
            imgui.text(f"Loaded meshes: {len(self._app.document)}")
            imgui.text(f"Registered ops: {len(OperationRegistry.all())}")
            imgui.text(f"Undo depth: {len(self._app.history)}")

    def _section_reset(self, prefs: Preferences) -> None:
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        if imgui.button("Reset to Defaults"):
            defaults = Preferences()
            # Copy defaults into the live instance.
            for f in prefs.__dataclass_fields__:
                if f != "recent_files":  # preserve recent files on reset
                    setattr(prefs, f, getattr(defaults, f))
            self._runner._apply_preferences()
