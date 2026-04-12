"""``DocumentNode`` — one mesh in the document.

A node bundles a CPU-side :class:`MeshData` with its display state
(transform, visibility, name) and a slot for the parallel GPU resource
(:class:`GpuMesh`) that the renderer uploads on the main thread.

Nodes are owned by :class:`Document`. UI panels reference nodes by id, never
by direct reference, so the document is free to swap a node's underlying
mesh (when an op completes) without invalidating UI state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from meshlite.domain.mesh_data import MeshData

from .transform import Transform

if TYPE_CHECKING:
    from meshlite.domain.mesh_info import MeshInfo
    from meshlite.render.gpu_mesh import GpuMesh


def _new_node_id() -> str:
    return uuid.uuid4().hex


@dataclass
class DocumentNode:
    """One mesh in the document.

    Attributes:
        id: Stable opaque identifier (uuid4 hex).
        name: Display name (typically the source filename).
        mesh: The CPU-side mesh data.
        gpu_mesh: GPU resource bound to the mesh. ``None`` until the renderer
            uploads it on the main thread (after :class:`AppReady`, or after
            an op completes and the command bus re-uploads).
        transform: Per-node TRS transform applied at draw time.
        visible: Whether the renderer should draw this node.
        source_path: File the mesh came from, or ``None`` for generated meshes.
        info_cache: Cached :class:`MeshInfo` (populated lazily by the Mesh
            Info panel, invalidated to ``None`` on :class:`NodeMeshReplaced`).
    """

    name: str
    mesh: MeshData
    id: str = field(default_factory=_new_node_id)
    gpu_mesh: GpuMesh | None = None
    transform: Transform = field(default_factory=Transform.identity)
    visible: bool = True
    source_path: Path | None = None
    info_cache: MeshInfo | None = None
    gpu_upload_failed: bool = False
