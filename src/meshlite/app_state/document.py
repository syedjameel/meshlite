"""``Document`` — the live app state: an ordered map of :class:`DocumentNode`.

The Document owns all loaded meshes and is the only place that mutates the
node list. UI panels read from it via accessors and react to events emitted
on changes — they never poke at the dict directly.

Operations mutate the document **only** via :class:`CommandBus`, which calls
:meth:`replace_mesh` on the main thread (so the GL re-upload triggered by
the ``NodeMeshReplaced`` event is safe).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path

from meshlite.domain.mesh_data import MeshData

from .events import EventBus, NodeAdded, NodeMeshReplaced, NodeRemoved
from .node import DocumentNode


class Document:
    """The live mesh document — an ordered collection of :class:`DocumentNode`."""

    def __init__(self, events: EventBus) -> None:
        self._nodes: OrderedDict[str, DocumentNode] = OrderedDict()
        self._events = events

    # ------------------------------------------------------------------
    # Add / remove
    # ------------------------------------------------------------------

    def add_node(
        self,
        mesh: MeshData,
        name: str,
        *,
        source_path: Path | None = None,
    ) -> str:
        """Add a new node and return its id.

        Emits :class:`NodeAdded` after insertion.
        """
        node = DocumentNode(name=name, mesh=mesh, source_path=source_path)
        self._nodes[node.id] = node
        self._events.emit(NodeAdded(node_id=node.id))
        return node.id

    def remove_node(self, node_id: str) -> bool:
        """Remove a node by id. Returns whether anything was removed.

        Emits :class:`NodeRemoved` after removal.
        """
        node = self._nodes.pop(node_id, None)
        if node is None:
            return False
        # Release the GPU resource if present (safe because remove_node is
        # always called on the main thread).
        if node.gpu_mesh is not None:
            node.gpu_mesh.release()
            node.gpu_mesh = None
        self._events.emit(NodeRemoved(node_id=node_id))
        return True

    def clear(self) -> None:
        """Remove every node. Emits one ``NodeRemoved`` per node."""
        for node_id in list(self._nodes.keys()):
            self.remove_node(node_id)

    # ------------------------------------------------------------------
    # Mesh replacement (the path used by completed operations)
    # ------------------------------------------------------------------

    def replace_mesh(self, node_id: str, new_mesh: MeshData) -> None:
        """Swap a node's mesh data. Emits :class:`NodeMeshReplaced`.

        Listeners (renderer GPU cache, info cache) re-upload / invalidate
        their entries in response to the event. The actual GPU re-upload is
        handled by the UI/render layer in its event handler — Document does
        not touch GL itself.
        """
        node = self._nodes.get(node_id)
        if node is None:
            raise KeyError(f"unknown node id: {node_id}")
        node.mesh = new_mesh
        node.info_cache = None
        self._events.emit(NodeMeshReplaced(node_id=node_id))

    # ------------------------------------------------------------------
    # Read accessors
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> DocumentNode | None:
        return self._nodes.get(node_id)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self) -> Iterator[DocumentNode]:
        return iter(self._nodes.values())

    def all_nodes(self) -> list[DocumentNode]:
        return list(self._nodes.values())

    def visible_nodes(self) -> list[DocumentNode]:
        return [n for n in self._nodes.values() if n.visible]

    def node_ids(self) -> list[str]:
        return list(self._nodes.keys())
