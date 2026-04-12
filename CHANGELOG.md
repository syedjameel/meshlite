# Changelog

## v0.2.0 (2026-04-12)

Production readiness release.

### New Features

- **User preferences** — all settings (viewport sensitivity, colors, lighting, camera FOV, undo limits) are persisted between sessions via hello_imgui's user pref API
- **Settings panel** — live sliders and color pickers in the sidebar for viewport, rendering, camera, and history settings with "Reset to Defaults"
- **Search panel** — fuzzy search across document nodes and operations in the sidebar
- **Recent files** — tracked automatically on mesh load; accessible from File > Open Recent and the command palette
- **Drag-and-drop** — drop mesh files onto the window to load them (GLFW backend, Linux)
- **Cross-platform CI** — GitHub Actions matrix now covers Linux, Windows, and macOS with Python 3.11/3.12/3.13

### Bug Fixes

- **active_task_count leak** — counter was never decremented after task completion
- **GPU upload retry spam** — failed uploads no longer retry every frame at 60fps flooding the log
- **Unnecessary mesh clone** — removed a redundant `.clone()` in CommandBus finalize, saving memory per undoable operation
- **Falsy zero check in Decimate** — setting max_deleted_vertices to 0 no longer silently defaults to unlimited
- **BasePanel error dedup** — distinct panel errors are now logged instead of silencing everything after the first
- **Auto repair partial failure** — result message now clearly says "PARTIAL" when self-intersection fix fails
- **Debug button in production** — removed the CounterOp debug button and `_dev` import from the viewport

### Improvements

- Extracted `FLT_MAX` constant — replaced 5 duplicated 19-digit float literals across decimate/remesh/subdivide
- Named byte estimation constants in undo history with derivation comments
- Asset path resolver (`utils/paths.py`) — works in dev, pip-installed, and frozen bundle contexts
- Operation manifest (`ops/_manifest.py`) — explicit module list for frozen-bundle discovery
- Shader loader and font loader now use the centralized path resolver

### Technical

- 85 automated tests (77 original + 8 new preferences tests)
- Cross-platform CI: ubuntu-latest, windows-latest, macos-latest
- `selected_color` field on `RenderItem` — selection color now driven by preferences

## v0.1.0 (2026-04-12)

Initial public release.

### Features

- **15 mesh operations** with full MeshLib parameter exposure:
  - File: Open Mesh, Save Mesh As
  - Repair: Fill Holes, Auto Repair, Remove Duplicates
  - Inspect: Fix Self-Intersections (Local + Voxel-based)
  - Mesh Edit: Decimate, Remesh, Subdivide, Laplacian Smooth
  - Boolean: Union / Intersection / Difference (with node picker)
  - Transform: Translate, Rotate, Scale, Mirror
- **VSCode-style UI** with activity bar, dockable panels, dark theme, codicons
- **MeshInspector-style top toolbar** with 26 tools across 7 groups
- **Command palette** (Ctrl+Shift+P) with fuzzy search
- **Snapshot-based undo/redo** (Ctrl+Z / Ctrl+Shift+Z)
- **Mesh Info panel** with comprehensive statistics
- **Properties panel** with auto-rendered parameter widgets
- **Outliner** with visibility toggles and right-click context menus
- **Status bar** with mesh count, selection, FPS
- **Async worker dispatch** — operations run on background threads
- **One-file operation pattern** — adding a new op requires zero edits elsewhere

### Technical

- 5-layer architecture: domain / ops / render / app_state / ui
- MeshLib 3.1.1.211 backend
- imgui_bundle 1.92.601 UI
- moderngl 5.12.0 renderer
- Python 3.11+ required
