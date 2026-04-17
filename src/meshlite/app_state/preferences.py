"""User preferences — persisted as JSON via hello_imgui's user pref API.

Lives in ``app_state/`` so it has zero GL / ImGui / meshlib dependencies.
All serialization uses stdlib ``json`` and ``dataclasses``.

The ``Preferences`` dataclass holds every configurable value. Consumers
(viewport, renderer, camera, history) read from the shared instance at
``app.preferences`` each frame. The UI runner loads preferences in
``post_init`` and saves them in ``before_exit``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

_LOGGER = logging.getLogger("meshlite.preferences")

RECENT_FILES_MAX = 10


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class Preferences:
    """All user-configurable settings, with defaults matching the original hardcoded values."""

    # Viewport sensitivity
    rotate_sensitivity: float = 0.005
    zoom_sensitivity: float = 0.1
    pan_sensitivity: float = 0.003

    # Camera
    fov_deg: float = 45.0

    # Renderer colors
    background_color: tuple[float, float, float, float] = (0.117, 0.117, 0.137, 1.0)
    mesh_color: tuple[float, float, float] = (0.6, 0.6, 0.65)
    selected_mesh_color: tuple[float, float, float] = (0.35, 0.55, 0.80)

    # Lighting (matches the reference meshviewer look)
    ambient_strength: float = 0.35
    specular_strength: float = 0.6
    specular_exponent: float = 64.0

    # History
    undo_max_depth: int = 20
    undo_max_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB

    # View toggles
    wireframe: bool = False
    show_axes: bool = True

    # Recent files (most recent first)
    recent_files: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> Preferences:
        """Parse JSON, ignoring unknown keys and filling missing ones from defaults."""
        try:
            raw = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning("invalid preferences JSON — using defaults")
            return cls()

        if not isinstance(raw, dict):
            return cls()

        defaults = cls()
        fields = {f.name for f in defaults.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in fields}

        # Convert lists back to tuples where needed.
        for key in ("background_color", "mesh_color", "selected_mesh_color"):
            if key in filtered and isinstance(filtered[key], list):
                filtered[key] = tuple(filtered[key])

        try:
            prefs = cls(**filtered)
        except TypeError:
            _LOGGER.warning("preferences type mismatch — using defaults")
            return cls()

        prefs._validate()
        return prefs

    @classmethod
    def defaults(cls) -> Preferences:
        return cls()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        """Clamp numeric fields to sensible ranges."""
        self.rotate_sensitivity = _clamp(self.rotate_sensitivity, 0.0001, 0.05)
        self.zoom_sensitivity = _clamp(self.zoom_sensitivity, 0.01, 0.5)
        self.pan_sensitivity = _clamp(self.pan_sensitivity, 0.0001, 0.05)
        self.fov_deg = _clamp(self.fov_deg, 10.0, 120.0)
        self.ambient_strength = _clamp(self.ambient_strength, 0.0, 1.0)
        self.specular_strength = _clamp(self.specular_strength, 0.0, 1.0)
        self.specular_exponent = _clamp(self.specular_exponent, 1.0, 128.0)
        self.undo_max_depth = max(1, min(200, self.undo_max_depth))
        self.undo_max_bytes = max(100 * 1024 * 1024, self.undo_max_bytes)  # min 100 MB
        self.recent_files = self.recent_files[:RECENT_FILES_MAX]

    # ------------------------------------------------------------------
    # Recent files
    # ------------------------------------------------------------------

    def add_recent_file(self, path: str) -> None:
        """Add path to front of recent list, deduplicating."""
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:RECENT_FILES_MAX]
