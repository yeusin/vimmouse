"""Window management (platform-agnostic wrapper)."""

import logging
from .platforms import get_platform

log = logging.getLogger(__name__)


class WindowManager:
    """Manages window operations like tiling, centering, and maximizing."""

    def __init__(self) -> None:
        self._provider = get_platform().window_manager

    def tile_window(self, quadrant: int) -> None:
        self._provider.tile_window(quadrant)

    def tile_window_sixth(self, col: int, row: int) -> None:
        self._provider.tile_window_sixth(col, row)

    def tile_window_half(self, side: str) -> None:
        self._provider.tile_window_half(side)

    def center_window(self) -> None:
        self._provider.center_window()

    def toggle_maximize(self) -> None:
        self._provider.toggle_maximize()
