"""Mesh file I/O — load and save :class:`MeshData` to/from disk.

Thin wrappers around :func:`mrm_shim.load` / :func:`mrm_shim.save` that
attach metadata (source path, display name) and convert ``Path`` arguments
to strings (the underlying ``meshlib`` API only accepts ``str``).

Operations that load files (e.g. ``LoadMeshOperation`` in M5) call into this
module on their worker thread; the resulting ``MeshData`` is then handed
back to the main thread for GPU upload via the command bus.
"""

from __future__ import annotations

from pathlib import Path

from . import mrm_shim
from .mesh_data import MeshData

# Formats `mrmeshpy.loadMesh` accepts (verified against meshlib 3.1.1.211).
SUPPORTED_LOAD_EXTENSIONS: tuple[str, ...] = (
    ".stl",
    ".obj",
    ".ply",
    ".off",
    ".glb",
    ".gltf",
    ".3mf",
    ".dxf",
    ".mrmesh",
)

# Formats `mrmeshpy.saveMesh` writes. Subset of load formats — some loaders
# (e.g. dxf, gltf) are read-only.
SUPPORTED_SAVE_EXTENSIONS: tuple[str, ...] = (
    ".stl",
    ".obj",
    ".ply",
    ".off",
    ".glb",
    ".mrmesh",
)


class UnsupportedMeshFormatError(ValueError):
    """Raised when a file extension isn't in the supported set."""


def load(path: str | Path) -> MeshData:
    """Load a mesh file into a :class:`MeshData`.

    Args:
        path: Filesystem path. Format is inferred from the extension.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        UnsupportedMeshFormatError: If the extension isn't in
            :data:`SUPPORTED_LOAD_EXTENSIONS`.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mesh file not found: {p}")
    if p.suffix.lower() not in SUPPORTED_LOAD_EXTENSIONS:
        raise UnsupportedMeshFormatError(
            f"Cannot load {p.suffix!r}; supported: {SUPPORTED_LOAD_EXTENSIONS}"
        )
    mr = mrm_shim.load(str(p))
    return MeshData(mr=mr, name=p.name, source_path=p.resolve())


def save(mesh: MeshData, path: str | Path) -> Path:
    """Write a :class:`MeshData` to disk.

    Args:
        mesh: The mesh to save.
        path: Destination path. Format is inferred from the extension. Parent
            directories are created if missing.

    Returns:
        The resolved absolute path that was written.

    Raises:
        UnsupportedMeshFormatError: If the extension isn't in
            :data:`SUPPORTED_SAVE_EXTENSIONS`.
    """
    p = Path(path)
    if p.suffix.lower() not in SUPPORTED_SAVE_EXTENSIONS:
        raise UnsupportedMeshFormatError(
            f"Cannot save {p.suffix!r}; supported: {SUPPORTED_SAVE_EXTENSIONS}"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    mrm_shim.save(mesh.mr, str(p))
    return p.resolve()
