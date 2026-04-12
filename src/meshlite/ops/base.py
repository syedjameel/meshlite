"""Operation contract.

Defines the surface every meshlite mesh operation conforms to. Used by
:class:`CommandBus` to dispatch ops to workers, and by the future Properties
panel (M8) to auto-render parameter widgets from a declarative schema.

History:

- **M4** introduced the bare ``Operation`` class with ``id``, ``label``,
  ``undoable``, and ``run``, plus :class:`OperationContext`,
  :class:`OperationResult`, and the exception types.
- **M5 (this iteration)** adds :class:`Param`, :class:`ParamSchema`, and the
  full set of class-level metadata: ``category``, ``icon``, ``description``,
  ``schema``, ``requires``, ``in_place``, ``creates_node``. None of these
  are required to define an operation — every field has a sensible default
  so the M4 :class:`CounterOp` continues to work unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from meshlite.domain.mesh_data import MeshData

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# IEEE 754 float32 max — used by meshlib Settings structs as "unlimited".
# Defined once here to avoid repeating the 19-digit literal in every op.
FLT_MAX = 3.4028234663852886e+38

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OperationError(Exception):
    """Generic op failure. Operations may raise this with a user-readable msg."""


class OperationCanceled(Exception):
    """Raised by an op when it observes ``ctx.is_canceled()`` and unwinds."""


# ---------------------------------------------------------------------------
# Param + ParamSchema (M5)
# ---------------------------------------------------------------------------

ParamKind = Literal["float", "int", "bool", "enum", "path", "vec3", "range", "string", "node_picker"]
"""Discrete kinds the auto-rendering Properties panel knows how to draw."""


@dataclass(frozen=True)
class Param:
    """One declarative parameter on an :class:`Operation`'s schema.

    Subclassing ``frozen`` because Params are class-level constants — they
    must not be mutated by per-instance code.

    Attributes:
        name: Python identifier for this param. Becomes the key in the
            ``params`` dict passed to :meth:`Operation.run`.
        kind: One of :data:`ParamKind`. Drives which ImGui widget the
            Properties panel renders in M8.
        label: Human-readable label shown in the UI.
        default: Default value. Used by :meth:`ParamSchema.defaults`.
        help: Tooltip text shown next to the widget.
        min, max: Numeric bounds (only for ``float`` / ``int`` / ``range``).
        step: Slider step (numeric kinds only).
        choices: Enum values (``enum`` kind only). The widget renders these
            as a combo box; the active value is one of the strings.
        visible_if: Optional predicate ``(values: dict) -> bool``. If False
            the widget is hidden — useful for hiding params that don't apply
            in the current configuration (e.g. "min hole size" when
            "Fill all holes" is unchecked).
    """

    name: str
    kind: ParamKind
    label: str
    default: Any
    help: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple[str, ...] | None = None
    visible_if: Callable[[dict[str, Any]], bool] | None = None


@dataclass(frozen=True)
class ParamSchema:
    """A frozen tuple of :class:`Param`s.

    Used both as the contract for what an op's params dict looks like and
    as the source of truth for the Properties panel's widget rendering.
    """

    params: tuple[Param, ...] = ()

    def __iter__(self):
        return iter(self.params)

    def __len__(self) -> int:
        return len(self.params)

    def by_name(self, name: str) -> Param | None:
        for p in self.params:
            if p.name == name:
                return p
        return None

    def defaults(self) -> dict[str, Any]:
        """Return a fresh dict mapping each param name to its default."""
        return {p.name: p.default for p in self.params}

    def validate(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate ``values`` against the schema, returning a normalized dict.

        - Missing keys are filled in from defaults.
        - Unknown keys raise :class:`ValueError`.
        - Numeric values out of ``[min, max]`` raise :class:`ValueError`.
        - Enum values not in ``choices`` raise :class:`ValueError`.

        The returned dict is a fresh copy — caller is free to mutate it.
        """
        out = self.defaults()
        for k, v in values.items():
            p = self.by_name(k)
            if p is None:
                raise ValueError(f"unknown param: {k!r}")
            if p.kind in ("float", "int") and v is not None:
                if p.min is not None and v < p.min:
                    raise ValueError(f"param {k!r}={v} below min {p.min}")
                if p.max is not None and v > p.max:
                    raise ValueError(f"param {k!r}={v} above max {p.max}")
            if p.kind == "enum" and p.choices is not None and v not in p.choices:
                raise ValueError(
                    f"param {k!r}={v!r} not in choices {p.choices!r}"
                )
            out[k] = v
        return out


