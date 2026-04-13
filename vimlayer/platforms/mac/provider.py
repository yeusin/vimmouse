"""macOS implementation of the platform provider."""

import os
import signal
import logging
import subprocess
import Quartz
from AppKit import (
    NSApplication,
    NSBundle,
    NSMenu,
    NSMenuItem,
    NSOffState,
    NSOnState,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)
from Foundation import NSObject
from PyObjCTools import AppHelper
import objc

from .window_manager import MacWindowManager
from .mouse import MacMouse
from .hotkey import MacHotkey, MODIFIER_MASK
from .accessibility import MacAccessibility
from .ui import MacUI
from ..base import PlatformProvider
from ... import config

log = logging.getLogger(__name__)

_DEFAULTS: Dict[str, Any] = {
    "keycode": 49,
    "flags": Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift,
    "auto_insert_mode": True,
    "global_tiling_bindings": {
        "win_half_left": {"keycode": 4, "cmd": True, "ctrl": True},
        "win_half_right": {"keycode": 37, "cmd": True, "ctrl": True},
        "win_half_up": {"keycode": 40, "cmd": True, "ctrl": True},
        "win_half_down": {"keycode": 38, "cmd": True, "ctrl": True},
        "win_maximize": {"keycode": 36, "cmd": True, "ctrl": True},
        "win_center": {"keycode": 8, "cmd": True, "ctrl": True},
        "win_tile_1": {"keycode": 18, "cmd": True, "ctrl": True},
        "win_tile_2": {"keycode": 19, "cmd": True, "ctrl": True},
        "win_tile_3": {"keycode": 20, "cmd": True, "ctrl": True},
        "win_tile_4": {"keycode": 21, "cmd": True, "ctrl": True},
        "win_sixth_tl": {"keycode": 12, "cmd": True, "ctrl": True},
        "win_sixth_tc": {"keycode": 13, "cmd": True, "ctrl": True},
        "win_sixth_tr": {"keycode": 14, "cmd": True, "ctrl": True},
        "win_sixth_bl": {"keycode": 0, "cmd": True, "ctrl": True},
        "win_sixth_bc": {"keycode": 1, "cmd": True, "ctrl": True},
        "win_sixth_br": {"keycode": 2, "cmd": True, "ctrl": True},
    },
}

_DEFAULT_KEYBINDINGS: Dict[str, Any] = {
    "move_left": {"keycode": 4},
    "move_down": {"keycode": 38},
    "move_up": {"keycode": 40},
    "move_right": {"keycode": 37},
    "scroll_up": {"keycode": 11, "ctrl": True},
    "scroll_down": {"keycode": 3, "ctrl": True},
    "toggle_all_hints": {"keycode": 3},
    "toggle_cheat_sheet": {"keycode": 44, "shift": True},
    "open_launcher": {"keycode": 44},
    "click": {"keycode": 49},
    "insert_mode": {"keycode": 34},
    "forward": {"keycode": 13},
    "back": {"keycode": 11},
    "right_click": {"keycode": 49, "shift": True},
    "toggle_drag": {"keycode": 9},
    "volume_mute": {"keycode": 109},
    "volume_down": {"keycode": 103},
    "volume_up": {"keycode": 111},
}

_MODIFIER_MAP = [
    (Quartz.kCGEventFlagMaskControl, "\u2303", "Ctrl+"),
    (Quartz.kCGEventFlagMaskAlternate, "\u2325", "Alt+"),
    (Quartz.kCGEventFlagMaskShift, "\u21e7", "Shift+"),
    (Quartz.kCGEventFlagMaskCommand, "\u2318", "Cmd+"),
]

_KEYCODE_NAMES = {
    49: "Space", 36: "Return", 48: "Tab", 51: "Delete", 53: "Escape",
    123: "\u2190", 124: "\u2192", 125: "\u2193", 126: "\u2191",
    122: "F1", 120: "F2", 99: "F3", 118: "F4", 96: "F5", 97: "F6", 98: "F7", 100: "F8", 101: "F9", 109: "F10", 103: "F11", 111: "F12",
}
_KEYCODE_LETTERS = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X", 8: "C", 9: "V",
    11: "B", 12: "Q", 13: "W", 14: "E", 15: "R", 16: "Y", 17: "T", 18: "1", 19: "2",
    20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8",
    29: "0", 30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P", 37: "L", 38: "J",
    39: "'", 40: "K", 41: ";", 42: "\\", 43: ",", 44: "/", 45: "N", 46: "M", 47: ".", 50: "`",
}
_KEYCODE_NAMES.update(_KEYCODE_LETTERS)


