"""Architecture rule enforcement — prevents layer violations from regressing.

Walks every .py file under src/meshlite/ and checks import rules:
- render/, app_state/ must NOT import meshlib
- ui/ must NOT import from meshlite.domain directly (use app_state re-exports)
- Only domain/ and ops/ may import meshlib
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).parent.parent / "src" / "meshlite"


def _collect_imports(filepath: pathlib.Path) -> list[str]:
    """Return all imported module names from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except SyntaxError:
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _relative_to_src(path: pathlib.Path) -> str:
    return str(path.relative_to(SRC.parent))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_render_does_not_import_meshlib() -> None:
    """render/ must not import meshlib directly."""
    violations = []
    for py in (SRC / "render").rglob("*.py"):
        for mod in _collect_imports(py):
            if mod.startswith("meshlib"):
                violations.append(f"{_relative_to_src(py)}: imports {mod}")
    assert not violations, "render/ imports meshlib:\n" + "\n".join(violations)


def test_app_state_does_not_import_meshlib() -> None:
    """app_state/ must not import meshlib directly."""
    violations = []
    for py in (SRC / "app_state").rglob("*.py"):
        for mod in _collect_imports(py):
            if mod.startswith("meshlib"):
                violations.append(f"{_relative_to_src(py)}: imports {mod}")
    assert not violations, "app_state/ imports meshlib:\n" + "\n".join(violations)


def test_ui_does_not_import_domain_directly() -> None:
    """ui/ must not import from meshlite.domain — use app_state re-exports."""
    violations = []
    for py in (SRC / "ui").rglob("*.py"):
        for mod in _collect_imports(py):
            if mod.startswith("meshlite.domain"):
                violations.append(f"{_relative_to_src(py)}: imports {mod}")
    assert not violations, "ui/ imports domain directly:\n" + "\n".join(violations)


def test_only_domain_and_ops_import_meshlib() -> None:
    """Only domain/ and ops/ may import meshlib. Everything else is banned."""
    allowed_dirs = {"domain", "ops"}
    violations = []
    for py in SRC.rglob("*.py"):
        rel = py.relative_to(SRC)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else ""
        if top_dir in allowed_dirs:
            continue
        for mod in _collect_imports(py):
            if mod.startswith("meshlib"):
                violations.append(f"{_relative_to_src(py)}: imports {mod}")
    assert not violations, "meshlib imported outside domain/ops:\n" + "\n".join(violations)
