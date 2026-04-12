"""``MeshInfoPanel`` — comprehensive mesh statistics in the bottom tab.

Reads from ``node.info_cache``, computing it lazily on first access for the
selected node via :func:`meshlite.domain.mesh_info.compute`. The cache is
invalidated to ``None`` by ``Document.replace_mesh`` whenever an op mutates
a node's mesh — so the next frame's render re-computes it.

Layout is a clean multi-section table matching the way professional mesh
tools (MeshInspector, MeshLab) present statistics.
"""

from __future__ import annotations

from imgui_bundle import imgui

from meshlite.app_state import MeshInfo

from ...widgets.info_cache import ensure_info_cache
from ..base_panel import BasePanel


def _row(label: str, value: str, *, muted: bool = False) -> None:
    """Draw one label–value row in a two-column layout."""
    imgui.text(label)
    imgui.same_line(160)
    if muted:
        imgui.text_disabled(value)
    else:
        imgui.text(value)


def _section(title: str) -> bool:
    """Draw a section header. Returns True always (just for visual grouping)."""
    imgui.spacing()
    imgui.text_colored(imgui.ImVec4(0.5, 0.75, 1.0, 1.0), title)
    imgui.separator()
    imgui.spacing()
    return True


class MeshInfoPanel(BasePanel):
    title = "Mesh Info"

    def render(self) -> None:
        sel = self._app.selection
        if sel.primary is None:
            imgui.text_disabled("Select a mesh to see its statistics.")
            return

        node = self._app.document.get_node(sel.primary)
        if node is None:
            imgui.text_disabled("(stale selection)")
            return

        info = ensure_info_cache(node)
        if info is None:
            imgui.text_colored(
                imgui.ImVec4(1.0, 0.4, 0.4, 1.0),
                "Error computing mesh info — see console",
            )
            return

        imgui.text(f"Mesh: {node.name}")
        imgui.spacing()

        # Refresh button
        if imgui.small_button("Refresh"):
            node.info_cache = None
            return  # will recompute next frame

        self._render_topology(info)
        self._render_geometry(info)
        self._render_bounding_box(info)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _render_topology(self, info: MeshInfo) -> None:
        _section("Topology")
        _row("Vertices", f"{info.num_vertices:,}")
        _row("Faces", f"{info.num_faces:,}")
        _row("Holes", f"{info.num_holes}")

        wt = info.is_watertight
        imgui.text("Watertight")
        imgui.same_line(160)
        imgui.text_colored(
            imgui.ImVec4(0.5, 0.9, 0.5, 1.0) if wt else imgui.ImVec4(1.0, 0.6, 0.4, 1.0),
            "Yes" if wt else f"No ({info.num_holes} holes)",
        )

        _row("Components", f"{info.connected_components}")

    def _render_geometry(self, info: MeshInfo) -> None:
        _section("Geometry")
        _row("Surface area", f"{info.surface_area:.6f}")
        _row("Volume", f"{info.volume:.6f}")
        _row("Avg edge length", f"{info.average_edge_length:.6f}")

    def _render_bounding_box(self, info: MeshInfo) -> None:
        _section("Bounding Box")
        _row("Min", f"({info.bbox_min[0]:9.4f}, {info.bbox_min[1]:9.4f}, {info.bbox_min[2]:9.4f})")
        _row("Max", f"({info.bbox_max[0]:9.4f}, {info.bbox_max[1]:9.4f}, {info.bbox_max[2]:9.4f})")
        _row("Dimensions", f"{info.bbox_dimensions[0]:.4f} x {info.bbox_dimensions[1]:.4f} x {info.bbox_dimensions[2]:.4f}")
        _row("Center", f"({info.bbox_center[0]:9.4f}, {info.bbox_center[1]:9.4f}, {info.bbox_center[2]:9.4f})")
