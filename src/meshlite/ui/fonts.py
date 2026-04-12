"""Font loading — default font + codicon glyphs merged into the same atlas.

Wired via ``runner_params.callbacks.load_additional_fonts``. The default
font (Roboto Regular + FontAwesome 6) is loaded by hello_imgui's
``imgui_default_settings`` first, then we attempt to merge codicons on top.
If the codicon TTF can't be loaded for any reason, :func:`icons.set_codicons_available`
is called with ``False`` so :func:`icons.safe` falls back to FontAwesome 6
glyphs at runtime.

Note on glyph ranges: ImGui 1.92+ uses a new font loader that doesn't
expose a per-font glyph-range filter on ``ImFontConfig``. So we just merge
the entire codicon font (~542 glyphs in U+EA60-U+F102, all icons we'd ever
want from it). Atlas overhead is negligible.
"""

from __future__ import annotations

import logging

from imgui_bundle import hello_imgui

from meshlite.utils.paths import fonts_dir

from . import icons

_LOGGER = logging.getLogger("meshlite.ui.fonts")

_CODICON_PATH = fonts_dir() / "codicon.ttf"


def load_fonts() -> None:
    """Load the default font + merge codicons.

    Set as ``runner_params.callbacks.load_additional_fonts`` so it runs
    once at startup, before the first frame builds the font atlas.
    """
    # 1. Load hello_imgui's default font (Roboto + FontAwesome 6).
    #    This is what gets rendered when no other font is selected.
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()

    # 2. Try to merge codicons into the same atlas.
    if not _CODICON_PATH.is_file():
        _LOGGER.warning(
            "codicon.ttf not found at %s — using FontAwesome fallbacks",
            _CODICON_PATH,
        )
        icons.set_codicons_available(False)
        return

    try:
        merge_params = hello_imgui.FontLoadingParams()
        merge_params.merge_to_last_font = True
        # We pass an absolute path, so set inside_assets=False; otherwise
        # hello_imgui prefixes its own assets dir.
        merge_params.inside_assets = False
        merge_params.adjust_size_to_dpi = True

        hello_imgui.load_font(str(_CODICON_PATH), 14.0, merge_params)
        icons.set_codicons_available(True)
        _LOGGER.info("merged codicons font from %s", _CODICON_PATH)
    except Exception as e:                                  # noqa: BLE001
        _LOGGER.exception("failed to load codicons: %s", e)
        icons.set_codicons_available(False)
