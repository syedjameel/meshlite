"""meshlite entry point.

Run with:

    python main.py

or, after ``pip install -e .``:

    meshlite
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow ``python main.py`` from the project root without installing the package.
# When installed via ``pip install -e .`` the package is on sys.path already and
# this insert is harmless.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meshlite.app import main  # noqa: E402

if __name__ == "__main__":
    main()
