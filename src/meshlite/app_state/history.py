"""Snapshot-based undo / redo for the document.

Strategy (Plan §3, "Undo: snapshot-based"): when a destructive operation
runs, the command bus snapshots ``MeshData.clone()`` of every node the op
touches *before* dispatch. On success it records the post-op meshes too,
and pushes a :class:`HistoryEntry` onto the stack. Undo swaps the live
mesh back to the ``before`` snapshot; redo swaps it forward to the
``after`` snapshot.

Why snapshots and not per-op inverses:
- MeshLib ops are C++ black boxes; an inverse for ``fillHoles`` is
  infeasible.
- ``mrm.Mesh(other)`` is a verified deep copy (M2). Cloning is cheap CPU.
- Undo logic is uniform across every future op — no per-op work needed.

Memory guardrails:
- Stack capped at ``max_depth`` entries (default 20).
- Total estimated bytes capped at ``max_total_bytes`` (default 2 GB).
  Estimated via ``MeshData.mr.heapBytes()``; oldest entries evicted first.

Listeners are not notified by the history stack itself — the command bus
is responsible for emitting events when it applies an undo/redo, because
the stack doesn't know which document the meshes belong to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from meshlite.domain.mesh_data import MeshData

_LOGGER = logging.getLogger("meshlite.history")

DEFAULT_MAX_DEPTH = 20
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB

# Fallback per-element byte estimates when meshlib's heapBytes() is unavailable.
# Derivation: MeshLib stores ~24 bytes positions + ~24 bytes normals + topology
# overhead per vertex; faces are 3 int32 indices + adjacency data.
_EST_BYTES_PER_VERTEX = 64
_EST_BYTES_PER_FACE = 16


@dataclass
class HistoryEntry:
    """One reversible op's worth of state."""

    label: str
    affected_node_ids: tuple[str, ...]
    before: dict[str, MeshData]                  # node_id → snapshot
    after: dict[str, MeshData] = field(default_factory=dict)

    def estimated_bytes(self) -> int:
        """Best-effort byte estimate using meshlib's ``heapBytes()``."""
        total = 0
        for snap in (*self.before.values(), *self.after.values()):
            try:
                total += int(snap.mr.heapBytes())
            except Exception:                    # noqa: BLE001
                _LOGGER.warning(
                    "heapBytes() unavailable — using fallback estimate for %s",
                    snap.name,
                )
                total += (snap.num_vertices * _EST_BYTES_PER_VERTEX
                          + snap.num_faces * _EST_BYTES_PER_FACE)
        return total


class UndoStack:
    """A bounded stack of :class:`HistoryEntry` snapshots.

    Two cursors:
    - ``_undo``: entries that can be undone (most recent on top).
    - ``_redo``: entries that have been undone and can be redone.

    Pushing a new entry clears the redo stack (the standard editor convention).
    """

    def __init__(
        self,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        self._undo: list[HistoryEntry] = []
        self._redo: list[HistoryEntry] = []
        self.max_depth = max_depth
        self.max_total_bytes = max_total_bytes

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def __len__(self) -> int:
        return len(self._undo)

    def total_bytes(self) -> int:
        return sum(e.estimated_bytes() for e in (*self._undo, *self._redo))

    def peek_undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    def peek_redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def push(self, entry: HistoryEntry) -> None:
        """Add a completed op's snapshot. Clears the redo stack and trims."""
        if not entry.after:
            raise ValueError("HistoryEntry.after must be populated before push()")
        self._undo.append(entry)
        self._redo.clear()
        self._trim()

    def undo(self) -> HistoryEntry | None:
        """Pop the top entry off the undo stack and return it.

        Caller is responsible for actually applying ``entry.before`` to the
        document — the stack just hands the entry back.
        """
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return entry

    def redo(self) -> HistoryEntry | None:
        """Pop the top entry off the redo stack and return it."""
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return entry

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    # ------------------------------------------------------------------
    # Bounds enforcement
    # ------------------------------------------------------------------

    def _trim(self) -> None:
        """Drop oldest undo entries until both caps are satisfied."""
        # Depth cap.
        while len(self._undo) > self.max_depth:
            self._undo.pop(0)
        # Byte cap. We only evict from the oldest end of the undo stack —
        # the redo stack is cleared on push, so it's empty here.
        while self._undo and self.total_bytes() > self.max_total_bytes:
            self._undo.pop(0)
