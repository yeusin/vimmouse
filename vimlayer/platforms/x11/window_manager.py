import logging
from typing import Optional
from Xlib import display, X
from ewmh import EWMH
from ..base import WindowManagerProvider

log = logging.getLogger(__name__)

class X11WindowManager(WindowManagerProvider):
    def __init__(self):
        self._ewmh = EWMH()
        self._display = self._ewmh.display
        self._screen = self._display.screen()

    def _get_active_window(self):
        return self._ewmh.getActiveWindow()

    def _get_screen_geometry(self):
        # Simplistic: just returns the entire screen size
        return 0, 0, self._screen.width_in_pixels, self._screen.height_in_pixels

    def _unmaximize_if_needed(self, win):
        state = self._ewmh.getWmState(win)
        is_max_v = '_NET_WM_STATE_MAXIMIZED_VERT' in state
        is_max_h = '_NET_WM_STATE_MAXIMIZED_HORZ' in state
        if is_max_v or is_max_h:
            log.info("Window is maximized, unmaximizing before tiling")
            # 0 = remove, 1 = add, 2 = toggle
            self._ewmh.setWmState(win, 0, '_NET_WM_STATE_MAXIMIZED_VERT', '_NET_WM_STATE_MAXIMIZED_HORZ')
            self._ewmh.display.flush()

    def tile_window(self, quadrant: int) -> None:
        win = self._get_active_window()
        log.info("tile_window quadrant=%d, active_win=%s", quadrant, win)
        if not win: return
        self._unmaximize_if_needed(win)
        sx, sy, sw, sh = self._get_screen_geometry()
        
        target_w = sw // 2
        target_h = sh // 2
        
        x = sx if quadrant in (1, 3) else sx + target_w
        y = sy if quadrant in (1, 2) else sy + target_h
        
        log.info("Moving window to x=%d, y=%d, w=%d, h=%d", x, y, target_w, target_h)
        self._ewmh.setMoveResizeWindow(win, x=x, y=y, w=target_w, h=target_h)
        self._ewmh.display.flush()

    def tile_window_sixth(self, col: int, row: int) -> None:
        win = self._get_active_window()
        log.info("tile_window_sixth col=%d, row=%d, active_win=%s", col, row, win)
        if not win: return
        self._unmaximize_if_needed(win)
        sx, sy, sw, sh = self._get_screen_geometry()
        target_w = sw // 3
        target_h = sh // 2
        log.info("Moving window to x=%d, y=%d, w=%d, h=%d", sx + col * target_w, sy + row * target_h, target_w, target_h)
        self._ewmh.setMoveResizeWindow(win, x=sx + col * target_w, y=sy + row * target_h, w=target_w, h=target_h)
        self._ewmh.display.flush()

    def tile_window_half(self, side: str) -> None:
        win = self._get_active_window()
        log.info("tile_window_half side=%s, active_win=%s", side, win)
        if not win: return
        self._unmaximize_if_needed(win)
        sx, sy, sw, sh = self._get_screen_geometry()
        
        if side == "left":
            self._ewmh.setMoveResizeWindow(win, x=sx, y=sy, w=sw // 2, h=sh)
        elif side == "right":
            self._ewmh.setMoveResizeWindow(win, x=sx + sw // 2, y=sy, w=sw // 2, h=sh)
        elif side == "top":
            self._ewmh.setMoveResizeWindow(win, x=sx, y=sy, w=sw, h=sh // 2)
        elif side == "bottom":
            self._ewmh.setMoveResizeWindow(win, x=sx, y=sy + sh // 2, w=sw, h=sh // 2)
        self._ewmh.display.flush()

    def center_window(self) -> None:
        win = self._get_active_window()
        log.info("center_window, active_win=%s", win)
        if not win: return
        self._unmaximize_if_needed(win)
        sx, sy, sw, sh = self._get_screen_geometry()
        w = sw // 2
        h = sh // 2
        log.info("Centering window to w=%d, h=%d", w, h)
        self._ewmh.setMoveResizeWindow(win, x=sx + (sw - w) // 2, y=sy + (sh - h) // 2, w=w, h=h)
        self._ewmh.display.flush()

    def toggle_maximize(self) -> None:
        win = self._get_active_window()
        if not win: return
        # EWMH maximize states are _NET_WM_STATE_MAXIMIZED_VERT and _NET_WM_STATE_MAXIMIZED_HORZ
        self._ewmh.setWmState(win, 2, '_NET_WM_STATE_MAXIMIZED_VERT', '_NET_WM_STATE_MAXIMIZED_HORZ')
        self._ewmh.display.flush()
