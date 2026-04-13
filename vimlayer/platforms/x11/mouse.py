import logging
from typing import Tuple, Any
from Xlib import display, X
from Xlib.ext import xtest

log = logging.getLogger(__name__)

class X11Mouse:
    def __init__(self):
        self._display = display.Display()
        self._root = self._display.screen().root

    def get_cursor_position(self) -> Tuple[float, float]:
        data = self._root.query_pointer()
        return float(data.root_x), float(data.root_y)

    def move_cursor(self, x: float, y: float, dragging: bool = False) -> None:
        # detail=0 for absolute motion
        xtest.fake_input(self._display, X.MotionNotify, 0, x=int(x), y=int(y))
        self._display.sync()

    def move_relative(self, dx: int, dy: int, repeat: bool = False, dragging: bool = False) -> None:
        # Basic relative motion, no acceleration implemented yet
        step = 20 if repeat else 5
        # detail=1 for relative motion
        xtest.fake_input(self._display, X.MotionNotify, 1, x=int(dx * step), y=int(dy * step))
        self._display.sync()

    def click(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        xtest.fake_input(self._display, X.ButtonPress, 1)
        xtest.fake_input(self._display, X.ButtonRelease, 1)
        self._display.sync()

    def right_click(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        xtest.fake_input(self._display, X.ButtonPress, 3)
        xtest.fake_input(self._display, X.ButtonRelease, 3)
        self._display.sync()

    def mouse_down(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        xtest.fake_input(self._display, X.ButtonPress, 1)
        self._display.sync()

    def mouse_up(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        xtest.fake_input(self._display, X.ButtonRelease, 1)
        self._display.sync()

    def back_button(self) -> None:
        xtest.fake_input(self._display, X.ButtonPress, 8)
        xtest.fake_input(self._display, X.ButtonRelease, 8)
        self._display.sync()

    def forward_button(self) -> None:
        xtest.fake_input(self._display, X.ButtonPress, 9)
        xtest.fake_input(self._display, X.ButtonRelease, 9)
        self._display.sync()

    def scroll(self, lines: int) -> None:
        # 4 is scroll up, 5 is scroll down in X11
        button = 4 if lines > 0 else 5
        for _ in range(abs(lines)):
            xtest.fake_input(self._display, X.ButtonPress, button)
            xtest.fake_input(self._display, X.ButtonRelease, button)
        self._display.sync()

    def element_center(self, position: Any, size: Any) -> Tuple[float, float]:
        """Convert position/size from accessibility API to center (x, y)."""
        # On Linux, accessibility coords are typically screen coords.
        return float(position[0] + size[0] / 2), float(position[1] + size[1] / 2)
