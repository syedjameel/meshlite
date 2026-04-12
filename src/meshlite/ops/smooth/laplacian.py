"""``LaplacianSmoothOperation`` — Laplacian mesh relaxation.

Exposes the FULL ``MeshRelaxParams`` struct from meshlib. Skips only
pointer/bitset types (region, weights).
"""

# Architecture note: ops/ is allowed to import meshlib directly for complex
# Settings struct construction. See CONTRIBUTING.md for layer rules.

from __future__ import annotations

from typing import Any

import meshlib.mrmeshpy as _mrm

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
class LaplacianSmoothOperation(Operation):
    """Laplacian mesh smoothing (vertex relaxation)."""

    id = "smooth.laplacian"
    label = "Laplacian Smooth"
    category = "Mesh Edit"
    description = "Smooth the mesh by iteratively relaxing vertex positions"
    icon = "\ueb31"
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        Param("iterations", "int", "Iterations", default=3,
              min=1, max=100, step=1,
              help="Number of relaxation passes over all vertices"),
        Param("force", "float", "Force", default=0.5,
              min=0.01, max=1.0, step=0.05,
              help="Strength of each iteration (0=none, 1=full neighbor average)"),
        Param("hard_smooth_tetrahedrons", "bool", "Hard smooth tetrahedrons", default=False,
              help="Apply additional smoothing to tetrahedron-like vertex configurations"),
        Param("limit_near_initial", "bool", "Limit near initial position", default=False,
              help="Constrain smoothed vertices to stay near their original positions"),
        Param("max_initial_dist", "float", "Max initial distance", default=0.0,
              min=0.0, max=100.0, step=0.01,
              help="Maximum allowed distance from original position "
                   "(only used when 'Limit near initial' is enabled, 0 = auto)",
              visible_if=lambda v: v.get("limit_near_initial", False)),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("LaplacianSmoothOperation requires a mesh")

        mr = mesh.mr
        iterations = int(params.get("iterations", 3))
        force = float(params.get("force", 0.5))

        ctx.report_progress(0.05, "smoothing...")

        rp = _mrm.MeshRelaxParams()
        rp.iterations = iterations
        rp.force = force
        rp.hardSmoothTetrahedrons = bool(params.get("hard_smooth_tetrahedrons", False))
        rp.limitNearInitial = bool(params.get("limit_near_initial", False))
        rp.maxInitialDist = float(params.get("max_initial_dist", 0.0))

        _mrm.relax(mr, rp)

        ctx.report_progress(1.0, "done")
        return OperationResult(
            mesh=mesh,
            info={"iterations": iterations, "force": force},
            message=f"Smoothed with {iterations} iterations (force={force:.2f})",
        )
