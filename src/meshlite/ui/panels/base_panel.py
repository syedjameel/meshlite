"""``BasePanel`` — abstract base for all dockable panels.

Every panel in :mod:`meshlite.ui.panels` subclasses this. The contract is
intentionally tiny:

    class MyPanel(BasePanel):
        title = "My Panel"
        def render(self) -> None:
            imgui.text("hello")

The base class:
- holds references to the app and runner so subclasses can read state
- wraps :meth:`render` in a try/except so a panel that throws can't kill
  the entire frame loop (it logs the exception and skips to the next panel)
- exposes ``title`` as the dockable window label
- has optional ``setup()`` / ``cleanup()`` hooks for resources

The runner builds one instance per panel class in its ``__init__`` and
hands ``panel.render`` to ``hello_imgui.DockableWindow.gui_function``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from imgui_bundle import hello_imgui, imgui

if TYPE_CHECKING:
    from meshlite.app import MeshLiteApp

    from ..runner import UIRunner

_LOGGER = logging.getLogger("meshlite.ui.panels")


class BasePanel:
    """Abstract base for dockable UI panels.

    Subclasses override :meth:`render` and optionally ``title``,
    :meth:`setup`, :meth:`cleanup`.
    """

    title: str = "Panel"

    def __init__(self, app: MeshLiteApp, runner: UIRunner) -> None:
        self._app = app
        self._runner = runner
        self._last_error_key: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle hooks (default no-ops)
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """One-shot init after the renderer / GL context exists.

        Called by the runner from its post_init. Default is a no-op.
        """

    def cleanup(self) -> None:
        """One-shot teardown before the GL context is destroyed.

        Default is a no-op.
        """

    # ------------------------------------------------------------------
    # Render — wrapped to keep one panel's bug from killing the frame
    # ------------------------------------------------------------------

    def render(self) -> None:
        """Override to draw the panel's content. Don't call directly —
        use :meth:`safe_render`."""
        raise NotImplementedError

    def safe_render(self) -> None:
        """Wrap :meth:`render` in a try/except. Logs once per distinct error
        type so we don't spam the console at 60 fps but still catch new bugs."""
        try:
            self.render()
        except Exception as e:                              # noqa: BLE001
            error_key = f"{type(e).__name__}: {e}"
            if error_key != self._last_error_key:
                _LOGGER.exception("panel %s render error: %s", self.title, e)
                hello_imgui.log(
                    hello_imgui.LogLevel.error,
                    f"panel {self.title} crashed: {e} (repeats silenced)",
                )
                self._last_error_key = error_key
            imgui.text_colored(
                imgui.ImVec4(1.0, 0.4, 0.4, 1.0),
                f"[panel {self.title} crashed — see console]",
            )
