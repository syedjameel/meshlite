"""Pure-MeshLib domain layer.

This package owns the only imports of ``meshlib.mrmeshpy`` /
``meshlib.mrmeshnumpy`` in the codebase. Everything outside ``domain/`` should
import from here, not from ``meshlib.*`` directly.
"""

from .mesh_data import MeshData
from .mesh_io import (
    SUPPORTED_LOAD_EXTENSIONS,
    SUPPORTED_SAVE_EXTENSIONS,
    UnsupportedMeshFormatError,
    load,
    save,
)

__all__ = [
    "MeshData",
    "SUPPORTED_LOAD_EXTENSIONS",
    "SUPPORTED_SAVE_EXTENSIONS",
    "UnsupportedMeshFormatError",
    "load",
    "save",
]
