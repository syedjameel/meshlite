"""``MeshData`` — the CPU-side mesh wrapper used everywhere outside ``render/``.

Wraps a ``meshlib.mrmeshpy.Mesh`` plus light metadata (a name and an optional
source path). All access to mesh statistics, cloning, and bounding boxes goes
through ``mrm_shim`` so this class never imports ``meshlib`` directly.

A ``MeshData`` instance is purely CPU-side. The render layer (M3) holds a
parallel ``GpuMesh`` per document node — they're kept in sync by the
``CommandBus`` (M4) when an operation replaces a node's mesh.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import mrm_shim
from .mrm_shim import MrMesh


@dataclass
class MeshData:
    """A MeshLib mesh + light metadata.

    Attributes:
        mr: The underlying ``mrmeshpy.Mesh`` instance.
        name: Display name (typically the source filename).
        source_path: Path the mesh was loaded from, or ``None`` for
            in-memory / generated meshes.
    """

    mr: MrMesh
    name: str
    source_path: Path | None = None

    # ------------------------------------------------------------------
    # Cloning
    # ------------------------------------------------------------------

    def clone(self) -> MeshData:
        """Return an independent deep copy.

        The underlying mesh is duplicated via ``mrm_shim.clone`` (verified to
        be a true deep copy in M2). Metadata is copied by value.
        """
        return MeshData(
            mr=mrm_shim.clone(self.mr),
            name=self.name,
            source_path=self.source_path,
        )

    # ------------------------------------------------------------------
    # Counts (delegated to mrm_shim — no direct meshlib access here)
    # ------------------------------------------------------------------

    @property
    def num_vertices(self) -> int:
        return mrm_shim.num_vertices(self.mr)

    @property
    def num_faces(self) -> int:
        return mrm_shim.num_faces(self.mr)

    @property
    def num_holes(self) -> int:
        return mrm_shim.num_holes(self.mr)

    @property
    def is_watertight(self) -> bool:
        return mrm_shim.is_watertight(self.mr)

    # ------------------------------------------------------------------
    # Geometry queries
    # ------------------------------------------------------------------

    @property
    def surface_area(self) -> float:
        return mrm_shim.surface_area(self.mr)

    @property
    def volume(self) -> float:
        return mrm_shim.volume(self.mr)

    def bounding_box(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """``((min_x, min_y, min_z), (max_x, max_y, max_z))``."""
        return mrm_shim.bounding_box(self.mr)
