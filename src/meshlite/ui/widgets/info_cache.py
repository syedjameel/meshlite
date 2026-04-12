"""Shared helper for lazy-computing and caching :class:`MeshInfo` on a node.

Both the Mesh Info bottom panel and the Properties panel need the same
logic: "if ``node.info_cache`` is None, compute it; if compute fails,
return None and show an error." This helper extracts that into one place.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from meshlite.app_state import MeshInfo, compute_mesh_info

if TYPE_CHECKING:
    from meshlite.app_state.node import DocumentNode

_LOGGER = logging.getLogger("meshlite.ui.info_cache")


def ensure_info_cache(node: DocumentNode) -> MeshInfo | None:
    """Return the node's cached :class:`MeshInfo`, computing it if needed.

    Returns ``None`` if computation fails (logs the error).
    """
    if node.info_cache is not None:
        return node.info_cache

    try:
        info = compute_mesh_info(node.mesh)
        node.info_cache = info
        return info
    except (RuntimeError, ValueError) as e:
        _LOGGER.warning("mesh info compute failed for %s: %s", node.name, e)
        return None
    except Exception as e:
        _LOGGER.exception("unexpected error computing mesh info for %s: %s", node.name, e)
        return None
