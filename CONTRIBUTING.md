# Contributing to meshlite

Thanks for your interest in contributing! meshlite is an open-source 3D mesh processing desktop app.

## Development Setup

```bash
git clone https://github.com/syedjameel/meshlite.git
cd meshlite
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Running Tests

```bash
PYTHONPATH= pytest
```

> **Note:** If your shell exports `PYTHONPATH` (e.g. for ROS or FreeCAD), clear it before running pytest to avoid plugin conflicts.

## Running the App

```bash
python main.py
```

## Adding a New Operation

Adding an operation to meshlite is a **one-file change**. Here's the pattern:

1. Create a file under `src/meshlite/ops/<category>/your_op.py`
2. Subclass `Operation`, decorate with `@register_operation`
3. Define `id`, `label`, `category`, `schema` (params), and `run()`
4. That's it — the op auto-discovers and appears in the command palette, sidebar, properties panel, and toolbar

See `src/meshlite/ops/smooth/laplacian.py` for a clean example.

If you plan to build a standalone bundle (PyInstaller etc.), also add the module path to `src/meshlite/ops/_manifest.py` so it's discovered in frozen mode.

## Architecture Rules

meshlite has 5 layers with strict dependency rules:

```
ui  ───>  app_state  ──>  ops  ──>  domain
 |            |            |
 └─>  render ─┘            └──>  domain
```

- **domain/** — pure MeshLib wrapper. Only place `meshlib.*` is imported (via `mrm_shim.py`)
- **ops/** — operations. May import `meshlib` directly for Settings struct construction
- **render/** — moderngl only. No meshlib, no ImGui
- **app_state/** — Document, CommandBus, events, preferences. No meshlib, no GL, no ImGui
- **ui/** — ImGui panels. Imports from `app_state` (not `domain` directly)

Run `pytest tests/test_architecture.py` to verify these rules.

## User Preferences

User-configurable settings live in `app_state/preferences.py` (a plain dataclass with JSON serialization). To make a new value configurable:

1. Add the field to `Preferences` with a sensible default
2. Read from `self._app.preferences.<field>` in the consumer code
3. Add a widget in `ui/panels/sidebar_settings.py` if it should be user-facing
4. Preferences are auto-saved on exit and auto-loaded on startup

## Code Style

- We use `ruff` for linting
- Type hints on all public functions
- Docstrings on all public classes and functions

## Pull Request Process

1. Fork + branch from `main`
2. Make your changes
3. Run `PYTHONPATH= pytest` — all tests must pass
4. Run `ruff check src/ tests/` — no errors
5. Open a PR with a clear description
