"""``Renderer`` — owns the moderngl context, FBO, shader program, and axes.

Ported from the existing project's ``core/renderer.py`` with two changes:

1. **Decoupled from a Scene class.** Where the old renderer took a ``Scene``
   object and iterated its meshes, this one takes a list of
   ``RenderItem`` (one per drawable: ``GpuMesh`` + model matrix + color).
   The Document/Scene model lives in ``app_state/`` and is wired up in M4.

2. **Decoupled from trimesh.** The old renderer's axis arrows came from a
   trimesh helper. We now use ``render.axes.build_axes`` which goes through
   ``mrmeshpy.makeArrow``.

Construction is deferred until ``post_init`` (when hello_imgui has created
the GL context). The renderer asserts moderngl can find a current context
on construction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import moderngl
from pyglm import glm

from .axes import AxisArrow, build_axes, release_axes
from .camera import ArcballCamera
from .gpu_mesh import GpuMesh
from .shader_loader import load_mesh_program

DEFAULT_BACKGROUND = (0.117, 0.117, 0.137, 1.0)        # near-black, slight blue tint
DEFAULT_MESH_COLOR = (0.6, 0.6, 0.65)               # light clay gray (MeshInspector-like)
SELECTED_MESH_COLOR = (0.35, 0.55, 0.80)             # selection blue
AXIS_SCALE_MULTIPLIER = 1.25


@dataclass
class RenderItem:
    """One drawable in a frame: a GPU mesh + a model matrix + a color."""

    gpu_mesh: GpuMesh
    model: glm.mat4 = field(default_factory=lambda: glm.mat4(1.0))
    color: tuple[float, float, float] = DEFAULT_MESH_COLOR
    selected: bool = False
    selected_color: tuple[float, float, float] = SELECTED_MESH_COLOR


@dataclass
class ViewOptions:
    """Per-frame view toggles. The Document layer (M4) will own these."""

    wireframe: bool = False
    show_axes: bool = True
    background: tuple[float, float, float, float] = DEFAULT_BACKGROUND

    # Lighting params — sent to the shader each frame. Matching the reference meshviewer.
    ambient_strength: float = 0.35
    specular_strength: float = 0.6
    specular_exponent: float = 64.0


class Renderer:
    """OpenGL renderer for meshlite.

    Owns:
        * the moderngl ``Context`` (acquired from the current GL context)
        * the framebuffer + color/depth textures used as the viewport target
        * the mesh shader program
        * the axis-arrow GPU meshes
    """

    def __init__(self, width: int, height: int) -> None:
        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.CULL_FACE)

        self.prog = load_mesh_program(self.ctx)
        self.axes: list[AxisArrow] = build_axes(self.ctx, self.prog)

        self.fbo: moderngl.Framebuffer | None = None
        self.color_texture: moderngl.Texture | None = None
        self.depth_texture: moderngl.Texture | None = None
        self.resize(width, height)

    # ------------------------------------------------------------------
    # Framebuffer lifecycle
    # ------------------------------------------------------------------

    def resize(self, width: int, height: int) -> None:
        width = max(1, int(width))
        height = max(1, int(height))

        if self.fbo is not None:
            self.fbo.release()
            self.color_texture.release()
            self.depth_texture.release()

        self.color_texture = self.ctx.texture((width, height), 4)
        self.depth_texture = self.ctx.depth_texture((width, height))
        self.fbo = self.ctx.framebuffer(
            color_attachments=[self.color_texture],
            depth_attachment=self.depth_texture,
        )

    @property
    def texture_glo(self) -> int:
        """The GL texture handle to pass to ``imgui.image``."""
        return self.color_texture.glo

    # ------------------------------------------------------------------
    # Frame
    # ------------------------------------------------------------------

    def render(
        self,
        items: Iterable[RenderItem],
        camera: ArcballCamera,
        view: ViewOptions,
        *,
        scene_scale: float = 1.0,
    ) -> None:
        """Render one frame's worth of items into the FBO.

        Args:
            items: Drawables for this frame.
            camera: Provides view + projection matrices.
            view: Per-frame toggles (wireframe, axes, background).
            scene_scale: Used to scale the axis arrows so they remain
                visible relative to the loaded mesh's bounding box.
        """
        assert self.fbo is not None
        self.fbo.use()
        self.ctx.clear(*view.background)

        view_mat = camera.get_view_matrix()
        proj_mat = camera.get_projection_matrix()
        self.prog["view"].write(view_mat)
        self.prog["projection"].write(proj_mat)
        cam_pos = tuple(camera.position)
        self.prog["light_pos"].value = cam_pos
        self.prog["view_pos"].value = cam_pos

        # Configurable lighting params (MeshInspector-style)
        self.prog["ambient_strength"].value = view.ambient_strength
        self.prog["specular_strength"].value = view.specular_strength
        self.prog["specular_exponent"].value = view.specular_exponent

        if view.wireframe:
            self.ctx.wireframe = True
        try:
            for item in items:
                color = item.selected_color if item.selected else item.color
                self._draw_one(item.gpu_mesh, item.model, color)
        finally:
            self.ctx.wireframe = False

        if view.show_axes:
            arrow_scale = scene_scale * AXIS_SCALE_MULTIPLIER
            scale_mat = glm.scale(glm.mat4(1.0), glm.vec3(arrow_scale))
            for axis in self.axes:
                self._draw_one(
                    axis.gpu_mesh,
                    scale_mat * axis.transform,
                    axis.color,
                )

        # Restore the default framebuffer so anything drawing after this
        # (e.g. ImGui) targets the screen, not our offscreen FBO.
        self.ctx.screen.use()

    def _draw_one(
        self,
        gpu_mesh: GpuMesh,
        model: glm.mat4,
        color: tuple[float, float, float],
    ) -> None:
        self.prog["model"].write(model)
        normal_mat = glm.mat3(glm.transpose(glm.inverse(model)))
        self.prog["normal_matrix"].write(normal_mat)
        gpu_mesh.render(color)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def release(self) -> None:
        """Free GPU resources owned by the renderer."""
        release_axes(self.axes)
        self.axes = []
        if self.prog is not None:
            self.prog.release()
            self.prog = None
        if self.fbo is not None:
            self.fbo.release()
            self.fbo = None
        if self.color_texture is not None:
            self.color_texture.release()
            self.color_texture = None
        if self.depth_texture is not None:
            self.depth_texture.release()
            self.depth_texture = None
