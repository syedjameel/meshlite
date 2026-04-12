"""``SidebarOutlinerPanel`` — tree of loaded document nodes.

M6 shipped this as a flat list with eye-toggle and click-to-select. M7
adds: triangle count next to name, delete button, right-click context menu
stub, hover highlighting.

The panel remains a flat list in M7 because meshlite doesn't yet have
the concept of node hierarchies (groups, parent-child). When that lands
(Phase 2), this panel becomes a real tree with expand/collapse.
"""

from __future__ import annotations

from imgui_bundle import hello_imgui, imgui

from .. import icons
from .base_panel import BasePanel


class SidebarOutlinerPanel(BasePanel):
    title = "Outliner"

    def render(self) -> None:
        doc = self._app.document
        sel = self._app.selection

        nodes = doc.all_nodes()
        if not nodes:
            imgui.text_disabled("(empty)")
            imgui.spacing()
            imgui.text_disabled("File → Open Mesh to begin")
            imgui.spacing()
            imgui.text_disabled(f"or click {icons.safe(icons.FILE_OPEN)} in the toolbar")
            return

        imgui.text_disabled(f"{len(nodes)} mesh(es)")
        imgui.separator()
        imgui.spacing()

        for node in nodes:
            self._render_node_row(node, sel)

    def _render_node_row(self, node, sel) -> None:
        is_selected = node.id in sel.selected
        node_id = node.id

        # Visibility eye toggle
        eye = icons.safe(icons.EYE if node.visible else icons.EYE_CLOSED)
        if imgui.small_button(f"{eye}##vis_{node_id}"):
            node.visible = not node.visible
        imgui.same_line()

        # Selectable row — whole remaining width
        flags = imgui.SelectableFlags_.allow_double_click.value
        label = node.name

        clicked, _ = imgui.selectable(
            f"{label}##sel_{node_id}", is_selected, flags
        )
        if clicked:
            if imgui.get_io().key_ctrl:
                sel.toggle(node_id)
            else:
                sel.set([node_id])

        # Suffix drawn right after the selectable (on the same line isn't
        # possible after selectable — show as tooltip instead for dense lists)
        if imgui.is_item_hovered():
            imgui.begin_tooltip()
            imgui.text(node.name)
            imgui.text_disabled(f"{node.mesh.num_vertices:,} verts, {node.mesh.num_faces:,} faces")
            if node.source_path:
                path_str = str(node.source_path)
                if len(path_str) > 60:
                    path_str = "..." + path_str[-57:]
                imgui.text_disabled(path_str)
            imgui.end_tooltip()

        # Right-click context menu
        if imgui.begin_popup_context_item(f"##ctx_{node_id}"):
            if imgui.menu_item("Select", "", False)[0]:
                sel.set([node_id])
            if imgui.menu_item("Toggle Visibility", "", False)[0]:
                node.visible = not node.visible
            imgui.separator()
            if imgui.menu_item(f"{icons.safe(icons.TRASH)} Delete", "", False)[0]:
                self._app.document.remove_node(node_id)
                if is_selected:
                    sel.remove(node_id)
                hello_imgui.log(
                    hello_imgui.LogLevel.info,
                    f"removed node: {node.name}",
                )
            imgui.end_popup()
