"""``SidebarOperationsPanel`` — browse registered ops grouped by category.

Walks :meth:`OperationRegistry.by_category` and renders one collapsing
header per category, with one selectable per op. Clicking an op sets
``runner.pending_op = (op_cls, defaults)`` which causes the Properties
panel to switch to pending-op mode and render the ParamSchema form with
a Run button.
"""

from __future__ import annotations

from imgui_bundle import imgui

from meshlite.ops import OperationRegistry

from .. import icons
from .base_panel import BasePanel


class SidebarOperationsPanel(BasePanel):
    title = "Operations"

    def render(self) -> None:
        registry = OperationRegistry.by_category()
        if not registry:
            imgui.text_disabled("(no operations registered)")
            return

        for category in sorted(registry.keys()):
            ops = registry[category]
            if imgui.collapsing_header(
                f"{category} ({len(ops)})",
                imgui.TreeNodeFlags_.default_open.value,
            ):
                imgui.indent(8)
                for op_cls in ops:
                    self._render_op_row(op_cls)
                imgui.unindent(8)

    def _render_op_row(self, op_cls) -> None:
        runner = self._runner

        # Icon from the op (raw codicon char) or fallback.
        icon_char = getattr(op_cls, "icon", "")
        icon_str = icons.safe(icon_char) + " " if icon_char else ""

        label = f"{icon_str}{op_cls.label}##op_{op_cls.id}"
        desc = getattr(op_cls, "description", "")

        # Highlight if this op is currently pending.
        is_pending = (
            runner.pending_op is not None and runner.pending_op[0] is op_cls
        )

        if imgui.selectable(label, is_pending)[0]:
            # Set the pending op — Properties panel picks it up next frame.
            schema = getattr(op_cls, "schema", None)
            defaults = schema.defaults() if schema else {}
            runner.pending_op = (op_cls, defaults)

        if desc and imgui.is_item_hovered():
            imgui.set_tooltip(desc)
