"""``SelectionModel`` — which document nodes are selected.

Sibling of :class:`Document`. Stored separately because UI panels (the
sidebar outliner, the properties panel, the viewport overlay) all read
selection state, and we want them to subscribe to selection changes
independently of mesh changes.
"""

from __future__ import annotations

from collections.abc import Iterable

from .events import EventBus, SelectionChanged


class SelectionModel:
    """A primary node + a multi-selection set, both keyed by node id."""

    def __init__(self, events: EventBus) -> None:
        self._events = events
        self._primary: str | None = None
        self._selected: set[str] = set()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @property
    def primary(self) -> str | None:
        return self._primary

    @property
    def selected(self) -> frozenset[str]:
        return frozenset(self._selected)

    def is_selected(self, node_id: str) -> bool:
        return node_id in self._selected

    def __len__(self) -> int:
        return len(self._selected)

    def __bool__(self) -> bool:
        return bool(self._selected)

    # ------------------------------------------------------------------
    # Mutate (each emits SelectionChanged exactly once if state changed)
    # ------------------------------------------------------------------

    def set(self, ids: Iterable[str]) -> None:
        new_selected = set(ids)
        new_primary = next(iter(new_selected), None) if new_selected else None
        if new_selected == self._selected and new_primary == self._primary:
            return
        self._selected = new_selected
        self._primary = new_primary
        self._emit()

    def add(self, node_id: str) -> None:
        if node_id in self._selected:
            return
        self._selected.add(node_id)
        if self._primary is None:
            self._primary = node_id
        self._emit()

    def remove(self, node_id: str) -> None:
        if node_id not in self._selected:
            return
        self._selected.discard(node_id)
        if self._primary == node_id:
            self._primary = next(iter(self._selected), None)
        self._emit()

    def toggle(self, node_id: str) -> None:
        if node_id in self._selected:
            self.remove(node_id)
        else:
            self.add(node_id)

    def clear(self) -> None:
        if not self._selected and self._primary is None:
            return
        self._selected.clear()
        self._primary = None
        self._emit()

    def _emit(self) -> None:
        self._events.emit(
            SelectionChanged(
                primary=self._primary,
                selected=tuple(sorted(self._selected)),
            )
        )
