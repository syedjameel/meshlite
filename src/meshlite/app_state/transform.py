"""``Transform`` — TRS dataclass for ``DocumentNode``.

Translation + rotation (quaternion) + uniform scale. Cheap to clone, plays
nicely with snapshot undo. ``to_mat4()`` produces the model matrix the
renderer feeds into the shader.

This lives in ``app_state/`` rather than ``render/`` because it's part of the
document model — it survives undo/redo, gets serialized, etc. The renderer
just reads from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyglm import glm


@dataclass
class Transform:
    """Per-node TRS transform."""

    translation: glm.vec3 = field(default_factory=lambda: glm.vec3(0.0, 0.0, 0.0))
    rotation: glm.quat = field(default_factory=lambda: glm.quat(1.0, 0.0, 0.0, 0.0))
    scale: glm.vec3 = field(default_factory=lambda: glm.vec3(1.0, 1.0, 1.0))

    def to_mat4(self) -> glm.mat4:
        """Compose translation × rotation × scale into a model matrix."""
        t = glm.translate(glm.mat4(1.0), self.translation)
        r = glm.mat4_cast(self.rotation)
        s = glm.scale(glm.mat4(1.0), self.scale)
        return t * r * s

    def clone(self) -> Transform:
        return Transform(
            translation=glm.vec3(self.translation),
            rotation=glm.quat(self.rotation),
            scale=glm.vec3(self.scale),
        )

    @classmethod
    def identity(cls) -> Transform:
        return cls()
