"""``OperationRegistry`` — discovery and lookup for :class:`Operation` subclasses.

Adding a new operation to meshlite is a one-file change: drop a Python
module under ``meshlite/ops/<category>/`` containing a subclass decorated
with :func:`register_operation`. The next time
:meth:`OperationRegistry.discover` runs (typically once at app startup, in
:meth:`MeshLiteApp.post_init`), the module is imported and the decorator
fires, adding the class to the registry. From there it is automatically
visible to:

- the sidebar Operations browser (M6+)
- the command palette (M9)
- the Properties panel (M8) — its schema is auto-rendered
- the CommandBus (always — it dispatches by class)

The registry never instantiates an op. Callers do
``OperationRegistry.get("repair.fill_holes")()`` themselves and pass the
instance into :meth:`CommandBus.run_operation`. This makes per-op
constructor args natural.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
from collections.abc import Iterable

from .base import Operation

_LOGGER = logging.getLogger("meshlite.ops.registry")


class _OperationRegistryMeta(type):
    """Lets us use ``OperationRegistry["repair.fill_holes"]`` as syntactic sugar."""

    def __getitem__(cls, op_id: str) -> type[Operation]:
        return cls.get(op_id)        # type: ignore[attr-defined]


class OperationRegistry(metaclass=_OperationRegistryMeta):
    """Class-level registry of :class:`Operation` subclasses.

    Lookup is by ``op.id`` string. The registry is a class attribute (not
    an instance) so the ``@register_operation`` decorator can write into it
    at module import time without needing a global instance to be threaded
    around.
    """

    _ops: dict[str, type[Operation]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, op_cls: type[Operation]) -> type[Operation]:
        """Add ``op_cls`` to the registry. Idempotent for the same class."""
        if not hasattr(op_cls, "id") or not op_cls.id:
            raise ValueError(
                f"{op_cls.__name__} must define a non-empty class-level `id`"
            )
        existing = cls._ops.get(op_cls.id)
        if existing is op_cls:
            return op_cls
        if existing is not None:
            raise ValueError(
                f"duplicate operation id {op_cls.id!r}: "
                f"{existing.__module__}.{existing.__qualname__} vs "
                f"{op_cls.__module__}.{op_cls.__qualname__}"
            )
        cls._ops[op_cls.id] = op_cls
        _LOGGER.debug("registered op: %s (%s)", op_cls.id, op_cls.__name__)
        return op_cls

    @classmethod
    def unregister(cls, op_id: str) -> bool:
        """Remove an op by id. Mostly for tests — production code shouldn't."""
        return cls._ops.pop(op_id, None) is not None

    @classmethod
    def clear(cls) -> None:
        """Drop every registration. Mostly for test isolation."""
        cls._ops.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, op_id: str) -> type[Operation]:
        """Return the op class for ``op_id``. Raises :class:`KeyError` if absent."""
        try:
            return cls._ops[op_id]
        except KeyError as e:
            raise KeyError(f"unknown operation id: {op_id!r}") from e

    @classmethod
    def has(cls, op_id: str) -> bool:
        return op_id in cls._ops

    @classmethod
    def all(cls) -> list[type[Operation]]:
        """All registered op classes, sorted by id for stable iteration."""
        return [cls._ops[k] for k in sorted(cls._ops)]

    @classmethod
    def by_category(cls) -> dict[str, list[type[Operation]]]:
        """Group registered ops by their ``category`` field, sorted within each."""
        out: dict[str, list[type[Operation]]] = {}
        for op_cls in cls.all():
            out.setdefault(op_cls.category, []).append(op_cls)
        for v in out.values():
            v.sort(key=lambda c: c.label)
        return out

    @classmethod
    def __len__(cls) -> int:
        return len(cls._ops)

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    @classmethod
    def discover(cls, package: str = "meshlite.ops") -> int:
        """Walk every submodule of ``package`` and import it.

        Importing each module triggers any ``@register_operation`` decorators
        at module scope, populating the registry. Returns how many ops are in
        the registry after discovery.

        Modules whose name begins with ``_`` (e.g. ``_dev``) are skipped, so
        the debug counter op stays out of the user-facing registry unless an
        explicit ``register_operation`` decorator opts it in elsewhere.
        """
        # In a PyInstaller bundle, walk_packages can't find submodules.
        # Fall back to the explicit manifest.
        if getattr(sys, "frozen", False):
            return cls._discover_frozen()

        pkg = importlib.import_module(package)
        if not hasattr(pkg, "__path__"):
            raise TypeError(f"{package!r} is not a package")

        skip_prefix = pkg.__name__ + "."
        for _, name, _is_pkg in pkgutil.walk_packages(
            pkg.__path__, prefix=skip_prefix
        ):
            # Skip any submodule whose dotted path contains a private
            # component (e.g. ``meshlite.ops._dev.counter_op``). The
            # ``_dev`` package is for development-only ops; the registry
            # never auto-imports them.
            relative = name[len(skip_prefix):]
            if any(part.startswith("_") for part in relative.split(".")):
                continue
            try:
                mod = importlib.import_module(name)
            except Exception:                                       # noqa: BLE001
                _LOGGER.exception("failed to import op module %s", name)
                continue

            # Re-register any Operation subclasses defined in this module
            # that are missing from the registry. This handles two cases:
            #   1. First-time import: the @register_operation decorator
            #      already added the class. The "missing" check skips it.
            #   2. Re-discovery after a clear() (in tests): the module is
            #      cached in sys.modules, so the decorator does NOT re-fire.
            #      We walk the module dict and re-register here.
            for _, member in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(member, Operation)
                    and member is not Operation
                    and getattr(member, "__module__", None) == name
                    and getattr(member, "id", None)
                    and not cls.has(member.id)
                ):
                    try:
                        cls.register(member)
                    except Exception:                                # noqa: BLE001
                        _LOGGER.exception("failed to register %s", member)

        _LOGGER.info(
            "operation registry: %d op(s) registered after discover()",
            len(cls._ops),
        )
        return len(cls._ops)


    @classmethod
    def _discover_frozen(cls) -> int:
        """Import ops from the manifest when running in a PyInstaller bundle."""
        from meshlite.ops._manifest import ALL_OP_MODULES

        for name in ALL_OP_MODULES:
            try:
                importlib.import_module(name)
            except Exception:                                        # noqa: BLE001
                _LOGGER.exception("failed to import op module %s", name)
        _LOGGER.info(
            "operation registry (frozen): %d op(s) registered",
            len(cls._ops),
        )
        return len(cls._ops)


# ---------------------------------------------------------------------------
# Decorator sugar
# ---------------------------------------------------------------------------


def register_operation(op_cls: type[Operation]) -> type[Operation]:
    """Class decorator that registers an op with :class:`OperationRegistry`.

    Usage::

        @register_operation
        class FillHolesOperation(Operation):
            id = "repair.fill_holes"
            label = "Fill Holes"
            ...
    """
    return OperationRegistry.register(op_cls)


def iter_registered() -> Iterable[type[Operation]]:
    """Convenience iterator over all registered op classes."""
    return iter(OperationRegistry.all())
