"""``PropertiesPanel`` — right-side panel for node info + pending-op params.

Two modes:

1. **Node info** (default): shows mesh statistics via :class:`MeshInfo`
   cache. Active when no op is pending.

2. **Pending-op** (M8): shows the op's :class:`ParamSchema` auto-rendered
   as ImGui widgets via :func:`render_params`, plus a **Run** button. Active
   when ``runner.pending_op`` is set (from the sidebar Operations browser,
   the top toolbar, or the M9 command palette). Clicking Run dispatches the
   op through the :class:`CommandBus`.

The ``pending_op`` state lives on the runner:

    runner.pending_op: tuple[type[Operation], dict[str, Any]] | None
"""

from __future__ import annotations

from imgui_bundle import hello_imgui, imgui

from meshlite.app_state import MeshInfo
from meshlite.ops.base import Operation

from ..widgets.info_cache import ensure_info_cache
from ..widgets.param_widgets import render_params, set_document_context
from .base_panel import BasePanel


class PropertiesPanel(BasePanel):
    title = "Properties"

    def render(self) -> None:
        runner = self._runner

        # If an op is pending, render the op form.
        if runner.pending_op is not None:
            self._render_pending_op()
            return

        # Default: show node info.
        self._render_node_info()

    # ------------------------------------------------------------------
    # Pending-op mode (M8)
    # ------------------------------------------------------------------

    def _render_pending_op(self) -> None:
        runner = self._runner
        op_cls, values = runner.pending_op
        op_label = getattr(op_cls, "label", op_cls.__name__)
        op_desc = getattr(op_cls, "description", "")
        schema = getattr(op_cls, "schema", None)
        requires = getattr(op_cls, "requires", "one_mesh")

        imgui.text_colored(imgui.ImVec4(0.5, 0.8, 1.0, 1.0), f"Operation: {op_label}")
        if op_desc:
            imgui.text_disabled(op_desc)
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        # Render the parameter widgets.
        if schema and len(schema) > 0:
            # Set document context so node_picker widgets can list meshes.
            set_document_context(self._app.document)
            render_params(schema, values)
            imgui.spacing()
            imgui.separator()
            imgui.spacing()

        # Selection check.
        target_id = self._app.selection.primary
        needs_mesh = requires != "none"
        if needs_mesh and target_id is None:
            imgui.text_colored(
                imgui.ImVec4(1.0, 0.6, 0.4, 1.0),
                "Select a mesh first",
            )
            imgui.spacing()

        # Run button.
        can_run = not needs_mesh or target_id is not None
        active_op = runner.active_task_id is not None
        if active_op:
            imgui.begin_disabled()
        if imgui.button("Run", imgui.ImVec2(-1, 32)) and can_run:
            self._dispatch_pending_op(op_cls, values, target_id)
        if active_op:
            imgui.end_disabled()

        imgui.spacing()

        # Cancel button (clears the pending state without dispatching).
        if imgui.button("Cancel", imgui.ImVec2(-1, 0)):
            runner.pending_op = None

    def _dispatch_pending_op(
        self,
        op_cls: type[Operation],
        values: dict,
        target_id: str | None,
    ) -> None:
        runner = self._runner
        try:
            op: Operation = op_cls()
            params = dict(values)

            # For ops with node_picker params, inject the actual MeshData
            # into the params dict so the worker can access mesh B without
            # touching the document from the worker thread.
            schema = getattr(op_cls, "schema", None)
            if schema:
                for p in schema.params:
                    if p.kind == "node_picker" and params.get(p.name):
                        node_b = self._app.document.get_node(params[p.name])
                        if node_b is not None:
                            params[f"_{p.name.replace('_id', '_data')}"] = node_b.mesh.clone()

            kwargs = {"params": params}
            if target_id is not None:
                kwargs["target_node_id"] = target_id
            self._app.command_bus.run_operation(op, **kwargs)
            runner.pending_op = None              # clear the form
        except Exception as e:
            hello_imgui.log(
                hello_imgui.LogLevel.error,
                f"Failed to dispatch {op_cls.label}: {e}",
            )

    # ------------------------------------------------------------------
    # Node-info mode (default, same as before)
    # ------------------------------------------------------------------

    def _render_node_info(self) -> None:
        sel = self._app.selection
        if sel.primary is None:
            imgui.text_disabled("No selection")
            imgui.spacing()
            imgui.text_disabled("Click a mesh in the Outliner")
            imgui.text_disabled("to inspect its properties.")
            imgui.spacing()
            imgui.separator()
            imgui.spacing()
            imgui.text_disabled("Or select an operation from")
            imgui.text_disabled("the sidebar Operations browser")
            imgui.text_disabled("to configure and run it here.")
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

        self._render_header(node)
        self._render_stats(info)
        self._render_visibility(node)

    def _render_header(self, node) -> None:
        imgui.text_colored(imgui.ImVec4(0.9, 0.9, 0.9, 1.0), node.name)
        if node.source_path:
            path_str = str(node.source_path)
            if len(path_str) > 45:
                path_str = "..." + path_str[-42:]
            imgui.text_disabled(path_str)
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

    def _render_stats(self, info: MeshInfo) -> None:
        imgui.columns(2, "##props_stats", False)
        imgui.set_column_width(0, 120)

        for label, value in (
            ("Vertices", f"{info.num_vertices:,}"),
            ("Faces", f"{info.num_faces:,}"),
            ("Components", f"{info.connected_components}"),
            ("Surface area", f"{info.surface_area:.4f}"),
            ("Volume", f"{info.volume:.4f}"),
            ("Avg edge len", f"{info.average_edge_length:.4f}"),
            ("Dimensions", f"{info.bbox_dimensions[0]:.3f} x {info.bbox_dimensions[1]:.3f} x {info.bbox_dimensions[2]:.3f}"),
        ):
            imgui.text(label)
            imgui.next_column()
            imgui.text(value)
            imgui.next_column()

        # Watertight row with color.
        imgui.text("Watertight")
        imgui.next_column()
        wt = info.is_watertight
        imgui.text_colored(
            imgui.ImVec4(0.5, 0.9, 0.5, 1.0) if wt else imgui.ImVec4(1.0, 0.6, 0.4, 1.0),
            "Yes" if wt else f"No ({info.num_holes} holes)",
        )
        imgui.next_column()

        imgui.columns(1)
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

    def _render_visibility(self, node) -> None:
        imgui.text("Visible")
        imgui.same_line(120)
        _, node.visible = imgui.checkbox(f"##propvis_{node.id}", node.visible)
        imgui.spacing()
