"""Cursor movement and click simulation via CGEvent."""

import Quartz
from ApplicationServices import (
    kAXValueCGPointType,
    kAXValueCGSizeType,
    AXValueGetValue,
)


def get_cursor_position():
    """Return the current cursor position as (x, y)."""
    event = Quartz.CGEventCreate(None)
    point = Quartz.CGEventGetLocation(event)
    return point.x, point.y


def move_cursor(x, y):
    """Move the mouse cursor to (x, y) using a synthetic mouse move event."""
    point = Quartz.CGPointMake(x, y)
    event = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft
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
