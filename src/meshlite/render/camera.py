"""ArcballCamera with orbit, pan, and zoom.

Camera navigation matching MeshInspector's behavior:

- **Left-drag**: orbit (rotate around the scene center)
- **Right-drag**: pan (screen-space shift — does NOT change the orbit center)
- **Scroll wheel**: zoom
- **Frame All**: sets the orbit center to the mesh's bounding box center

Key design: pan is a **view-space 2D offset**, not a world-space target move.
After panning and then rotating, the object still spins around its own center
— the pan offset is applied independently in screen space. This matches how
MeshInspector, Blender, and Maya handle panning.
"""

from __future__ import annotations

from pyglm import glm

DEFAULT_ZOOM = 5.0
DEFAULT_ROTATION_X_DEG = -35.264
DEFAULT_ROTATION_Y_DEG = -45.0
DEFAULT_FOV_DEG = 45.0
DEFAULT_NEAR = 0.1
DEFAULT_FAR = 10000.0


class ArcballCamera:
    """Camera with orbit, pan (screen-space), and zoom."""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        zoom: float = DEFAULT_ZOOM,
        rotation_x_deg: float = DEFAULT_ROTATION_X_DEG,
        rotation_y_deg: float = DEFAULT_ROTATION_Y_DEG,
        fov_deg: float = DEFAULT_FOV_DEG,
        near: float = DEFAULT_NEAR,
        far: float = DEFAULT_FAR,
    ) -> None:
        self.width = width
        self.height = height
        self.zoom = zoom
        self.fov_deg = fov_deg
        self.near = near
        self.far = far

        # Orbit center — the point the camera looks at and rotates around.
        # Set by Frame All to the mesh center. NOT changed by panning.
        self.target = glm.vec3(0.0, 0.0, 0.0)

        # Pan offset — a screen-space (view-space) 2D shift applied AFTER
        # the orbit view matrix. Panning moves the rendered image on screen
        # without changing the rotation center.
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0

        rot_x = glm.angleAxis(glm.radians(rotation_x_deg), glm.vec3(1, 0, 0))
        rot_y = glm.angleAxis(glm.radians(rotation_y_deg), glm.vec3(0, 1, 0))
        self.rotation: glm.quat = rot_y * rot_x

        self._view = glm.mat4(1.0)
        self._projection = glm.mat4(1.0)
        self._view_dirty = True
        self._cached_position: glm.vec3 | None = None

        self.set_viewport(width, height)

    # ------------------------------------------------------------------
    # Viewport / projection
    # ------------------------------------------------------------------

    def set_viewport(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        aspect = width / float(height) if height > 0 else 1.0
        self._projection = glm.perspective(
            glm.radians(self.fov_deg), aspect, self.near, self.far
        )

    def get_projection_matrix(self) -> glm.mat4:
        return self._projection

    # ------------------------------------------------------------------
    # View matrix
    # ------------------------------------------------------------------

    def get_view_matrix(self) -> glm.mat4:
        if self._view_dirty:
            eye_local = glm.vec3(0, 0, self.zoom)
            up_local = glm.vec3(0, 1, 0)
            rot_mat = glm.mat4_cast(self.rotation)
            eye_world = glm.vec3(rot_mat * glm.vec4(eye_local, 1.0)) + self.target
            up_world = glm.vec3(rot_mat * glm.vec4(up_local, 0.0))

            # Base orbit view matrix — looks at the orbit center.
            orbit_view = glm.lookAt(eye_world, self.target, up_world)

            # Apply pan as a view-space translation. This shifts the rendered
            # image on screen without changing the orbit center, so rotation
            # after pan still orbits around the scene center.
            pan_mat = glm.translate(glm.mat4(1.0), glm.vec3(-self._pan_x, -self._pan_y, 0.0))
            self._view = pan_mat * orbit_view

            self._view_dirty = False
        return self._view

    @property
    def position(self) -> glm.vec3:
        """Camera eye position in world space (ignores pan — for lighting)."""
        if self._cached_position is None or self._view_dirty:
            eye_local = glm.vec3(0, 0, self.zoom)
            rot_mat = glm.mat4_cast(self.rotation)
            self._cached_position = glm.vec3(rot_mat * glm.vec4(eye_local, 1.0)) + self.target
        return self._cached_position

    def view_direction(self) -> glm.vec3:
        return glm.normalize(self.target - self.position)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set_zoom(self, zoom: float) -> None:
        if self.zoom != zoom:
            self.zoom = zoom
            self._view_dirty = True
            self._cached_position = None

    def set_rotation(self, rotation: glm.quat) -> None:
        self.rotation = rotation
        self._view_dirty = True
        self._cached_position = None

    def set_target(self, target: glm.vec3) -> None:
        """Set the orbit center (used by Frame All). Resets pan."""
        self.target = target
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._view_dirty = True
        self._cached_position = None

    def pan(self, dx_pixels: float, dy_pixels: float) -> None:
        """Pan by a screen-space delta (in pixels).

        Moves the rendered image on screen without changing the orbit center.
        The pan amount is scaled by zoom so it feels consistent at any distance.
        """
        # Convert pixel delta to view-space units. The scale factor is
        # proportional to zoom so panning feels the same speed regardless
        # of how far away the camera is.
        scale = self.zoom * 0.001
        self._pan_x -= dx_pixels * scale
        self._pan_y += dy_pixels * scale
        self._view_dirty = True

    def reset(self, target: glm.vec3 | None = None, zoom: float | None = None) -> None:
        """Reset camera to default orientation. Clears pan."""
        rot_x = glm.angleAxis(glm.radians(DEFAULT_ROTATION_X_DEG), glm.vec3(1, 0, 0))
        rot_y = glm.angleAxis(glm.radians(DEFAULT_ROTATION_Y_DEG), glm.vec3(0, 1, 0))
        self.rotation = rot_y * rot_x
        self.target = target if target is not None else glm.vec3(0, 0, 0)
        self.zoom = zoom if zoom is not None else DEFAULT_ZOOM
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._view_dirty = True
        self._cached_position = None

    def invalidate_cache(self) -> None:
        self._view_dirty = True
        self._cached_position = None

    # ------------------------------------------------------------------
    # Picking
    # ------------------------------------------------------------------

    def screen_ray(self, x: float, y: float, width: int, height: int) -> glm.vec3:
        """Direction of a ray from the camera through screen point ``(x, y)``."""
        view = self.get_view_matrix()
        proj = self.get_projection_matrix()
        viewport = glm.vec4(0, 0, width, height)
        p0 = glm.unProject(glm.vec3(x, height - y, 0.0), view, proj, viewport)
        p1 = glm.unProject(glm.vec3(x, height - y, 1.0), view, proj, viewport)
        return glm.normalize(p1 - p0)
