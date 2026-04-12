"""``SaveMeshOperation`` — write a document node's mesh to disk.

Read-only with respect to the document model: it neither replaces the node's
mesh nor adds a new one. ``undoable=False``, ``creates_node=False``,
``in_place=False``. The op exists for the same reason as
:class:`LoadMeshOperation`: so that saving routes through the same dispatch
+ progress + event pipeline as everything else.

The destination path is passed via ``params["path"]``. M5's File → Save
Mesh As menu fills it from a ``portable_file_dialogs`` save dialog.
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
class SaveMeshOperation(Operation):
    """Save a mesh to disk. Format inferred from extension."""

    id = "io.save_mesh"
    label = "Save Mesh As..."
    category = "File"
    description = "Save the active mesh to disk (STL / OBJ / PLY / GLB / OFF)"
    icon = "\ueb4a"                              # codicon-save-as
    requires = "one_mesh"
    creates_node = False
    undoable = False
    schema = ParamSchema(
        (
            Param(
                name="path",
                kind="path",
                label="Destination",
                default="",
                help="Where to write the mesh. Format is inferred from extension.",
            ),
        )
    )

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        if mesh is None:
            raise OperationError("SaveMeshOperation requires a target mesh")

        path_str = params.get("path") or ""
        if not path_str:
            raise OperationError("no path provided to SaveMeshOperation")

        path = Path(path_str)
        ctx.report_progress(0.1, f"writing {path.name}...")

        try:
            written = mesh_io.save(mesh, path)
        except mesh_io.UnsupportedMeshFormatError as e:
            raise OperationError(str(e)) from e

        ctx.report_progress(1.0, f"wrote {written.name}")
        size = written.stat().st_size if written.exists() else 0
        return OperationResult(
            mesh=None,                                # save doesn't change the doc
            info={"path": str(written), "bytes": size},
            message=f"Saved to {written} ({size:,} bytes)",
        )
