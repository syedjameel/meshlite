"""Codicon code-points used by meshlite UI.

Constants reference glyphs in Microsoft's `vscode-codicons` font (vendored
at ``assets/fonts/codicon.ttf``, CC BY 4.0). The font's PUA range is
``U+EA60 → U+F102`` (542 glyphs total in the published TTF, verified by
parsing the cmap directly during M6).

Each constant is a single-character string. Use them like:

    if imgui.button(f"{icons.SAVE} Save"):
        ...

The :func:`safe` helper returns the codicon glyph if codicons loaded, else
the FontAwesome 6 fallback. M6 calls :func:`set_codicons_available` once at
font load time so :func:`safe` knows which atlas is live.

Code points are taken from the codicon SVG sources at
https://github.com/microsoft/vscode-codicons/tree/main/src/icons —
verified by inspecting the published TTF.
"""

from __future__ import annotations

from imgui_bundle import icons_fontawesome_6 as fa

# ---------------------------------------------------------------------------
# Codicon glyphs we use. Code-points come from the codicon-1.15 PUA block.
# Only the dozen or so we actually reference — the full font has ~600 icons.
# ---------------------------------------------------------------------------

# All code-points verified by parsing the codicon TTF post + cmap tables in M6.5.
# Several M6 entries had wrong code-points (rendered as some other glyph) — fixed here.

# File / IO
FILE_OPEN = "\ueaf7"           # codicon-folder-opened
FILE = "\ueb60"                # codicon-file
SAVE = "\ueb4b"                # codicon-save
SAVE_AS = "\ueb4a"             # codicon-save-as
NEW_FILE = "\uea7f"            # codicon-new-file
TRASH = "\uea81"               # codicon-trash
CLEAR_ALL = "\ueabf"           # codicon-clear-all
REFRESH = "\ueb37"             # codicon-refresh

# Sidebar mode buttons
LIST_TREE = "\ueb86"           # codicon-list-tree
SEARCH = "\uea6d"              # codicon-search
TOOLS = "\ueb6d"               # codicon-tools
SETTINGS_GEAR = "\ueb51"       # codicon-settings-gear
HISTORY = "\uea82"             # codicon-history

# Visibility
EYE = "\uea70"                 # codicon-eye
EYE_CLOSED = "\ueae7"          # codicon-eye-closed

# Run / control
PLAY = "\ueb2c"                # codicon-play
STOP_CIRCLE = "\ueba5"         # codicon-stop-circle

# Output / status
INFO = "\uea74"                # codicon-info
WARNING = "\uea6c"             # codicon-warning
ERROR = "\uea87"               # codicon-error
CHECK = "\ueab2"               # codicon-check

# Layout / chevrons
CHEVRON_DOWN = "\ueab4"        # codicon-chevron-down
CHEVRON_RIGHT = "\ueab6"       # codicon-chevron-right
CHEVRON_LEFT = "\ueab5"        # codicon-chevron-left
CHEVRON_UP = "\ueab7"          # codicon-chevron-up

# Camera / 3D
GLOBE = "\ueb01"               # codicon-globe
SCREEN_FULL = "\ueb4c"         # codicon-screen-full (frame all)
PREVIEW = "\ueb2f"             # codicon-preview
EXPAND_ALL = "\ueb95"          # codicon-expand-all
ZOOM_IN = "\ueb81"             # codicon-zoom-in
ZOOM_OUT = "\ueb82"            # codicon-zoom-out

# ---------------------------------------------------------------------------
# Operation icons (added in M6.5 for the top tools toolbar)
# ---------------------------------------------------------------------------

# Inspect
GRAPH = "\ueb03"               # codicon-graph (mesh info)
GRAPH_LINE = "\uebe2"          # codicon-graph-line (statistics)
SYMBOL_RULER = "\uea96"        # codicon-symbol-ruler (measure)
DASHBOARD = "\ueacd"           # codicon-dashboard
TELESCOPE = "\ueb68"           # codicon-telescope
PULSE = "\ueb31"               # codicon-pulse

# Mesh repair
SHIELD = "\ueb53"              # codicon-shield (fill holes / repair)
WAND = "\uebcf"                # codicon-wand (auto repair)
SYMBOL_EVENT = "\uea86"        # codicon-symbol-event (find issues)
CIRCUIT_BOARD = "\ueabe"       # codicon-circuit-board (manifold check)

# Mesh edit
PACKAGE = "\ueb29"             # codicon-package (mesh / object)
LAYERS = "\uebd2"              # codicon-layers (decimate)
LAYERS_ACTIVE = "\uebd4"       # codicon-layers-active (remesh / lod)
EDIT = "\uea73"                # codicon-edit
ROCKET = "\ueb44"              # codicon-rocket (smooth / fast op)
PRIMITIVE_SQUARE = "\uea72"    # codicon-primitive-square (subdivide)

# Boolean
GIT_MERGE = "\ueafe"           # codicon-git-merge (boolean union)
MERGE = "\uebab"               # codicon-merge (boolean)
SPLIT_HORIZONTAL = "\ueb56"    # codicon-split-horizontal (boolean subtract)
DIFF = "\ueae1"                # codicon-diff (boolean diff)

