"""Operations layer.

Public surface:

- :class:`Operation` — base class every op subclasses
- :class:`Param`, :class:`ParamSchema` — declarative parameter schemas
- :class:`OperationContext`, :class:`OperationResult` — worker-side
  helpers and return value
- :class:`OperationError`, :class:`OperationCanceled` — exceptions
- :class:`OperationRegistry`, :func:`register_operation` — discovery + lookup

Auto-discovery: call :meth:`OperationRegistry.discover` once at app startup
(handled by :meth:`MeshLiteApp.post_init`). It walks every submodule under
``meshlite.ops`` and imports them, triggering ``@register_operation``
decorators at module scope.
"""

from .base import (
    Operation,
    OperationCanceled,
    OperationContext,
    OperationError,
    OperationResult,
    Param,
    ParamKind,
    ParamSchema,
    Requires,
)
from .registry import OperationRegistry, iter_registered, register_operation

__all__ = [
    "Operation",
    "OperationCanceled",
    "OperationContext",
    "OperationError",
    "OperationRegistry",
    "OperationResult",
    "Param",
    "ParamKind",
    "ParamSchema",
    "Requires",
    "iter_registered",
    "register_operation",
]
