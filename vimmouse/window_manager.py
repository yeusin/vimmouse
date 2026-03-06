"""Window management: tiling, splitting, and cycling."""

import logging
import ApplicationServices as AX
import Quartz
from AppKit import NSScreen

log = logging.getLogger(__name__)

class WindowManager:
    """Manages window operations like tiling, centering, and maximizing."""
    def __init__(self):
        self._saved_frames = {}

    def _get_focused_window(self):
        system = AX.AXUIElementCreateSystemWide()
        err, focused_app = AX.AXUIElementCopyAttributeValue(system, "AXFocusedApplication", None)
        if err != 0 or not focused_app:
            return None
        err, focused_win = AX.AXUIElementCopyAttributeValue(focused_app, "AXFocusedWindow", None)
        return focused_win if err == 0 else None

    def _get_visible_rect(self):
        screen = NSScreen.mainScreen()
        full = screen.frame()
        visible = screen.visibleFrame()
        ax_x = visible.origin.x
        ax_y = full.size.height - visible.origin.y - visible.size.height
        return ax_x, ax_y, visible.size.width, visible.size.height

    def _get_window_frame(self, win):
        err, pos_val = AX.AXUIElementCopyAttributeValue(win, "AXPosition", None)
        err2, size_val = AX.AXUIElementCopyAttributeValue(win, "AXSize", None)
        if pos_val and size_val:
            _, p = AX.AXValueGetValue(pos_val, AX.kAXValueCGPointType, None)
            _, s = AX.AXValueGetValue(size_val, AX.kAXValueCGSizeType, None)
            return p.x, p.y, s.width, s.height
        return None

    def _set_window_frame(self, win, x, y, w, h):
        pos = AX.AXValueCreate(AX.kAXValueCGPointType, Quartz.CGPointMake(x, y))
        size = AX.AXValueCreate(AX.kAXValueCGSizeType, Quartz.CGSizeMake(w, h))
        AX.AXUIElementSetAttributeValue(win, "AXPosition", pos)
        AX.AXUIElementSetAttributeValue(win, "AXSize", size)

    def tile_window(self, quadrant):
        win = self._get_focused_window()
        if not win:
            return
        ax_x, ax_y, ax_w, ax_h = self._get_visible_rect()
        hw, hh = ax_w / 2, ax_h / 2
        coords = {1: (ax_x, ax_y), 2: (ax_x + hw, ax_y), 
                  3: (ax_x, ax_y + hh), 4: (ax_x + hw, ax_y + hh)}
        if quadrant in coords:
            x, y = coords[quadrant]
            self._set_window_frame(win, x, y, hw, hh)

    def tile_window_sixth(self, col, row):
        win = self._get_focused_window()
        if not win:
            return
        ax_x, ax_y, ax_w, ax_h = self._get_visible_rect()
        tw, hh = ax_w / 3, ax_h / 2
        self._set_window_frame(win, ax_x + col * tw, ax_y + row * hh, tw, hh)

    def tile_window_half(self, side):
        win = self._get_focused_window()
        if not win:
            return
        ax_x, ax_y, ax_w, ax_h = self._get_visible_rect()
        frames = {
            "left": (ax_x, ax_y, ax_w / 2, ax_h),
            "right": (ax_x + ax_w / 2, ax_y, ax_w / 2, ax_h),
            "top": (ax_x, ax_y, ax_w, ax_h / 2),
            "bottom": (ax_x, ax_y + ax_h / 2, ax_w, ax_h / 2)
        }
        if side in frames:
            self._set_window_frame(win, *frames[side])

    def center_window(self):
        win = self._get_focused_window()
        if not win:
            return
        ax_x, ax_y, ax_w, ax_h = self._get_visible_rect()
        w = ax_w / 2
        self._set_window_frame(win, ax_x + (ax_w - w) / 2, ax_y, w, ax_h)

    def toggle_maximize(self):
        win = self._get_focused_window()
        if not win:
            return
        key = hash(win)
        if key in self._saved_frames:
            self._set_window_frame(win, *self._saved_frames.pop(key))
        else:
            frame = self._get_window_frame(win)
            if frame:
                self._saved_frames[key] = frame
                self._set_window_frame(win, *self._get_visible_rect())