# Transform (codicons has no native rotate/scale/translate — use stand-ins)
COMPASS = "\uebd5"             # codicon-compass (transform / orient)
COLOR_MODE = "\ueac6"          # codicon-color-mode
MIRROR = "\uea69"              # codicon-mirror (mirror transform)
EXTENSIONS = "\ueae6"          # codicon-extensions (more tools)


# ---------------------------------------------------------------------------
# Fallback to FontAwesome 6 — used when codicons failed to load.
# ---------------------------------------------------------------------------

_FALLBACKS: dict[str, str] = {
    # File / IO
    FILE_OPEN: fa.ICON_FA_FOLDER_OPEN,
    FILE: fa.ICON_FA_FILE,
    SAVE: fa.ICON_FA_FLOPPY_DISK,
    SAVE_AS: fa.ICON_FA_FLOPPY_DISK,
    NEW_FILE: fa.ICON_FA_FILE_CIRCLE_PLUS,
    TRASH: fa.ICON_FA_TRASH,
    CLEAR_ALL: fa.ICON_FA_TRASH_CAN,
    REFRESH: fa.ICON_FA_ARROWS_ROTATE,
    # Sidebar
    LIST_TREE: fa.ICON_FA_LIST,
    SEARCH: fa.ICON_FA_MAGNIFYING_GLASS,
    TOOLS: fa.ICON_FA_WRENCH,
    SETTINGS_GEAR: fa.ICON_FA_GEAR,
    HISTORY: fa.ICON_FA_CLOCK_ROTATE_LEFT,
    # Visibility / control
    EYE: fa.ICON_FA_EYE,
    EYE_CLOSED: fa.ICON_FA_EYE_SLASH,
    PLAY: fa.ICON_FA_PLAY,
    STOP_CIRCLE: fa.ICON_FA_STOP,
    # Status
    INFO: fa.ICON_FA_CIRCLE_INFO,
    WARNING: fa.ICON_FA_TRIANGLE_EXCLAMATION,
    ERROR: fa.ICON_FA_CIRCLE_EXCLAMATION,
    CHECK: fa.ICON_FA_CHECK,
    # Chevrons
    CHEVRON_DOWN: fa.ICON_FA_CHEVRON_DOWN,
    CHEVRON_RIGHT: fa.ICON_FA_CHEVRON_RIGHT,
    CHEVRON_LEFT: fa.ICON_FA_CHEVRON_LEFT,
    CHEVRON_UP: fa.ICON_FA_CHEVRON_UP,
    # Camera / view
    GLOBE: fa.ICON_FA_GLOBE,
    SCREEN_FULL: fa.ICON_FA_EXPAND,
    PREVIEW: fa.ICON_FA_EYE,
    EXPAND_ALL: fa.ICON_FA_EXPAND,
    ZOOM_IN: fa.ICON_FA_MAGNIFYING_GLASS_PLUS,
    ZOOM_OUT: fa.ICON_FA_MAGNIFYING_GLASS_MINUS,
    # Inspect
    GRAPH: fa.ICON_FA_CHART_LINE,
    GRAPH_LINE: fa.ICON_FA_CHART_LINE,
    SYMBOL_RULER: fa.ICON_FA_RULER,
    DASHBOARD: fa.ICON_FA_GAUGE_HIGH,
    TELESCOPE: fa.ICON_FA_BINOCULARS,
    PULSE: fa.ICON_FA_HEART_PULSE,
    # Mesh repair
    SHIELD: fa.ICON_FA_SHIELD,
    WAND: fa.ICON_FA_WAND_MAGIC_SPARKLES,
    SYMBOL_EVENT: fa.ICON_FA_BOLT,
    CIRCUIT_BOARD: fa.ICON_FA_MICROCHIP,
    # Mesh edit
    PACKAGE: fa.ICON_FA_BOX,
    LAYERS: fa.ICON_FA_LAYER_GROUP,
    LAYERS_ACTIVE: fa.ICON_FA_LAYER_GROUP,
    EDIT: fa.ICON_FA_PEN,
    ROCKET: fa.ICON_FA_ROCKET,
    PRIMITIVE_SQUARE: fa.ICON_FA_SQUARE,
    # Boolean
    GIT_MERGE: fa.ICON_FA_CODE_MERGE,
    MERGE: fa.ICON_FA_CODE_MERGE,
    SPLIT_HORIZONTAL: fa.ICON_FA_CODE_BRANCH,
    DIFF: fa.ICON_FA_CODE_COMPARE,
    # Transform
    COMPASS: fa.ICON_FA_COMPASS,
    COLOR_MODE: fa.ICON_FA_PALETTE,
    MIRROR: fa.ICON_FA_RIGHT_LEFT,
    EXTENSIONS: fa.ICON_FA_PUZZLE_PIECE,
}

_codicons_available: bool = False


def set_codicons_available(value: bool) -> None:
    """Called once after font loading to record whether codicons merged.

    If codicons failed (file missing, atlas overflow, etc.), :func:`safe`
    falls back to the FontAwesome 6 glyphs from ``icons_fontawesome_6``,
    which is bundled with ``imgui_bundle`` and always available.
    """
    global _codicons_available
    _codicons_available = value


def safe(glyph: str) -> str:
    """Return ``glyph`` if codicons loaded, else its FontAwesome fallback."""
    if _codicons_available:
        return glyph
    return _FALLBACKS.get(glyph, "?")
