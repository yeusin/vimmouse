"""Cursor movement and click simulation via CGEvent."""

import time
from typing import Tuple, Any
import Quartz
from ApplicationServices import (
    kAXValueCGPointType,
    kAXValueCGSizeType,
    AXValueGetValue,
)


_MOUSE_S0 = 4         # base sensitivity (pixels per step)
_MOUSE_STEP_MAX = 100  # cap on maximum step size
_MOUSE_RAMP_FRAMES = 20  # smooth ramp over ~20 events
_MOUSE_TIMEOUT = 0.15  # session timeout for acceleration reset (seconds)


class MouseController:
    """Manages mouse state, including acceleration for keyboard-driven movement."""
    def __init__(self) -> None:
        self._mouse_repeat_count = 0
        self._last_move_time = 0.0
        self._last_dx = 0
        self._last_dy = 0

    def move_relative(self, dx: int, dy: int, repeat: bool = False, dragging: bool = False) -> None:
        """Move the mouse cursor with smooth acceleration."""
        now = time.time()

        # Reset acceleration if:
        # 1. Too much time passed since last move
        # 2. The direction changed significantly (reversing on either axis)
        # 3. This is a new key press (not a repeat)
        direction_reversed = (dx != 0 and self._last_dx != 0 and (dx > 0) != (self._last_dx > 0)) or \
                             (dy != 0 and self._last_dy != 0 and (dy > 0) != (self._last_dy > 0))

        if repeat and (now - self._last_move_time < _MOUSE_TIMEOUT) and not direction_reversed:
            # We continue the ramp smoothly without abrupt jumps.
            self._mouse_repeat_count = min(self._mouse_repeat_count + 1, _MOUSE_RAMP_FRAMES)
        else:
            # New press, stop, or change direction; reset to base speed.
            self._mouse_repeat_count = 0

        self._last_move_time = now
        self._last_dx = dx
        self._last_dy = dy

        # Calculate speed based on current ramp-up position
        t = self._mouse_repeat_count / _MOUSE_RAMP_FRAMES
        # Smoothstep (Cubic) acceleration for a more organic feel
        ease = 3 * (t**2) - 2 * (t**3)
        step = int(_MOUSE_S0 + (_MOUSE_STEP_MAX - _MOUSE_S0) * ease)

        pos = get_cursor_position()
        if pos:
            x, y = pos
            move_cursor(x + dx * step, y + dy * step, dragging=dragging)


def get_cursor_position() -> Tuple[float, float]:
    """Return the current cursor position as (x, y)."""
    event = Quartz.CGEventCreate(None)
    if not event:
        return 0.0, 0.0
    point = Quartz.CGEventGetLocation(event)
    return point.x, point.y


def move_cursor(x: float, y: float, dragging: bool = False) -> None:
    """Move the mouse cursor to (x, y), clamped to screen bounds."""
    w = Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID())
    h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    point = Quartz.CGPointMake(x, y)
    event_type = Quartz.kCGEventLeftMouseDragged if dragging else Quartz.kCGEventMouseMoved
    event = Quartz.CGEventCreateMouseEvent(
        None, event_type, point, Quartz.kCGMouseButtonLeft
    )
    if event:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def click(x: float, y: float) -> None:
    """Click at (x, y) by posting mouse down + up events."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    if down:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    if up:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def mouse_down(x: float, y: float) -> None:
    """Press and hold left mouse button at (x, y)."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    if down:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)


def mouse_up(x: float, y: float) -> None:
    """Release left mouse button at (x, y)."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    if up:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def right_click(x: float, y: float) -> None:
    """Right-click at (x, y) by posting right mouse down + up events."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventRightMouseDown, point, Quartz.kCGMouseButtonRight
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventRightMouseUp, point, Quartz.kCGMouseButtonRight
    )
    if down:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    if up:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def back_button() -> None:
    """Simulate mouse back button (button 3) press."""
    event = Quartz.CGEventCreate(None)
    if not event:
        return
    pos = Quartz.CGEventGetLocation(event)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseDown, pos, 3
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseUp, pos, 3
    )
    if down and up:
        Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventButtonNumber, 3)
        Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventButtonNumber, 3)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def forward_button() -> None:
    """Simulate mouse forward button (button 4) press."""
    event = Quartz.CGEventCreate(None)
    if not event:
        return
    pos = Quartz.CGEventGetLocation(event)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseDown, pos, 4
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseUp, pos, 4
    )
    if down and up:
        Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventButtonNumber, 4)
        Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventButtonNumber, 4)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def scroll(lines: int) -> None:
    """Scroll vertically. Positive = up, negative = down."""
    event = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 1, lines
    )
    if event:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def element_center(position: Any, size: Any) -> Tuple[float, float]:
    """Return (cx, cy) center point given AXValue position and size."""
    err, pos = AXValueGetValue(position, kAXValueCGPointType, None)
    err, sz = AXValueGetValue(size, kAXValueCGSizeType, None)
    x = pos.x + sz.width / 2
    y = pos.y + sz.height / 2
    return x, y
