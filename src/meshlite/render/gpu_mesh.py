"""``GpuMesh`` — a moderngl VAO/VBO/IBO bundle bound to a shader program.

Lives entirely on the main (UI/GL) thread. Constructing a ``GpuMesh`` issues
GL calls, so we assert the constructor runs on the main thread to catch the
worker-thread isolation violation early (Plan §5: "Enforced invariants").

The ``MeshData → GpuMesh`` pipeline is:

    domain.MeshData
        │
        ▼  render.gpu_upload.mesh_data_to_arrays(...)
    MeshArrays(positions, normals, indices)
        │
        ▼  GpuMesh(ctx, prog, arrays)
    GpuMesh    (VBO + IBO + VAO bound to the program)
"""

from __future__ import annotations

import threading

import moderngl
import numpy as np

from .gpu_upload import MeshArrays

# Captured at module import time. The first thread to import this module is
# treated as the main thread; ``GpuMesh.__init__`` asserts against it.
_MAIN_THREAD = threading.current_thread()


class GpuMesh:
    """GPU-side mesh: vertex buffer + index buffer + vertex array object."""

    def __init__(
        self,
        ctx: moderngl.Context,
        prog: moderngl.Program,
        arrays: MeshArrays,
    ) -> None:
        if threading.current_thread() is not _MAIN_THREAD:
            raise RuntimeError(
                "GpuMesh must be constructed on the main thread; "
                "operations should hand back MeshData and let the command bus "
                "do the GPU upload (see plan §5)."
            )

        self._ctx = ctx
        self._prog = prog
        self._index_count = int(arrays.indices.size)

        # Interleave (position, normal) for cache locality, mirroring the
        # existing project's renderer. Layout: vec3 in_position, vec3 in_normal.
        interleaved = np.column_stack((arrays.positions, arrays.normals))
        interleaved = np.ascontiguousarray(interleaved, dtype=np.float32)

        self._vbo = ctx.buffer(interleaved.tobytes())
        self._ibo = ctx.buffer(arrays.indices.tobytes())
        self._vao = ctx.vertex_array(
            prog,
            [(self._vbo, "3f 3f", "in_position", "in_normal")],
            self._ibo,
        )

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def render(self, color: tuple[float, float, float]) -> None:
        """Issue the draw call. Caller is responsible for setting matrix uniforms."""
        self._prog["object_color"].value = color
        self._vao.render()

    # ------------------------------------------------------------------
    # Lifetime
    # ------------------------------------------------------------------

    def release(self) -> None:
        """Free GPU resources. Safe to call more than once."""
        for res_name in ("_vao", "_ibo", "_vbo"):
            res = getattr(self, res_name, None)
            if res is not None:
                res.release()
                setattr(self, res_name, None)

    @property
    def index_count(self) -> int:
        return self._index_count