# ---------------------------------------------------------------------------
# Worker-side context — what op.run() can call into
# ---------------------------------------------------------------------------


@dataclass
class OperationContext:
    """Worker-thread side-channel for progress + cancellation."""

    report_progress: Callable[[float, str], None]
    is_canceled: Callable[[], bool]
    op_id: str = ""


# ---------------------------------------------------------------------------
# Op result
# ---------------------------------------------------------------------------


@dataclass
class OperationResult:
    """Return value from :meth:`Operation.run`.

    Attributes:
        mesh: For mesh-mutating ops: the new mesh that should replace the
            target node's mesh (when ``creates_node=False``) or be added as a
            new node (when ``creates_node=True``). For read-only or debug ops:
            ``None``.
        info: Optional side-channel data (e.g. ``{"filled": 7}``). Forwarded
            into the :class:`OpCompleted` event.
        message: One-line status message logged to the console.
    """

    mesh: MeshData | None = None
    info: dict = field(default_factory=dict)
    message: str = ""


# ---------------------------------------------------------------------------
# Operation base class
# ---------------------------------------------------------------------------

Requires = Literal["none", "one_mesh", "many_meshes"]


def validate_mesh(mesh: MeshData | None, op_name: str) -> MeshData:
    """Validate an op's input mesh. Raises :class:`OperationError` if invalid.

    Call at the top of every op's ``run()`` that requires a mesh.
    """
    if mesh is None:
        raise OperationError(f"{op_name} requires a target mesh")
    if mesh.num_vertices == 0:
        raise OperationError(f"{op_name}: mesh has no vertices")
    if mesh.num_faces == 0:
        raise OperationError(f"{op_name}: mesh has no faces")
    return mesh


class Operation:
    """The contract every meshlite operation must conform to.

    Subclasses override the class-level metadata they care about and
    implement :meth:`run`. Every metadata field has a default — only ``id``,
    ``label``, and ``run`` are strictly required.

    Class-level metadata:

        id: Unique stable identifier (e.g. ``"repair.fill_holes"``). Used by
            the registry, the command palette, and event payloads.
        label: Human-readable name shown in menus / palette / properties.
        category: Group name for the sidebar Operations browser.
        icon: Codicon code-point shown next to the label (M11 polish).
        description: One-line description shown in tooltips and the palette.
        schema: Declarative parameter list. Properties panel auto-renders
            this in M8.
        requires: Selection requirement: ``"none"`` for ops that don't need
            a target (file open, debug ops), ``"one_mesh"`` for most mesh
            ops, ``"many_meshes"`` for boolean / merge ops.
        in_place: Whether the op mutates its input mesh in place (``True``)
            or returns a new mesh (``False``, the default).
        creates_node: Whether the op produces a *new* document node rather
            than replacing an existing one. ``True`` for file loads.
        undoable: Whether the command bus should snapshot before dispatch.
            ``False`` for ops that don't change the mesh (debug, save, info).
    """

    id: ClassVar[str]
    label: ClassVar[str]
    category: ClassVar[str] = "General"
    icon: ClassVar[str] = ""
    description: ClassVar[str] = ""
    schema: ClassVar[ParamSchema] = ParamSchema()
    requires: ClassVar[Requires] = "one_mesh"
    in_place: ClassVar[bool] = False
    creates_node: ClassVar[bool] = False
    undoable: ClassVar[bool] = True

    def run(
        self,
        mesh: MeshData | None,
        params: dict[str, Any],
        ctx: OperationContext,
    ) -> OperationResult:
        """Execute the op on a worker thread.

        Args:
            mesh: A clone of the target node's mesh, or ``None`` for ops
                with ``requires="none"`` (e.g. file load, debug ops). The
                clone is the worker's to mutate freely — it is never the
                live mesh in the document.
            params: Op-specific parameters. The command bus validates these
                against ``self.schema`` before invocation.
            ctx: Worker-side progress + cancel hooks.

        Returns:
            An :class:`OperationResult` describing what changed.

        Raises:
            OperationCanceled: If ``ctx.is_canceled()`` returns True.
            OperationError: For user-facing failures.
        """
        raise NotImplementedError
