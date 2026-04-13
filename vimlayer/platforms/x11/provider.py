import logging
import sys
import signal
from typing import Any, Dict, Optional, List, Tuple, Callable
from Xlib import display, X
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from ..base import PlatformProvider
from .window_manager import X11WindowManager
from .mouse import X11Mouse
from .hotkey import X11Hotkey
from .accessibility import X11Accessibility
from .ui import X11UI
from ... import config

log = logging.getLogger(__name__)

_DEFAULTS: Dict[str, Any] = {
    "keycode": 65,  # Space
    "flags": X.ControlMask,  # Ctrl
    "auto_insert_mode": True,
    "global_tiling_bindings": {
        "win_half_left": {"keycode": 113, "alt": True, "ctrl": True}, # Left
        "win_half_right": {"keycode": 114, "alt": True, "ctrl": True}, # Right
        "win_half_up": {"keycode": 111, "alt": True, "ctrl": True}, # Up
        "win_half_down": {"keycode": 116, "alt": True, "ctrl": True}, # Down
        "win_maximize": {"keycode": 36, "alt": True, "ctrl": True}, # Return
        "win_center": {"keycode": 54, "alt": True, "ctrl": True}, # C
        "win_tile_1": {"keycode": 10, "alt": True, "ctrl": True}, # 1
        "win_tile_2": {"keycode": 11, "alt": True, "ctrl": True}, # 2
        "win_tile_3": {"keycode": 12, "alt": True, "ctrl": True}, # 3
        "win_tile_4": {"keycode": 13, "alt": True, "ctrl": True}, # 4
        "win_sixth_tl": {"keycode": 24, "alt": True, "ctrl": True}, # q
        "win_sixth_tc": {"keycode": 25, "alt": True, "ctrl": True}, # w
        "win_sixth_tr": {"keycode": 26, "alt": True, "ctrl": True}, # e
        "win_sixth_bl": {"keycode": 38, "alt": True, "ctrl": True}, # a
        "win_sixth_bc": {"keycode": 39, "alt": True, "ctrl": True}, # s
        "win_sixth_br": {"keycode": 40, "alt": True, "ctrl": True}, # d
    },
}

_DEFAULT_KEYBINDINGS: Dict[str, Any] = {
    "move_left": {"keycode": 43}, # h
    "move_down": {"keycode": 44}, # j
    "move_up": {"keycode": 45}, # k
    "move_right": {"keycode": 46}, # l
    "scroll_up": {"keycode": 41, "ctrl": True}, # f
    "scroll_down": {"keycode": 56, "ctrl": True}, # b
    "toggle_all_hints": {"keycode": 33}, # p? no, maybe f? 
    "toggle_cheat_sheet": {"keycode": 61, "shift": True}, # /
    "open_launcher": {"keycode": 61}, # /
    "click": {"keycode": 65}, # Space
    "insert_mode": {"keycode": 31}, # i
    "forward": {"keycode": 25}, # w
    "back": {"keycode": 24}, # q
    "right_click": {"keycode": 65, "shift": True}, # Shift+Space
    "toggle_drag": {"keycode": 55}, # v
    "volume_mute": {"keycode": 121},
    "volume_down": {"keycode": 122},
    "volume_up": {"keycode": 123},
}

