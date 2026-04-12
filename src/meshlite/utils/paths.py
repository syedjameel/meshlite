"""Runtime asset path resolution.

Works in three contexts:

1. **Development / editable install:** ``python main.py`` or ``pip install -e .``
   Assets live at ``<project-root>/assets/fonts/`` and ``assets/shaders/``.

2. **Pip-installed:** ``pip install meshlite``
   Hatch's ``shared-data`` copies assets to ``<prefix>/share/meshlite/fonts/``
   and ``<prefix>/share/meshlite/shaders/`` (no ``assets/`` subdirectory).

3. **Frozen (PyInstaller):** assets are bundled under ``_MEIPASS/assets/``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def fonts_dir() -> Path:
    """Return the directory containing ``codicon.ttf``."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / "fonts"  # type: ignore[attr-defined]

    # Development: <root>/src/meshlite/utils/paths.py → <root>/assets/fonts
    dev = Path(__file__).resolve().parents[3] / "assets" / "fonts"
    if dev.is_dir():
        return dev

    # Pip-installed: <prefix>/share/meshlite/fonts
    installed = Path(sys.prefix) / "share" / "meshlite" / "fonts"
    if installed.is_dir():
        return installed

    return dev  # fallback — will trigger "not found" warnings downstream


def shaders_dir() -> Path:
    """Return the directory containing ``mesh.vert`` and ``mesh.frag``."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / "shaders"  # type: ignore[attr-defined]

    # Development
    dev = Path(__file__).resolve().parents[3] / "assets" / "shaders"
    if dev.is_dir():
        return dev

    # Pip-installed
    installed = Path(sys.prefix) / "share" / "meshlite" / "shaders"
    if installed.is_dir():
        return installed

    return dev
