"""Cursor movement and click simulation via CGEvent."""

import time
import Quartz
from ApplicationServices import (
    kAXValueCGPointType,
    kAXValueCGSizeType,
    AXValueGetValue,
)


_MOUSE_S0 = 10        # base sensitivity (pixels per step)
_MOUSE_STEP_MAX = 75   # cap on maximum step size
_MOUSE_RAMP_FRAMES = 25  # smooth ramp over ~25-30 events


class MouseController:
    """Manages mouse state, including acceleration for keyboard-driven movement."""
    def __init__(self):
        self._mouse_repeat_count = 0
        self._last_move_time = 0

    def move_relative(self, dx, dy, repeat=False, dragging=False):
        """Move the mouse cursor with smooth acceleration."""
        now = time.time()

        # If the last move was recent (within 300ms), we are in a movement session.
        if now - self._last_move_time < 0.3:
            # We continue the ramp smoothly without abrupt jumps.
            self._mouse_repeat_count = min(self._mouse_repeat_count + 1, _MOUSE_RAMP_FRAMES)
        else:
            # Movement stopped for too long; reset to base speed.
            self._mouse_repeat_count = 0

        self._last_move_time = now

        # Calculate speed based on current ramp-up position
        t = self._mouse_repeat_count / _MOUSE_RAMP_FRAMES
        # Smoothstep (Cubic) acceleration for a more organic feel
        ease = 3 * (t**2) - 2 * (t**3)
        step = int(_MOUSE_S0 + (_MOUSE_STEP_MAX - _MOUSE_S0) * ease)

        x, y = get_cursor_position()
        move_cursor(x + dx * step, y + dy * step, dragging=dragging)


def get_cursor_position():
    """Return the current cursor position as (x, y)."""
    event = Quartz.CGEventCreate(None)
    point = Quartz.CGEventGetLocation(event)
    return point.x, point.y


def move_cursor(x, y, dragging=False):
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
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def click(x, y):
    """Click at (x, y) by posting mouse down + up events."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def mouse_down(x, y):
    """Press and hold left mouse button at (x, y)."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)


def mouse_up(x, y):
    """Release left mouse button at (x, y)."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def right_click(x, y):
    """Right-click at (x, y) by posting right mouse down + up events."""
    move_cursor(x, y)
    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventRightMouseDown, point, Quartz.kCGMouseButtonRight
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventRightMouseUp, point, Quartz.kCGMouseButtonRight
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def back_button():
    """Simulate mouse back button (button 3) press."""
    pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseDown, pos, 3
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseUp, pos, 3
    )
    Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventButtonNumber, 3)
    Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventButtonNumber, 3)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def forward_button():
    """Simulate mouse forward button (button 4) press."""
    pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseDown, pos, 4
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventOtherMouseUp, pos, 4
    )
    Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventButtonNumber, 4)
    Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventButtonNumber, 4)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def scroll(lines):
    """Scroll vertically. Positive = up, negative = down."""
    event = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 1, lines
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def element_center(position, size):
    """Return (cx, cy) center point given AXValue position and size."""
    err, pos = AXValueGetValue(position, kAXValueCGPointType, None)
    err, sz = AXValueGetValue(size, kAXValueCGSizeType, None)
    x = pos.x + sz.width / 2
    y = pos.y + sz.height / 2
    return x, y
