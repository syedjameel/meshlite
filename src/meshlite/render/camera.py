"""Production-grade arcball camera for mesh inspection.

## Design

Three independent state components:

- **``target``** — the orbit pivot (world space). Rotation always pivots
  around this point. Pan does NOT move it. This is what the reference
  commercial CAD tools (Fusion 360, MeshInspector) call the "pivot point".
  It's moved only by explicit calls (``set_target``, Frame All).

- **``rotation``** — quaternion for orbit orientation. Driven by true
  arcball input (cursor → hemisphere mapping, cross-product axis).
  Gimbal-lock-immune.

- **``_pan_x`` / ``_pan_y``** — view-space 2D translation applied AFTER
  ``lookAt``. This shifts the rendered image laterally without affecting
  the pivot. Scaled by zoom and FOV so a 100-pixel drag moves the mesh
  exactly 100 pixels on screen at target depth, regardless of distance.

### Why view-space pan instead of moving target

When pan moves ``target``, rotation after pan pivots around an offscreen
world point — the mesh swings across the viewport. Users expect rotation
to pivot around the geometry they see, even after panning. View-space
pan keeps ``target`` locked to the geometry, so rotation consistently
orbits around the same pivot regardless of panning.

## Adaptive projection

``near`` and ``far`` planes are recomputed each time ``zoom`` changes:

    near = zoom * 0.01   # 1% of viewing distance
    far  = zoom * 1000   # 1000x viewing distance

Ratio is kept at 1e5 (not higher) so a 24-bit depth buffer retains
usable precision everywhere in frustum — wider ratios cause Z-fighting
and (on some drivers) aggressive far-plane clipping mid-mesh. Production
mesh viewers scale near/far with camera distance to support both tiny
features and large scenes without manual tweaking.

## Interaction

- **Left-drag** → arcball rotation (no threshold, no hover requirement
  once drag starts)
- **Right/middle-drag** → pan (view-space shift, pivot unchanged)
- **Scroll** → zoom toward cursor (re-projects cursor hit before/after
  zoom so the world point under the cursor stays under the cursor)
- **Reset/Frame All** → clears pan and sets target to visible bbox center
"""

from __future__ import annotations

import numpy as np
from pyglm import glm

DEFAULT_ZOOM = 5.0
DEFAULT_ROTATION_X_DEG = -35.264
DEFAULT_ROTATION_Y_DEG = 45.0
DEFAULT_FOV_DEG = 45.0

# Zoom range. Low enough to inspect sub-millimeter features on unit-scale
# meshes; high enough for terrain-scale scenes. Near/far scale with zoom,
# so precision stays good across this entire range.
MIN_ZOOM = 1e-4
MAX_ZOOM = 1e6

# Arcball orbit speed. 1.0 matches raw hemisphere mapping; 1.5 matches the
# orbit speed of the reference meshviewer so ports feel the same to users.
ARCBALL_SENSITIVITY = 1.5

# Cursor-ray / target-plane alignment below this dot product is treated
# as too grazing for stable re-projection — zoom_towards_cursor falls
# back to plain zoom. At FOV=45°, a cursor in the viewport corner still
# gives ~0.9; 0.3 only triggers on pathological configurations.
ZOOM_CURSOR_MIN_DENOM = 0.3


