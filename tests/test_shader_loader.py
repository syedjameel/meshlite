"""Shader parity test.

``shader_loader`` ships an embedded fallback shader so the app still comes
up when ``assets/shaders/`` is missing. The risk is silent drift: someone
edits ``mesh.frag`` but forgets the fallback. This test asserts both
sources declare the same uniforms so the two code paths render
consistently.
"""

from __future__ import annotations

import re

from meshlite.render import shader_loader
from meshlite.utils.paths import shaders_dir

_UNIFORM_RE = re.compile(r"uniform\s+(\w+)\s+(\w+)\s*;")


def _uniforms(source: str) -> set[tuple[str, str]]:
    return set(_UNIFORM_RE.findall(source))


def test_asset_and_fallback_agree_on_uniforms():
    frag_path = shaders_dir() / "mesh.frag"
    vert_path = shaders_dir() / "mesh.vert"

    asset_frag = frag_path.read_text()
    asset_vert = vert_path.read_text()

    assert _uniforms(asset_frag) == _uniforms(shader_loader._FALLBACK_FRAG), (
        "mesh.frag and _FALLBACK_FRAG declare different uniforms — they will "
        "render inconsistently when the fallback is used. Keep them in sync."
    )
    assert _uniforms(asset_vert) == _uniforms(shader_loader._FALLBACK_VERT), (
        "mesh.vert and _FALLBACK_VERT declare different uniforms."
    )
