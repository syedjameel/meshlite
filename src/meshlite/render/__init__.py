"""Render layer — moderngl-based GPU rendering.

Pure GPU code, never touches ImGui directly. The UI layer instantiates a
:class:`Renderer` in its post-init callback (when the GL context is live)
and calls :meth:`Renderer.render` once per frame from a viewport panel.
"""

from .camera import ArcballCamera
from .gpu_mesh import GpuMesh
from .gpu_upload import MeshArrays, mesh_data_to_arrays
from .renderer import Renderer, RenderItem, ViewOptions

__all__ = [
    "ArcballCamera",
    "GpuMesh",
    "MeshArrays",
    "RenderItem",
    "Renderer",
    "ViewOptions",
    "mesh_data_to_arrays",
]