class StatusBarController(NSObject):
    def init(self):
        self = objc.super(StatusBarController, self).init()
        if self is None: return None
        self._provider = None
        
        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        self._status_item.setTitle_("VL")

        menu = NSMenu.alloc().init()
        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Settings\u2026", b"openSettings:", "")
        settings_item.setTarget_(self)
        menu.addItem_(settings_item)
        
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", b"quit:", "")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)
        self._status_item.setMenu_(menu)
        return self

    @objc.typedSelector(b"v@:@")
    def openSettings_(self, sender):
        if self._provider: self._provider.ui.show_settings()

    @objc.typedSelector(b"v@:@")
    def quit_(self, sender):
        AppHelper.stopEventLoop()


class MacPlatformProvider(PlatformProvider):
    def __init__(self):
        self._window_manager = MacWindowManager()
        self._mouse = MacMouse()
        self._hotkey = MacHotkey()
        self._accessibility = MacAccessibility()
        self._ui = MacUI()

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

    def get_default_config(self): return dict(_DEFAULTS)
    def get_default_keybindings(self):
        import json
        return json.loads(json.dumps(_DEFAULT_KEYBINDINGS))

    def format_hotkey(self, keycode: int, flags: int, use_symbols: bool = True) -> str:
        parts = []
        for mask, sym, text in _MODIFIER_MAP:
            if flags & mask:
                parts.append(sym if use_symbols else text)
        parts.append(_KEYCODE_NAMES.get(keycode, f"Key{keycode}"))
        return "".join(parts)

    def format_binding(self, spec: Any, use_symbols: bool = True) -> str:
        if isinstance(spec, list):
            return " / ".join(self.format_binding(s, use_symbols) for s in spec)
        keycode = spec["keycode"]
        ctrl = spec.get("ctrl", False)
        shift = spec.get("shift", False)
        name = _KEYCODE_NAMES.get(keycode, f"Key{keycode}")
        if use_symbols:
            prefix = ("\u2303" if ctrl else "") + ("\u21e7" if shift else "")
        else:
            prefix = ("Ctrl+" if ctrl else "") + ("Shift+" if shift else "")
        return f"{prefix}{name}"

    def run(self) -> None:
        self._ensure_accessibility()
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(2)

        from .ui_components import ensure_edit_menu
        ensure_edit_menu()

        status_bar_ctrl = StatusBarController.alloc().init()
        status_bar_ctrl._provider = self

        def on_mode_change(mode):
            log.info("Mode changed: %s", mode or "NORMAL")
            display_mode = mode or "NORMAL"
            if mode:
                status_bar_ctrl._status_item.setTitle_(f"VL:{mode}")
            else:
                status_bar_ctrl._status_item.setTitle_("VL")
            
            # Update watermark
            self._ui.show_watermark(display_mode, timeout=1.0 if display_mode == "NORMAL" else None)

        overlay = self._ui.create_hint_overlay(on_mode_change=on_mode_change)
        
        def on_hotkey():
            AppHelper.callAfter(overlay.return_to_normal)

        overlay._on_config_change = lambda: self._register_global_hotkeys(overlay, config.load())

        cfg = config.load()
        if not self._hotkey.register(on_hotkey, keycode=cfg["keycode"], flags=cfg["flags"], is_primary=True):
            return

        self._register_global_hotkeys(overlay, cfg)
        overlay.show()

        signal.signal(signal.SIGINT, lambda *_: AppHelper.stopEventLoop())
        AppHelper.runEventLoop()

    def _ensure_accessibility(self):
        if AXIsProcessTrusted(): return True
        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if bundle_id:
            subprocess.run(["tccutil", "reset", "Accessibility", bundle_id], capture_output=True)
        return AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})

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
            if spec.get("cmd"): flags |= Quartz.kCGEventFlagMaskCommand
            if spec.get("alt"): flags |= Quartz.kCGEventFlagMaskAlternate
            if spec.get("ctrl"): flags |= Quartz.kCGEventFlagMaskControl
            if spec.get("shift"): flags |= Quartz.kCGEventFlagMaskShift

            def make_callback(h, a):
                def callback():
                    AppHelper.callAfter(h)
                    label = a.replace("win_", "").replace("_", " ").upper()
                    AppHelper.callAfter(lambda: overlay._watermark.set_mode(label, timeout=1.0))
                return callback
            self._hotkey.register(make_callback(handler, action), keycode, flags)
