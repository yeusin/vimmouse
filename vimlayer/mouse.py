"""Cursor movement and click simulation (platform-agnostic wrapper)."""

import time
import logging
from typing import Tuple, Any
from .platforms import get_platform

log = logging.getLogger(__name__)

_MOUSE_S0 = 4
_MOUSE_STEP_MAX = 100
_MOUSE_RAMP_FRAMES = 20
_MOUSE_TIMEOUT = 0.15

class MouseController:
    """Manages mouse state, including acceleration for keyboard-driven movement."""

    def __init__(self) -> None:
        self._provider = get_platform().mouse
        self._mouse_repeat_count = 0
        self._last_move_time = 0.0
        self._last_dx = 0
        self._last_dy = 0

    def move_relative(self, dx: int, dy: int, repeat: bool = False, dragging: bool = False) -> None:
        now = time.time()
        direction_reversed = (
            dx != 0 and self._last_dx != 0 and (dx > 0) != (self._last_dx > 0)
        ) or (dy != 0 and self._last_dy != 0 and (dy > 0) != (self._last_dy > 0))

        if repeat and (now - self._last_move_time < _MOUSE_TIMEOUT) and not direction_reversed:
            self._mouse_repeat_count = min(self._mouse_repeat_count + 1, _MOUSE_RAMP_FRAMES)
        else:
            self._mouse_repeat_count = 0

        self._last_move_time = now
        self._last_dx = dx
        self._last_dy = dy

        t = self._mouse_repeat_count / _MOUSE_RAMP_FRAMES
        ease = 3 * (t**2) - 2 * (t**3)
        step = int(_MOUSE_S0 + (_MOUSE_STEP_MAX - _MOUSE_S0) * ease)

        pos = get_cursor_position()
        if pos:
            x, y = pos
            move_cursor(x + dx * step, y + dy * step, dragging=dragging)


def get_cursor_position() -> Tuple[float, float]:
    return get_platform().mouse.get_cursor_position()


def move_cursor(x: float, y: float, dragging: bool = False) -> None:
    get_platform().mouse.move_cursor(x, y, dragging=dragging)


def click(x: float, y: float) -> None:
    get_platform().mouse.click(x, y)


def mouse_down(x: float, y: float) -> None:
    get_platform().mouse.mouse_down(x, y)


def mouse_up(x: float, y: float) -> None:
    get_platform().mouse.mouse_up(x, y)


def right_click(x: float, y: float) -> None:
    get_platform().mouse.right_click(x, y)


def back_button() -> None:
    get_platform().mouse.back_button()


def forward_button() -> None:
    get_platform().mouse.forward_button()


def scroll(lines: int) -> None:
    get_platform().mouse.scroll(lines)


def element_center(position: Any, size: Any) -> Tuple[float, float]:
    return get_platform().mouse.element_center(position, size)