class ArcballCamera:
    """Production arcball: orbit-around-pivot, view-space pan, adaptive projection."""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        zoom: float = DEFAULT_ZOOM,
        rotation_x_deg: float = DEFAULT_ROTATION_X_DEG,
        rotation_y_deg: float = DEFAULT_ROTATION_Y_DEG,
        fov_deg: float = DEFAULT_FOV_DEG,
    ) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.zoom = float(zoom)
        self.fov_deg = float(fov_deg)

        # Orbit center (world space). Moved only by set_target / Frame All.
        self.target = glm.vec3(0.0, 0.0, 0.0)

        # View-space pan offset — applied AFTER lookAt. Does NOT move target.
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0

        rot_x = glm.angleAxis(glm.radians(rotation_x_deg), glm.vec3(1, 0, 0))
        rot_y = glm.angleAxis(glm.radians(rotation_y_deg), glm.vec3(0, 1, 0))
        self.rotation: glm.quat = rot_y * rot_x

        self._last_arcball: glm.vec3 | None = None

        self._view = glm.mat4(1.0)
        self._projection = glm.mat4(1.0)
        self._view_dirty = True
        self._cached_position: glm.vec3 | None = None

        # Near/far get set via _update_projection.
        self.near: float = 0.0
        self.far: float = 0.0
        self._update_projection()

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------

    def set_viewport(self, width: int, height: int) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self._update_projection()

    def _update_projection(self) -> None:
        """Recompute projection with adaptive near/far planes.

        Scales near/far with zoom so depth precision is preserved across
        a wide range of scene scales. Ratio is kept at 1e5 so a 24-bit
        depth buffer stays usable everywhere. Called whenever zoom,
        viewport, or fov changes.
        """
        aspect = self.width / float(self.height) if self.height > 0 else 1.0
        # near at 1% of zoom, far at 1000x zoom — ratio 1e5.
        near = max(self.zoom * 0.01, 1e-5)
        far = self.zoom * 1000.0
        if far <= near * 10.0:
            far = near * 10.0  # always give some depth range
        self.near = near
        self.far = far
        self._projection = glm.perspective(
            glm.radians(self.fov_deg), aspect, near, far
        )

    def get_projection_matrix(self) -> glm.mat4:
        return self._projection

    # ------------------------------------------------------------------
    # View matrix — lookAt with post-applied view-space pan
    # ------------------------------------------------------------------

    def get_view_matrix(self) -> glm.mat4:
        if self._view_dirty:
            eye_local = glm.vec3(0.0, 0.0, self.zoom)
            rot_mat = glm.mat4_cast(self.rotation)
            eye = glm.vec3(rot_mat * glm.vec4(eye_local, 1.0)) + self.target
            up = glm.vec3(rot_mat * glm.vec4(0.0, 1.0, 0.0, 0.0))
            base = glm.lookAt(eye, self.target, up)

            # Apply pan as a view-space translation (after lookAt). This
            # shifts the image laterally without affecting the orbit pivot.
            if self._pan_x != 0.0 or self._pan_y != 0.0:
                pan_mat = glm.translate(
                    glm.mat4(1.0),
                    glm.vec3(self._pan_x, self._pan_y, 0.0),
                )
                self._view = pan_mat * base
            else:
                self._view = base

            self._view_dirty = False
        return self._view

    @property
    def position(self) -> glm.vec3:
        """Camera eye position in world space (used for lighting)."""
        if self._cached_position is None or self._view_dirty:
            eye_local = glm.vec3(0.0, 0.0, self.zoom)
            rot_mat = glm.mat4_cast(self.rotation)
            self._cached_position = (
                glm.vec3(rot_mat * glm.vec4(eye_local, 1.0)) + self.target
            )
        return self._cached_position

    def view_direction(self) -> glm.vec3:
        """Unit vector from the eye toward the orbit center."""
        return glm.normalize(self.target - self.position)

    # ------------------------------------------------------------------
    # Arcball rotation (left-drag)
    # ------------------------------------------------------------------

    def _screen_to_arcball(self, x: float, y: float) -> glm.vec3:
        """Project a 2D viewport coord onto a 3D arcball hemisphere.

        ``(x, y)`` are viewport-local pixel coordinates (top-left origin).
        """
        px = (2.0 * x - self.width) / self.width
        py = (self.height - 2.0 * y) / self.height
        d = px * px + py * py
        if d > 1.0:
            v = glm.normalize(glm.vec3(px, py, 0.0))
        else:
            z = float(np.sqrt(1.0 - d))
            v = glm.vec3(px, py, z)
        return glm.normalize(v)

    def begin_drag(self, x: float, y: float) -> None:
        """Call on mouse-down; capture the starting arcball point."""
        self._last_arcball = self._screen_to_arcball(x, y)

    def drag(self, x: float, y: float) -> None:
        """Call each frame while the mouse is held; rotate incrementally."""
        if self._last_arcball is None:
            return

        curr = self._screen_to_arcball(x, y)
        dot = float(np.clip(glm.dot(self._last_arcball, curr), -1.0, 1.0))

        if dot < 0.999999:
            axis = glm.cross(self._last_arcball, curr)
            if glm.length(axis) > 1e-6:
                angle = float(np.arccos(dot)) * ARCBALL_SENSITIVITY
                if angle < 1e-4:
                    angle = 1e-4
                rot_quat = glm.angleAxis(-angle, glm.normalize(axis))
                self.rotation = self.rotation * rot_quat
                self._view_dirty = True
                self._cached_position = None

        self._last_arcball = curr

    def end_drag(self) -> None:
        """Call on mouse-up; clear drag state."""
        self._last_arcball = None

    # ------------------------------------------------------------------
    # Pan (view-space — does NOT move target)
    # ------------------------------------------------------------------

    def pan(self, dx_pixels: float, dy_pixels: float) -> None:
        """Shift the rendered image by ``(dx, dy)`` screen pixels.

        Implemented as a view-space 2D translation so the orbit pivot
        stays locked to the geometry. Pan scale is derived from FOV and
        zoom so one pixel of drag equals one pixel of on-screen motion
        at target depth.
        """
        # View-space units per screen pixel at target depth:
        #   screen_height_at_target = 2 * zoom * tan(fov/2)
        #   view_units_per_pixel    = screen_height_at_target / height
        tan_half_fov = glm.tan(glm.radians(self.fov_deg) * 0.5)
        scale = 2.0 * self.zoom * tan_half_fov / self.height
        self._pan_x += dx_pixels * scale
        # Flip Y: screen-y grows downward, view-y grows upward.
        self._pan_y -= dy_pixels * scale
        self._view_dirty = True

    def reset_pan(self) -> None:
        """Clear the view-space pan offset."""
        if self._pan_x != 0.0 or self._pan_y != 0.0:
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._view_dirty = True

    # ------------------------------------------------------------------
    # Zoom (scroll wheel)
    # ------------------------------------------------------------------

    def _clamp_zoom(self, z: float) -> float:
        return max(MIN_ZOOM, min(MAX_ZOOM, z))

    def zoom_delta(self, amount: float) -> None:
        """Exponential zoom by ``amount`` wheel units (10% per unit)."""
        if amount == 0.0:
            return
        self.zoom = self._clamp_zoom(self.zoom * (1.0 - amount * 0.1))
        self._update_projection()
        self._view_dirty = True
        self._cached_position = None

    def zoom_towards_cursor(self, amount: float, ray: glm.vec3) -> None:
        """Zoom such that the world point under the cursor stays under it.

        ``ray`` is a unit direction vector from the camera through the
        cursor (from :meth:`screen_ray`). The pivot (``target``) is
        adjusted so the projected cursor position doesn't drift.

        Falls back to plain zoom if the ray/plane geometry is ill-conditioned
        (cursor ray nearly parallel to the target plane, which would push
        the hit point to infinity).
        """
        if amount == 0.0:
            return

        plane_point = glm.vec3(self.target)
        plane_normal = self.view_direction()

        denom = glm.dot(ray, plane_normal)
        # Require a reasonably well-conditioned intersection. Grazing rays
        # would push the hit point toward infinity and teleport the target.
        if denom < ZOOM_CURSOR_MIN_DENOM:
            self.zoom_delta(amount)
            return

        pos_before = self.position
        t_before = glm.dot(pos_before - plane_point, plane_normal) / denom
        hit_before = pos_before - ray * t_before

        new_zoom = self._clamp_zoom(self.zoom * (1.0 - amount * 0.1))
        if new_zoom == self.zoom:
            return  # clamped; nothing to do
        self.zoom = new_zoom
        self._update_projection()
        self._view_dirty = True
        self._cached_position = None

        pos_after = self.position
        t_after = glm.dot(pos_after - plane_point, plane_normal) / denom
        hit_after = pos_after - ray * t_after

        offset = hit_before - hit_after
        # Safety: never shift target by more than the viewing distance in a
        # single step. Protects against numerical blow-up at extreme FOV
        # or viewport geometry.
        offset_len = float(glm.length(offset))
        max_offset = self.zoom
        if offset_len > max_offset:
            offset = offset * (max_offset / offset_len)

        self.target = self.target + offset
        self._view_dirty = True
        self._cached_position = None

    # ------------------------------------------------------------------
    # Setters — preserved API
    # ------------------------------------------------------------------

    def set_zoom(self, zoom: float) -> None:
        new_zoom = self._clamp_zoom(zoom)
        if self.zoom != new_zoom:
            self.zoom = new_zoom
            self._update_projection()
            self._view_dirty = True
            self._cached_position = None

    def set_rotation(self, rotation: glm.quat) -> None:
        self.rotation = rotation
        self._view_dirty = True
        self._cached_position = None

    def set_target(self, target: glm.vec3, *, reset_pan: bool = True) -> None:
        """Set the orbit pivot. By default also clears any pan offset.

        Frame All / Frame Selected should call this with ``reset_pan=True``
        so the user gets a clean, centered view.
        """
        self.target = target
        if reset_pan:
            self._pan_x = 0.0
            self._pan_y = 0.0
        self._view_dirty = True
        self._cached_position = None

    def set_target_preserve_view(self, new_target: glm.vec3) -> None:
        """Move the orbit pivot to ``new_target`` while keeping the rendered
        image identical.

        Derivation: ``view = pan(p) * lookAt(eye, t)`` is equivalent to
        ``lookAt(eye - R⁻¹·p, t - R⁻¹·p)`` where ``R`` is world→view rotation.
        To preserve the view when changing target from ``t_old`` to ``t_new``,
        we need ``p_new = p_old + R · (t_new - t_old)``.

        Used on rotate-start: snap the pivot to the mesh center without any
        visual jump, so rotation orbits around what the user actually sees.
        """
        # Degenerate meshes can yield a NaN bbox center; accepting it would
        # corrupt the view matrix permanently.
        if not (
            np.isfinite(new_target.x)
            and np.isfinite(new_target.y)
            and np.isfinite(new_target.z)
        ):
            return
        delta_world = new_target - self.target
        if float(glm.length(delta_world)) < 1e-9:
            return
        # R (world → view) for a rotation quaternion that represents local → world
        # is the transpose of glm.mat3(mat4_cast(rotation)).
        rot_mat3 = glm.mat3(glm.mat4_cast(self.rotation))
        delta_view = glm.transpose(rot_mat3) * delta_world
        self._pan_x += float(delta_view.x)
        self._pan_y += float(delta_view.y)
        self.target = new_target
        self._view_dirty = True
        self._cached_position = None

    def reset(
        self,
        target: glm.vec3 | None = None,
        zoom: float | None = None,
    ) -> None:
        """Reset to default orientation, pan, and optionally target/zoom."""
        rot_x = glm.angleAxis(glm.radians(DEFAULT_ROTATION_X_DEG), glm.vec3(1, 0, 0))
        rot_y = glm.angleAxis(glm.radians(DEFAULT_ROTATION_Y_DEG), glm.vec3(0, 1, 0))
        self.rotation = rot_y * rot_x
        self.target = target if target is not None else glm.vec3(0, 0, 0)
        self.zoom = self._clamp_zoom(zoom if zoom is not None else DEFAULT_ZOOM)
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._last_arcball = None
        self._update_projection()
        self._view_dirty = True
        self._cached_position = None

    def invalidate_cache(self) -> None:
        self._view_dirty = True
        self._cached_position = None

    # ------------------------------------------------------------------
    # Picking
    # ------------------------------------------------------------------

    def screen_ray(
        self, x: float, y: float, width: int, height: int
    ) -> glm.vec3:
        """Unit direction of a ray from the camera through viewport point (x, y)."""
        view = self.get_view_matrix()
        proj = self.get_projection_matrix()
        viewport = glm.vec4(0, 0, width, height)
        p0 = glm.unProject(glm.vec3(x, height - y, 0.0), view, proj, viewport)
        p1 = glm.unProject(glm.vec3(x, height - y, 1.0), view, proj, viewport)
        return glm.normalize(p1 - p0)
