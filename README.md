# meshlite

A desktop 3D mesh processing application with a VSCode-inspired interface, powered by [MeshLib](https://meshlib.io/), [moderngl](https://github.com/moderngl/moderngl), and [Dear ImGui](https://github.com/pthom/imgui_bundle).

## Features

**15 mesh operations** with full parameter control:

| Category | Operations |
|---|---|
| **File** | Open (STL / OBJ / PLY / GLB / OFF / 3MF), Save As |
| **Repair** | Fill Holes, Auto Repair, Remove Duplicates |
| **Inspect** | Mesh Info, Find Self-Intersections (Local + Voxel) |
| **Mesh Edit** | Decimate, Remesh, Subdivide, Laplacian Smooth |
| **Boolean** | Union, Intersection, Difference |
| **Transform** | Translate, Rotate, Scale, Mirror |

**Professional UI:**

- MeshInspector-style top toolbar with grouped icon buttons
- Activity bar + collapsible sidebar (Outliner, Operations, Search, Settings)
- Properties panel with auto-rendered parameter widgets
- Command palette with fuzzy search (`Ctrl+Shift+P`)
- Mesh Info panel with topology, geometry, and bounding box statistics
- Snapshot-based undo/redo (`Ctrl+Z` / `Ctrl+Shift+Z`)
- VSCode "Dark+" theme with codicon glyphs
- Drag-and-drop file loading (GLFW backend)
- Recent files list (File menu + command palette)
- Persistent user preferences (viewport, rendering, camera, history)

**Architecture:**

- Adding a new operation is a **single-file change** — zero edits to UI, toolbar, or registry
- 5-layer separation: `domain` / `ops` / `render` / `app_state` / `ui`
- Async worker dispatch — operations run on background threads
- 85 automated tests with architecture rule enforcement
- Cross-platform CI (Linux, Windows, macOS)

## Install

### From PyPI

```bash
pip install meshlite
meshlite
```

### From source

```bash
git clone https://github.com/syedjameel/meshlite.git
cd meshlite
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python main.py
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+P` | Command palette |
| `Ctrl+O` | Open mesh |
| `Ctrl+S` | Save mesh as |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `F` | Frame all (fit viewport) |
| Drag file onto window | Load mesh |

## User Preferences

All settings are persisted automatically between sessions:

- **Viewport:** Rotate / zoom / pan sensitivity
- **Rendering:** Background color, mesh color, selected color, lighting (ambient, specular)
- **Camera:** Field of view
- **History:** Undo depth, memory cap

Access via the **Settings** panel in the sidebar (gear icon in the activity bar).

## Adding a New Operation

meshlite's architecture makes it trivial to add operations. Create one file:

```python
# src/meshlite/ops/smooth/laplacian.py

@register_operation
class LaplacianSmoothOperation(Operation):
    id = "smooth.laplacian"
    label = "Laplacian Smooth"
    category = "Mesh Edit"
    schema = ParamSchema((
        Param("iterations", "int", "Iterations", default=3, min=1, max=100),
        Param("force", "float", "Force", default=0.5, min=0.01, max=1.0),
    ))

    def run(self, mesh, params, ctx):
        # ... meshlib calls ...
        return OperationResult(mesh=mesh, message="Smoothed")
```

The operation automatically appears in the command palette, sidebar, properties panel, and toolbar — with zero edits to any other file.

## Architecture

```
ui  ───>  app_state  ──>  ops  ──>  domain
 |            |            |
 └─>  render ─┘            └──>  domain
```

| Layer | Responsibility | Dependencies |
|---|---|---|
| `domain/` | MeshLib wrapper (`mrm_shim.py`), mesh data, I/O | meshlib, numpy |
| `ops/` | Operations framework, registry, auto-discovery | domain |
| `render/` | moderngl renderer, GPU mesh, camera, shaders | domain (read-only) |
| `app_state/` | Document, CommandBus, undo, events, preferences | domain, ops |
| `ui/` | ImGui panels, theme, toolbar, command palette | all layers (except domain directly) |

## Tech Stack

- **Python 3.11+**
- [MeshLib](https://meshlib.io/) — mesh processing engine (GPL-3)
- [imgui_bundle](https://github.com/pthom/imgui_bundle) — Dear ImGui + hello_imgui
- [moderngl](https://github.com/moderngl/moderngl) — OpenGL rendering
- [numpy](https://numpy.org/) + [PyGLM](https://github.com/Zuzu-Typ/PyGLM)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, code style, and how to add operations.

## License

[GPL-3.0-or-later](./LICENSE) — matches MeshLib's license.
