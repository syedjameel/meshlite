"""``LoadMeshOperation`` — load a mesh file into a new document node.

This is the first real operation in meshlite. It does very little — most
of the work lives in :func:`meshlite.domain.mesh_io.load`. The op exists
so that loading goes through the same pipeline as every other op:

- Dispatched via :class:`CommandBus.run_operation` (file dialog runs on the
  main thread; the actual decode happens on a worker)
- Reports progress via :class:`OperationContext`
- Result is a brand-new :class:`MeshData` that the bus installs as a new
  :class:`DocumentNode` (via ``creates_node=True``)
- Logged + emitted as ``OpStarted`` / ``OpCompleted`` events

The path is passed via ``params["path"]``. M5's File menu fills it from a
``portable_file_dialogs`` open dialog. M9's command palette will use the
same code path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meshlite.domain import mesh_io
from meshlite.domain.mesh_data import MeshData

from ..base import (
    Operation,
    OperationContext,
    OperationError,
    OperationResult,
    Param,
    ParamSchema,
)
from ..registry import register_operation


@register_operation
class LoadMeshOperation(Operation):
    """Load a mesh file as a new node in the document."""

    id = "io.load_mesh"
    label = "Open Mesh"
    category = "File"
    description = "Load an STL / OBJ / PLY / GLB / OFF / 3MF mesh into the scene"
    icon = "\ueaf7"                              # codicon-folder-opened
    requires = "none"
    creates_node = True
    undoable = False
    schema = ParamSchema(
        (
            Param(
                name="path",
                kind="path",
                label="File",
                default="",
                help="Mesh file to load",
            ),
        )
    )

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        path_str = params.get("path") or ""
        if not path_str:
            raise OperationError("no path provided to LoadMeshOperation")

        path = Path(path_str)
        ctx.report_progress(0.05, f"opening {path.name}...")

        try:
            loaded = mesh_io.load(path)
        except FileNotFoundError as e:
            raise OperationError(str(e)) from e
        except mesh_io.UnsupportedMeshFormatError as e:
            raise OperationError(str(e)) from e

        if ctx.is_canceled():
            from ..base import OperationCanceled
            raise OperationCanceled()

        ctx.report_progress(1.0, f"loaded {path.name}")
        return OperationResult(
            mesh=loaded,
            info={
                "path": str(path),
                "vertices": loaded.num_vertices,
                "faces": loaded.num_faces,
                "watertight": loaded.is_watertight,
                "holes": loaded.num_holes,
            },
            message=f"Loaded {loaded.name} ({loaded.num_vertices} verts, {loaded.num_faces} faces)",
        )
