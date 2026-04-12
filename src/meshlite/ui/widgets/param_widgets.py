"""Auto-rendering of :class:`ParamSchema` as ImGui widgets.

:func:`render_params` is the generic function that the Properties panel
calls each frame when an operation is "pending". It iterates the schema's
:class:`Param` list and draws the appropriate ImGui widget for each kind.

Adding a new :class:`ParamKind` is one ``elif`` clause here and one
test — no other files need editing.

The optional ``document`` parameter enables the ``"node_picker"`` kind,
which renders a dropdown of all nodes in the document. Used by multi-mesh
ops (Boolean, Align, Measure Distance).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from imgui_bundle import imgui

from meshlite.ops.base import Param, ParamSchema

if TYPE_CHECKING:
    from meshlite.app_state.document import Document


# Module-level reference set by the Properties panel each frame before
# calling render_params. Avoids changing the function signature (which
# would break all existing callers).
_active_document: Document | None = None


def set_document_context(doc: Document | None) -> None:
    """Set the document used by ``node_picker`` widgets this frame."""
    global _active_document
    _active_document = doc


def render_params(schema: ParamSchema, values: dict[str, Any]) -> bool:
    """Render ImGui widgets for every param in ``schema``.

    Mutates ``values`` in place. Returns ``True`` if any value changed this
    frame.
    """
    changed = False
    for p in schema.params:
        # Dynamic visibility.
        if p.visible_if is not None and not p.visible_if(values):
            continue
        c = _render_one(p, values)
        changed = changed or c
    return changed


def _render_one(p: Param, values: dict[str, Any]) -> bool:
    """Render a single param and update ``values[p.name]`` if changed."""
    c = False

    if p.kind == "float":
        lo = p.min if p.min is not None else 0.0
        hi = p.max if p.max is not None else 100.0
        c, values[p.name] = imgui.slider_float(
            p.label, float(values[p.name]), lo, hi
        )

    elif p.kind == "int":
        lo = int(p.min) if p.min is not None else 0
        hi = int(p.max) if p.max is not None else 100
        c, values[p.name] = imgui.slider_int(
            p.label, int(values[p.name]), lo, hi
        )

    elif p.kind == "bool":
        c, values[p.name] = imgui.checkbox(p.label, bool(values[p.name]))

    elif p.kind == "enum" and p.choices:
        items = list(p.choices)
        cur = values[p.name]
        idx = items.index(cur) if cur in items else 0
        c, new_idx = imgui.combo(p.label, idx, items)
        if c:
            values[p.name] = items[new_idx]

    elif p.kind == "string" or p.kind == "path":
        c, values[p.name] = imgui.input_text(p.label, str(values[p.name]))

    elif p.kind == "node_picker":
        c = _render_node_picker(p, values)

    else:
        imgui.text_disabled(f"[unsupported kind: {p.kind}] {p.label}")

    # Help tooltip on the label.
    if p.help and imgui.is_item_hovered():
        imgui.set_tooltip(p.help)

    return c


def _render_node_picker(p: Param, values: dict[str, Any]) -> bool:
    """Render a combo box listing all document nodes by name.

    The selected value is stored as the node's id string.
    """
    doc = _active_document
    if doc is None:
        imgui.text_disabled(f"{p.label}: (no document context)")
        return False

    nodes = doc.all_nodes()
    if not nodes:
        imgui.text_disabled(f"{p.label}: (no meshes loaded)")
        return False

    names = [n.name for n in nodes]
    ids = [n.id for n in nodes]
    cur_id = values.get(p.name, "")
    cur_idx = ids.index(cur_id) if cur_id in ids else -1

    # Show "(pick a mesh)" as the preview when nothing is selected.
    preview = names[cur_idx] if cur_idx >= 0 else "(pick a mesh)"

    c = False
    if imgui.begin_combo(p.label, preview):
        for i, (name, nid) in enumerate(zip(names, ids, strict=True)):
            selected = i == cur_idx
            if imgui.selectable(f"{name}##np_{nid}", selected)[0]:
                values[p.name] = nid
                c = True
            if selected:
                imgui.set_item_default_focus()
        imgui.end_combo()
    return c


def help_marker(text: str) -> None:
    """Draw a small ``(?)`` marker with a hover tooltip."""
    imgui.text_disabled("(?)")
    if imgui.is_item_hovered():
        imgui.begin_tooltip()
        imgui.push_text_wrap_pos(imgui.get_font_size() * 35.0)
        imgui.text_unformatted(text)
        imgui.pop_text_wrap_pos()
        imgui.end_tooltip()
