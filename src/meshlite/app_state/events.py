"""``EventBus`` — typed pub/sub for cross-layer notifications.

The Document, SelectionModel, CommandBus, and history stack emit events
when state changes. UI panels subscribe to events they care about so they
don't need to poll every frame and don't need direct references to the
emitters. This is the same observer pattern the existing project's
``ui_state.py`` uses, made type-safe via dataclass events.

Subscribers are stored as ``WeakSet``-style lists per event type — but
actually, plain lists are fine here because the UI runner owns the
subscribers and ties them to its own lifetime. We don't need weakrefs yet.

Usage:

    bus = EventBus()
    bus.subscribe(NodeAdded, lambda e: print("added", e.node_id))
    bus.emit(NodeAdded(node_id="abc-123"))
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

# ---------------------------------------------------------------------------
# Event dataclasses — frozen so subscribers can't accidentally mutate them.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppReady:
    """Emitted by ``MeshLiteApp.post_init`` once the GL context + renderer are live."""


@dataclass(frozen=True)
class NodeAdded:
    node_id: str


@dataclass(frozen=True)
class NodeRemoved:
    node_id: str


@dataclass(frozen=True)
class NodeMeshReplaced:
    """Mesh data on a node was swapped (e.g. after an op completed).

    Listeners that hold derived state (GPU upload cache, info cache) should
    invalidate their entry for ``node_id``.
    """

    node_id: str


@dataclass(frozen=True)
class SelectionChanged:
    primary: str | None
    selected: tuple[str, ...]


@dataclass(frozen=True)
class OpStarted:
    task_id: str
    op_id: str
    label: str


@dataclass(frozen=True)
class OpProgress:
    task_id: str
    progress: float
    message: str


@dataclass(frozen=True)
class OpCompleted:
    task_id: str
    op_id: str
    info: dict
    message: str


@dataclass(frozen=True)
class OpFailed:
    task_id: str
    op_id: str
    error: str


@dataclass(frozen=True)
class OpCanceled:
    task_id: str
    op_id: str


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------

E = TypeVar("E")
EventHandler = Callable[[Any], None]


class EventBus:
    """Synchronous typed event dispatch.

    Handlers run on the thread that calls :meth:`emit`. Since most events
    are emitted from the main thread (the CommandBus drains task results on
    the main thread before emitting OpCompleted), this is fine.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        self._subscribers[event_type].append(handler)  # type: ignore[arg-type]

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> bool:
        handlers = self._subscribers.get(event_type)
        if not handlers:
            return False
        try:
            handlers.remove(handler)  # type: ignore[arg-type]
            return True
        except ValueError:
            return False

    def emit(self, event: Any) -> None:
        """Synchronously dispatch ``event`` to all subscribers of its type."""
        for handler in list(self._subscribers.get(type(event), ())):
            handler(event)

    def clear(self) -> None:
        """Drop all subscribers. Used in tests + on shutdown."""
        self._subscribers.clear()
