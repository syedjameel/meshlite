"""Runtime asset path resolution.

Works in three contexts:
1. **Development:** running from the source tree (``python main.py``)
2. **Installed:** pip-installed into a virtualenv
3. **Frozen:** PyInstaller one-folder or one-file bundle

In all cases the ``assets/`` directory contains ``fonts/codicon.ttf``
and ``shaders/mesh.{vert,frag}``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    """Return the project root (the directory containing ``assets/``)."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle: assets are in _MEIPASS.
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Development / installed: this file is at <root>/src/meshlite/utils/paths.py
    return Path(__file__).resolve().parents[3]


def asset_dir() -> Path:
    return _project_root() / "assets"


def fonts_dir() -> Path:
    return asset_dir() / "fonts"


def shaders_dir() -> Path:
    return asset_dir() / "shaders"
