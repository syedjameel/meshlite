"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to ``tests/fixtures/``."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def cube_stl_path(fixtures_dir: Path) -> Path:
    """Path to the committed unit-cube STL fixture (8 verts, 12 faces)."""
    p = fixtures_dir / "cube.stl"
    assert p.exists(), f"missing fixture: {p} — regenerate via tests/fixtures/_gen.py"
    return p


@pytest.fixture(scope="session")
def open_cyl_path(fixtures_dir: Path) -> Path:
    """Path to the open cylinder STL fixture (32 verts, 32 faces, 2 holes)."""
    p = fixtures_dir / "open_cylinder.stl"
    assert p.exists(), f"missing fixture: {p}"
    return p
