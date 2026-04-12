"""App state layer — Document, CommandBus, UndoStack, EventBus, TaskRunner.

No GL, no ImGui. Owns the live mesh document and the dispatch logic that
glues UI invocations to worker-thread operations.
"""

# Re-exported from domain/ so the UI layer can access mesh info
# without violating the "UI must not import domain directly" rule.
from meshlite.domain.mesh_info import MeshInfo
from meshlite.domain.mesh_info import compute as compute_mesh_info

from .command_bus import ActiveOp, CommandBus
from .document import Document
from .events import (
    AppReady,
    EventBus,
    NodeAdded,
    NodeMeshReplaced,
    NodeRemoved,
    OpCanceled,
    OpCompleted,
    OpFailed,
    OpProgress,
    OpStarted,
    SelectionChanged,
)
from .history import HistoryEntry, UndoStack
from .preferences import Preferences
from .node import DocumentNode
from .selection_model import SelectionModel
from .task_runner import TaskRunner
from .transform import Transform

__all__ = [
    "ActiveOp",
    "AppReady",
    "CommandBus",
    "Document",
    "DocumentNode",
    "EventBus",
    "HistoryEntry",
    "NodeAdded",
    "NodeMeshReplaced",
    "NodeRemoved",
    "OpCanceled",
    "OpCompleted",
    "OpFailed",
    "OpProgress",
    "OpStarted",
    "SelectionChanged",
    "SelectionModel",
    "TaskRunner",
    "Transform",
    "UndoStack",
    "MeshInfo",
    "Preferences",
    "compute_mesh_info",
]
