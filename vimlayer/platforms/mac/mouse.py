"""macOS implementation of mouse control."""

import time
import logging
from typing import Tuple, Any
import Quartz
from ApplicationServices import (
    kAXValueCGPointType,
    kAXValueCGSizeType,
    AXValueGetValue,
)
from ..base import MouseProvider

log = logging.getLogger(__name__)

_MOUSE_S0 = 4
_MOUSE_STEP_MAX = 100
_MOUSE_RAMP_FRAMES = 20
_MOUSE_TIMEOUT = 0.15


class MacMouse(MouseProvider):
    def __init__(self) -> None:
        pass

    def move_relative(self, dx: int, dy: int, repeat: bool = False, dragging: bool = False) -> None:
        pos = self.get_cursor_position()
        if pos:
            x, y = pos
            self.move_cursor(x + dx, y + dy, dragging=dragging)

    def get_cursor_position(self) -> Tuple[float, float]:
        event = Quartz.CGEventCreate(None)
        if not event:
            return 0.0, 0.0
        point = Quartz.CGEventGetLocation(event)
        return point.x, point.y

    def move_cursor(self, x: float, y: float, dragging: bool = False) -> None:
        w = Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID())
        h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        point = Quartz.CGPointMake(x, y)
        event_type = Quartz.kCGEventLeftMouseDragged if dragging else Quartz.kCGEventMouseMoved
        event = Quartz.CGEventCreateMouseEvent(None, event_type, point, Quartz.kCGMouseButtonLeft)
        if event:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def click(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        point = Quartz.CGPointMake(x, y)
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
        if down: Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        if up: Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def right_click(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        point = Quartz.CGPointMake(x, y)
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseDown, point, Quartz.kCGMouseButtonRight)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseUp, point, Quartz.kCGMouseButtonRight)
        if down: Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        if up: Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def mouse_down(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        point = Quartz.CGPointMake(x, y)
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
        if down: Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

    def mouse_up(self, x: float, y: float) -> None:
        self.move_cursor(x, y)
        point = Quartz.CGPointMake(x, y)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
        if up: Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def back_button(self) -> None:
        event = Quartz.CGEventCreate(None)
        if not event: return
        pos = Quartz.CGEventGetLocation(event)
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventOtherMouseDown, pos, 3)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventOtherMouseUp, pos, 3)
        if down and up:
            Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventButtonNumber, 3)
            Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventButtonNumber, 3)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def forward_button(self) -> None:
        event = Quartz.CGEventCreate(None)
        if not event: return
        pos = Quartz.CGEventGetLocation(event)
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventOtherMouseDown, pos, 4)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventOtherMouseUp, pos, 4)
        if down and up:
            Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventButtonNumber, 4)
            Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventButtonNumber, 4)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def scroll(self, lines: int) -> None:
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, lines)
        if event:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def element_center(self, position: Any, size: Any) -> Tuple[float, float]:
        err, pos = AXValueGetValue(position, kAXValueCGPointType, None)
        err, sz = AXValueGetValue(size, kAXValueCGSizeType, None)
        x = pos.x + sz.width / 2
        y = pos.y + sz.height / 2
        return x, y
