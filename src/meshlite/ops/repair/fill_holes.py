"""``FillHolesOperation`` — fill all boundary holes to make a mesh watertight.

Exposes the FULL ``FillHoleParams`` struct from meshlib as a 1:1 param
mapping (except internal pointer/output types the UI can't represent).
"""

# Architecture note: ops/ is allowed to import meshlib directly for complex
# Settings struct construction. See CONTRIBUTING.md for layer rules.

from __future__ import annotations

import logging
from typing import Any

import meshlib.mrmeshpy as _mrm

from meshlite.domain.mesh_data import MeshData

from ..base import (
    Operation,
    OperationCanceled,
    OperationContext,
    OperationError,
    OperationResult,
    Param,
    ParamSchema,
)
from ..registry import register_operation

_LOGGER = logging.getLogger("meshlite.ops.repair")

_METRIC_BUILDERS = {
    "Default": lambda mesh: None,
    "Universal": lambda mesh: _mrm.getUniversalMetric(mesh),
    "Edge Length": lambda mesh: _mrm.getEdgeLengthFillMetric(mesh),
    "Circumscribed": lambda mesh: _mrm.getCircumscribedMetric(mesh),
}

def _adv(v):
    return v.get("show_advanced", False)


@register_operation
class FillHolesOperation(Operation):
    """Fill every boundary hole in a mesh to make it watertight."""

    id = "repair.fill_holes"
    label = "Fill Holes"
    category = "Repair"
    description = "Fill all boundary holes in the mesh to make it watertight"
    icon = "\ueb53"
    requires = "one_mesh"
    undoable = True
    schema = ParamSchema((
        # --- Primary params ---
        Param("metric", "enum", "Metric", default="Universal",
              choices=tuple(_METRIC_BUILDERS.keys()),
              help="Algorithm for triangulating the hole patches"),
        Param("max_polygon_subdivisions", "int", "Max polygon subdivisions",
              default=20, min=1, max=200, step=1,
              help="Maximum number of polygon subdivisions during fill"),
        Param("smooth_bd", "bool", "Smooth boundary", default=True,
              help="Smooth the boundary vertices of the filled patch"),
        # --- Advanced ---
        Param("show_advanced", "bool", "Show advanced", default=False),
        Param("make_degenerate_band", "bool", "Make degenerate band", default=False,
              visible_if=_adv,
              help="Create a degenerate band around the hole before filling — "
                   "useful for preserving sharp boundary features"),
        Param("multiple_edges_mode", "enum", "Multiple edges resolve", default="Simple",
              choices=("None", "Simple", "Strong"),
              visible_if=_adv,
              help="How to resolve multiple edges meeting at one vertex during fill. "
                   "None=ignore, Simple=basic resolution, Strong=aggressive"),
    ))

    def run(self, mesh: MeshData | None, params: dict[str, Any],
            ctx: OperationContext) -> OperationResult:
        if mesh is None:
            raise OperationError("FillHolesOperation requires a target mesh")

        mr = mesh.mr
        ctx.report_progress(0.02, "finding holes...")
        edges = mr.topology.findHoleRepresentiveEdges()
        total = len(edges)
        if total == 0:
            return OperationResult(
                mesh=mesh,
                info={"filled": 0, "holes_before": 0, "holes_after": 0},
                message="No holes found — mesh was already watertight",
            )

        # Build metric.
        metric_name = params.get("metric", "Universal")
        builder = _METRIC_BUILDERS.get(metric_name)
        if builder is None:
            raise OperationError(f"unknown metric: {metric_name!r}")
        metric_obj = builder(mr)

        fp = _mrm.FillHoleParams()
        if metric_obj is not None:
            fp.metric = metric_obj
        fp.maxPolygonSubdivisions = int(params.get("max_polygon_subdivisions", 20))
        fp.smoothBd = bool(params.get("smooth_bd", True))
        fp.makeDegenerateBand = bool(params.get("make_degenerate_band", False))

        # MultipleEdgesResolveMode mapping
        mode_str = params.get("multiple_edges_mode", "Simple")
        _MEM = _mrm.FillHoleParams.MultipleEdgesResolveMode
        mode_map = {
            "None": getattr(_MEM, "None"),   # "None" is a Python keyword; use getattr
            "Simple": _MEM.Simple,
            "Strong": _MEM.Strong,
        }
        fp.multipleEdgesResolveMode = mode_map.get(mode_str, _MEM.Simple)

        filled = 0
        for i, edge in enumerate(edges):
            if ctx.is_canceled():
                raise OperationCanceled()
            try:
                _mrm.fillHole(mr, edge, fp)
                filled += 1
            except Exception as e:
                _LOGGER.warning("fillHole failed on edge %s: %s", edge, e)
            ctx.report_progress(0.05 + 0.95 * (i + 1) / total, f"filled {i + 1}/{total} holes")

        holes_after = mr.topology.findNumHoles()
        return OperationResult(
            mesh=mesh,
            info={"filled": filled, "holes_before": total, "holes_after": holes_after,
                  "watertight": holes_after == 0},
            message=(f"Filled {filled}/{total} holes"
                     + (" — mesh is now watertight" if holes_after == 0 else f" — {holes_after} holes remain")),
        )