class X11PlatformProvider(PlatformProvider):
    def __init__(self):
        self._window_manager = X11WindowManager()
        self._mouse = X11Mouse()
        self._hotkey = X11Hotkey()
        self._accessibility = X11Accessibility()
        self._ui = X11UI()
        self._app = None
        self._tray = None

    @property
    def window_manager(self): return self._window_manager
    @property
    def mouse(self): return self._mouse
    @property
    def hotkey(self): return self._hotkey
    @property
    def accessibility(self): return self._accessibility
    @property
    def ui(self): return self._ui

    def get_default_config(self) -> Dict[str, Any]:
        return dict(_DEFAULTS)

    def get_default_keybindings(self) -> Dict[str, Any]:
        import json
        return json.loads(json.dumps(_DEFAULT_KEYBINDINGS))

    def format_hotkey(self, keycode: int, flags: int, use_symbols: bool = True) -> str:
        parts = []
        if flags & X.ControlMask: parts.append("Ctrl+" if not use_symbols else "\u2303")
        if flags & X.Mod1Mask: parts.append("Alt+" if not use_symbols else "\u2325")
        if flags & X.ShiftMask: parts.append("Shift+" if not use_symbols else "\u21e7")
        if flags & X.Mod4Mask: parts.append("Super+" if not use_symbols else "\u2318")
        
        # Keycode to name mapping
        from Xlib import XK
        disp = self.window_manager._display
        keysym = disp.keycode_to_keysym(keycode, 0)
        
        # Try to find a nice name in XK
        name = None
        for k, v in XK.__dict__.items():
            if k.startswith("XK_") and v == keysym:
                name = k[3:] # Strip "XK_"
                break
        
        if name:
            name = name.upper()
            if name == "CONTROL_L" or name == "CONTROL_R": name = "CTRL"
            elif name == "ALT_L" or name == "ALT_R": name = "ALT"
            elif name == "SHIFT_L" or name == "SHIFT_R": name = "SHIFT"
            elif name == "SUPER_L" or name == "SUPER_R": name = "SUPER"
            elif name == "RETURN": name = "ENTER"
            parts.append(name)
        else:
            # Fallback for printing characters that might not be in XK
            name = XK.keysym_to_string(keysym)
            if name:
                parts.append(name.upper())
            else:
                parts.append(f"Key{keycode}")
        return "".join(parts)

    def format_binding(self, spec: Any, use_symbols: bool = True) -> str:
        if isinstance(spec, list):
            return " / ".join(self.format_binding(s, use_symbols) for s in spec)
        keycode = spec["keycode"]
        ctrl = spec.get("ctrl", False)
        shift = spec.get("shift", False)
        alt = spec.get("alt", False)
        super_key = spec.get("super", False)
        
        parts = []
        if ctrl: parts.append("Ctrl+" if not use_symbols else "\u2303")
        if alt: parts.append("Alt+" if not use_symbols else "\u2325")
        if shift: parts.append("Shift+" if not use_symbols else "\u21e7")
        if super_key: parts.append("Super+" if not use_symbols else "\u2318")
        
        from Xlib import XK
        disp = self.window_manager._display
        keysym = disp.keycode_to_keysym(keycode, 0)
        
        name = None
        for k, v in XK.__dict__.items():
            if k.startswith("XK_") and v == keysym:
                name = k[3:]
                break
        
        if name:
            name = name.upper()
            if name == "CONTROL_L" or name == "CONTROL_R": name = "CTRL"
            elif name == "ALT_L" or name == "ALT_R": name = "ALT"
            elif name == "SHIFT_L" or name == "SHIFT_R": name = "SHIFT"
            elif name == "SUPER_L" or name == "SUPER_R": name = "SUPER"
            elif name == "RETURN": name = "ENTER"
            parts.append(name)
        else:
            name = XK.keysym_to_string(keysym)
            if name:
                parts.append(name.upper())
            else:
                parts.append(f"Key{keycode}")
        return "".join(parts)

    def run(self) -> None:
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        overlay = self._ui.create_hint_overlay(on_mode_change=self._on_mode_change)
        
        self._setup_tray()

        def on_hotkey():
            overlay.return_to_normal()

        cfg = config.load()
        self._hotkey.register(on_hotkey, keycode=cfg["keycode"], flags=cfg["flags"], is_primary=True)
        self._register_global_hotkeys(overlay, cfg)

        # Integration: Poll X11 events via QTimer
        # In a real implementation, we should use QSocketNotifier on the X11 display connection.
        self._timer = QTimer()
        self._timer.timeout.connect(self._hotkey.process_events)
        self._timer.start(10) # 10ms polling

        overlay.show()

        signal.signal(signal.SIGINT, lambda *_: self._app.quit())
        sys.exit(self._app.exec())

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self._get_tray_icon(), self._app)
        self._tray.setToolTip("VimLayer")
        
        menu = QMenu()
        settings_action = menu.addAction("Settings\u2026")
        settings_action.triggered.connect(self._ui.show_settings)
        
        menu.addSeparator()
        
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._app.quit)
        
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _get_tray_icon(self, text: str = "VL"):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw text
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
        
        painter.end()
        return QIcon(pixmap)

    def _on_mode_change(self, mode: Optional[str]):
        log.info("Mode changed: %s", mode or "NORMAL")
        display_mode = mode or "NORMAL"
        
        # Update tray
        if self._tray:
            if mode:
                self._tray.setIcon(self._get_tray_icon(f"V:{display_mode[0]}"))
            else:
                self._tray.setIcon(self._get_tray_icon("VL"))
            self._tray.setToolTip(f"VimLayer - {display_mode}")

        # Update watermark
        if mode:
            self._ui.show_watermark(display_mode, timeout=1.0 if display_mode == "NORMAL" else None)
        else:
            self._ui.hide_watermark()

    def _register_global_hotkeys(self, overlay, cfg):
        self._hotkey.unregister_all()
        global_tiling = cfg.get("global_tiling_bindings", {})
        from .hint_overlay import _WINDOW_ACTIONS
        for action, spec in global_tiling.items():
            handler_factory = _WINDOW_ACTIONS.get(action)
            if not handler_factory: continue
            handler = handler_factory(overlay)
            keycode = spec.get("keycode")
            if keycode is None: continue
            
            flags = 0
            if spec.get("ctrl"): flags |= X.ControlMask
            if spec.get("alt"): flags |= X.Mod1Mask
            if spec.get("shift"): flags |= X.ShiftMask
            if spec.get("super"): flags |= X.Mod4Mask

            def make_callback(h, a):
                def callback():
                    # Since we are in the polling loop (Qt thread), we can call directly or via QTimer.singleShot
                    h()
                    label = a.replace("win_", "").replace("_", " ").upper()
                    self._ui.show_watermark(label, timeout=1.0)
                return callback
            self._hotkey.register(make_callback(handler, action), keycode, flags)
