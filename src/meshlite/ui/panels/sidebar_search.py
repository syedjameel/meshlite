"""``SidebarSearchPanel`` — search across document nodes and operations.

Fuzzy-matches the typed query against node names and operation labels
using the same fzf-style scorer as the command palette.
"""

from __future__ import annotations

from imgui_bundle import imgui

from meshlite.ops import OperationRegistry
from meshlite.utils.fuzzy import filter_and_rank

from .base_panel import BasePanel


class SidebarSearchPanel(BasePanel):
    title = "Search"

    def __init__(self, app, runner) -> None:
        super().__init__(app, runner)
        self._query: str = ""

    def render(self) -> None:
        changed, self._query = imgui.input_text_with_hint(
            "##search_input", "Search nodes and operations...", self._query
        )

        imgui.separator()

        if not self._query.strip():
            imgui.text_disabled("Type to search nodes and operations")
            return

        q = self._query.strip()
        self._render_node_results(q)
        self._render_op_results(q)

    def _render_node_results(self, query: str) -> None:
        nodes = self._app.document.all_nodes()
        if not nodes:
            return

        names = [n.name for n in nodes]
        ranked = filter_and_rank(query, names)

        if not ranked:
            return

        if imgui.collapsing_header(
            f"Nodes ({len(ranked)})##search_nodes",
            imgui.TreeNodeFlags_.default_open.value,
        ):
            for _score, name, _indices in ranked:
                node = next((n for n in nodes if n.name == name), None)
                if node is None:
                    continue
                is_selected = node.id in self._app.selection.selected
                clicked, _ = imgui.selectable(
                    f"  {name}##search_node_{node.id}", is_selected
                )
                if clicked:
                    self._app.selection.set([node.id])

    def _render_op_results(self, query: str) -> None:
        all_ops = OperationRegistry.all()
        if not all_ops:
            return

        display_map: dict[str, type] = {}
        for op_cls in all_ops:
            cat = getattr(op_cls, "category", "General")
            label = getattr(op_cls, "label", op_cls.__name__)
            display_map[f"{cat}: {label}"] = op_cls

        ranked = filter_and_rank(query, list(display_map.keys()))
        if not ranked:
            return

        if imgui.collapsing_header(
            f"Operations ({len(ranked)})##search_ops",
            imgui.TreeNodeFlags_.default_open.value,
        ):
            for _score, display, _indices in ranked:
                op_cls = display_map.get(display)
                if op_cls is None:
                    continue
                clicked, _ = imgui.selectable(f"  {display}##search_op_{op_cls.id}", False)
                if clicked:
                    schema = getattr(op_cls, "schema", None)
                    defaults = schema.defaults() if schema else {}
                    self._runner.pending_op = (op_cls, defaults)
                if imgui.is_item_hovered():
                    desc = getattr(op_cls, "description", "")
                    if desc:
                        imgui.set_tooltip(desc)
