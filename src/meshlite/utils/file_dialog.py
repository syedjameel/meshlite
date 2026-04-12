"""Native file open / save dialogs.

Wraps :mod:`imgui_bundle.portable_file_dialogs` (the bundled
``portable-file-dialogs`` C++ library) into two synchronous Python helpers.

The underlying API is asynchronous (construct, then poll ``ready()`` /
``result()``), but file dialogs are user-blocking by their nature. We just
loop on ``ready()`` with a tiny sleep so the spinner stays cheap. The whole
call returns when the dialog closes.

Both helpers run on the **main thread** and block until the user picks a
file or cancels. Don't call them from a worker — there's nothing to do
there, and you'd be racing the UI loop.
"""

from __future__ import annotations

import time
from pathlib import Path

from imgui_bundle import portable_file_dialogs as pfd

# Same set as ``domain.mesh_io.SUPPORTED_LOAD_EXTENSIONS``, but expressed as
# a (description, glob) pair list as expected by portable_file_dialogs.
_LOAD_FILTERS = [
    "Mesh files",
    "*.stl *.obj *.ply *.off *.glb *.gltf *.3mf *.dxf *.mrmesh "
    "*.STL *.OBJ *.PLY *.OFF *.GLB *.GLTF *.3MF *.DXF *.MRMESH",
    "STL", "*.stl *.STL",
    "OBJ", "*.obj *.OBJ",
    "PLY", "*.ply *.PLY",
    "All files", "*",
]

_SAVE_FILTERS = [
    "STL", "*.stl",
    "OBJ", "*.obj",
    "PLY", "*.ply",
    "OFF", "*.off",
    "GLB", "*.glb",
    "MRMesh", "*.mrmesh",
]


def _wait_for_dialog(dialog) -> None:
    """Spin until ``dialog.ready()``. Sleeps 5 ms between polls."""
    while not dialog.ready(timeout=0):
        time.sleep(0.005)


def open_mesh_dialog(*, title: str = "Open Mesh", default_path: str = "") -> Path | None:
    """Show a native file-open dialog filtered to mesh formats.

    Returns the chosen path, or ``None`` if the user canceled.
    """
    dialog = pfd.open_file(title, default_path, _LOAD_FILTERS)
    _wait_for_dialog(dialog)
    paths = dialog.result()
    if not paths:
        return None
    return Path(paths[0])


def save_mesh_dialog(
    *,
    title: str = "Save Mesh As",
    default_name: str = "mesh.stl",
) -> Path | None:
    """Show a native file-save dialog filtered to mesh formats.

    ``default_name`` is the suggested filename — typically the loaded mesh's
    name with its extension preserved.
    """
    dialog = pfd.save_file(title, default_name, _SAVE_FILTERS)
    _wait_for_dialog(dialog)
    path = dialog.result()
    if not path:
        return None
    return Path(path)
