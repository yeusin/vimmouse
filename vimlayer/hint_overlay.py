"""Vimium-style hint overlay for clicking UI elements."""

import logging
import os
import subprocess
import objc
import Quartz
from AppKit import (
    NSImageView,
    NSScreen,
    NSColor,
    NSWindow,
    NSMakeRect,
    NSMakeSize,
    NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSWorkspace,
    NSRunningApplication,
)
from PyObjCTools import AppHelper
import ApplicationServices as AX
from . import accessibility
from . import config
from . import hotkey
from .launcher import Launcher
from . import mouse
from .mouse import MouseController
from . import ui
from .ui import WatermarkManager, CheatSheetOverlay
from .window_manager import WindowManager

log = logging.getLogger(__name__)

# Hint label style
HINT_FONT_SIZE = 12
HINT_BG_COLOR = (0.15, 0.15, 0.15, 0.85)  # dark gray
HINT_TEXT_COLOR = (1.0, 1.0, 1.0, 1.0)  # white
HINT_PADDING = 4
HINT_CORNER_RADIUS = 4

# Window hint style
WIN_HINT_FONT_SIZE = 20
WIN_HINT_BG_COLOR = (0.12, 0.12, 0.12, 0.90)  # dark gray
WIN_HINT_TEXT_COLOR = (1.0, 1.0, 1.0, 1.0)  # white
WIN_HINT_PADDING_X = 14
WIN_HINT_PADDING_Y = 10
WIN_HINT_CORNER_RADIUS = 12
WIN_HINT_ICON_SIZE = 32
WIN_HINT_GAP = 10  # gap between icon and text

# macOS hardware key codes → Latin letters (input-source-independent)
_KEYCODE_TO_CHAR = {
    0: "a",
    1: "s",
    2: "d",
    3: "f",
    4: "h",
    5: "g",
    6: "z",
    7: "x",
    8: "c",
    9: "v",
    11: "b",
    12: "q",
    13: "w",
    14: "e",
    15: "r",
    16: "y",
    17: "t",
    18: "1",
    19: "2",
    20: "3",
    21: "4",
    22: "6",
    23: "5",
    24: "=",
    25: "9",
    26: "7",
    27: "-",
    28: "8",
    29: "0",
    30: "]",
    31: "o",
    32: "u",
    33: "[",
    34: "i",
    35: "p",
    36: "return",
    37: "l",
    38: "j",
    39: "'",
    40: "k",
    41: ";",
    42: "\\",
    43: ",",
    44: "/",
    45: "n",
    46: "m",
    47: ".",
    48: "tab",
    49: "space",
    50: "`",
}
_KEY_ESCAPE = 53
_KEY_BACKSPACE = 51
_CTRL_FLAG = 1 << 18  # NSEventModifierFlagControl
_SHIFT_FLAG = 1 << 17  # NSEventModifierFlagShift
_CMD_FLAG = 1 << 20    # NSEventModifierFlagCommand
_ALT_FLAG = 1 << 19    # NSEventModifierFlagAlternate

# Navigation and control keys to be blocked in normal mode
_NAV_KEYCODES = {
    123,
    124,
    125,
    126,  # Arrows (Left, Right, Down, Up)
    116,
    121,  # Page Up, Page Down
    115,
    119,  # Home, End
    117,  # Forward Delete
}

_ALL_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _build_binding_lookup(bindings):
    """Build a dict mapping (keycode, ctrl, shift, cmd, alt) → action from keybindings config."""
    lookup = {}
    for action, spec in bindings.items():
        specs = spec if isinstance(spec, list) else [spec]
        for s in specs:
            key = (
                s["keycode"],
                bool(s.get("ctrl", False)),
                bool(s.get("shift", False)),
                bool(s.get("cmd", False)),
                bool(s.get("alt", False)),
            )
            lookup[key] = action
    return lookup


# Window sub-command dispatch: action → (overlay) → callable
# Each returns a no-arg callable that AppHelper.callAfter can invoke.
_WINDOW_ACTIONS = {
    "win_tile_1": lambda o: lambda: o._win_mgr.tile_window(1),
    "win_tile_2": lambda o: lambda: o._win_mgr.tile_window(2),
    "win_tile_3": lambda o: lambda: o._win_mgr.tile_window(3),
    "win_tile_4": lambda o: lambda: o._win_mgr.tile_window(4),
    "win_sixth_tl": lambda o: lambda: o._win_mgr.tile_window_sixth(0, 0),
    "win_sixth_tc": lambda o: lambda: o._win_mgr.tile_window_sixth(1, 0),
    "win_sixth_tr": lambda o: lambda: o._win_mgr.tile_window_sixth(2, 0),
    "win_sixth_bl": lambda o: lambda: o._win_mgr.tile_window_sixth(0, 1),
    "win_sixth_bc": lambda o: lambda: o._win_mgr.tile_window_sixth(1, 1),
    "win_sixth_br": lambda o: lambda: o._win_mgr.tile_window_sixth(2, 1),
    "win_half_left": lambda o: lambda: o._win_mgr.tile_window_half("left"),
    "win_half_down": lambda o: lambda: o._win_mgr.tile_window_half("bottom"),
    "win_half_up": lambda o: lambda: o._win_mgr.tile_window_half("top"),
    "win_half_right": lambda o: lambda: o._win_mgr.tile_window_half("right"),
    "win_center": lambda o: o._win_mgr.center_window,
    "win_maximize": lambda o: o._win_mgr.toggle_maximize,
}


def _compute_hint_chars(bindings):
    """Return hint chars string excluding keys bound to actions."""
    bound_keycodes = set()
    for action, spec in bindings.items():
        if action.startswith("win_"):
            continue
        specs = spec if isinstance(spec, list) else [spec]
        for s in specs:
            if not s.get("ctrl") and not s.get("shift") and not s.get("cmd") and not s.get("alt"):
                bound_keycodes.add(s["keycode"])
    excluded = {_KEYCODE_TO_CHAR.get(kc, "").upper() for kc in bound_keycodes}
    return "".join(c for c in _ALL_ALPHA if c not in excluded)


def _element_position(el):
    """Extract (x, y) from an element's AXPosition."""
    err, pos = AX.AXValueGetValue(el["position"], AX.kAXValueCGPointType, None)
    return (pos.x, pos.y)


class HintWindow(NSWindow):
    """Transparent full-screen window for visual overlay (hints)."""

    def init(self):
        screen = NSScreen.mainScreen().frame()
        self = objc.super(HintWindow, self).initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, screen.size.width, screen.size.height),
            0,  # borderless
            NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self.setLevel_(NSFloatingWindowLevel)
        self.setOpaque_(False)
        self.setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.0, 0.01))
        self.setIgnoresMouseEvents_(True)
        self.setHasShadow_(False)
        return self


class HintOverlay:
    def __init__(self, on_mode_change=None):
        self._on_mode_change = on_mode_change
        self._on_config_change = None
        self.window = None
        self.labels = []  # [(hint_string, NSTextField, data, kind)]
        self.typed = ""
        self._pid = None
        self._ws_observer = None
        self._clicking = False
        self._dragging = False
        self._hints_visible = False
        self._hints_gen = 0
        self._win_hint_cache = {}  # kCGWindowNumber -> hint char

        self._mouse_ctrl = MouseController()
        self._watermark = WatermarkManager(on_hide=self._on_watermark_hide)
        self._cheat_sheet = CheatSheetOverlay()
        self._win_mgr = WindowManager()

        self._insert_mode = False
        self._auto_insert = False
        self._last_auto_element = None
        self._normal_tap = None
        self._normal_source = None
        self._menu_tap = None
        self._menu_source = None
        self._is_polling = False
        self._launcher = Launcher(on_dismiss=self._on_launcher_dismiss)
        self.reload_keybindings()

    def _get_cheat_sheet_sections(self):
        """Return dynamic cheat sheet sections based on current keybindings."""

        def b(action):
            spec = self._bindings.get(action)
            if not spec:
                spec = self._global_tiling_bindings.get(action)
            if not spec:
                return "??"

            # For global tiling, we use format_hotkey as it includes modifiers beyond ctrl/shift
            if action in self._global_tiling_bindings:
                flags = 0
                if spec.get("cmd"):
                    flags |= Quartz.kCGEventFlagMaskCommand
                if spec.get("ctrl"):
                    flags |= Quartz.kCGEventFlagMaskControl
                if spec.get("alt"):
                    flags |= Quartz.kCGEventFlagMaskAlternate
                if spec.get("shift"):
                    flags |= Quartz.kCGEventFlagMaskShift
                return config.format_hotkey(spec["keycode"], flags, use_symbols=True)

            return config.format_binding(spec, use_symbols=True)

        sections = [
            (
                "Navigation",
                [
                    (
                        f"{b('move_up')} {b('move_down')} {b('move_left')} {b('move_right')}",
                        "Move mouse cursor",
                    ),
                    (b("click"), "Left click"),
                    (b("right_click"), "Right click"),
                    (f"{b('scroll_up')} {b('scroll_down')}", "Scroll up / down"),
                    (f"{b('back')} {b('forward')}", "Mouse back / forward"),
                    (b("toggle_drag"), "Toggle mouse drag"),
                ],
            ),
            (
                "Media Control",
                [
                    (f"{b('volume_up')} {b('volume_down')}", "Volume Up / Down"),
                    (b("volume_mute"), "Toggle Mute"),
                ],
            ),
            (
                "Hints",
                [
                    (b("toggle_all_hints"), "Toggle hint labels (2s)"),
                    ("1-3 chars", "Click hinted element"),
                    ("Esc", "Reset typing / Dismiss hints"),
                ],
            ),
            (
                "Modes & Tools",
                [
                    (b("insert_mode"), "Enter Insert mode"),
                    (b("open_launcher"), "Open app launcher"),
                    (
                        config.format_hotkey(*hotkey.get_hotkey(), use_symbols=True),
                        "Return to Normal mode",
                    ),
                ],
            ),
            (
                "Global Window Tiling",
                [
                    (
                        f"{b('win_half_up')} {b('win_half_down')} {b('win_half_left')} {b('win_half_right')}",
                        "Tile to half screen",
                    ),
                    (
                        f"{b('win_tile_1')} {b('win_tile_2')} {b('win_tile_3')} {b('win_tile_4')}",
                        "Tile to quarter screen",
                    ),
                    (
                        f"{b('win_sixth_tl')} {b('win_sixth_tc')} {b('win_sixth_tr')}",
                        "Tile to top sixth",
                    ),
                    (
                        f"{b('win_sixth_bl')} {b('win_sixth_bc')} {b('win_sixth_br')}",
                        "Tile to bottom sixth",
                    ),
                    (f"{b('win_center')} {b('win_maximize')}", "Center / Maximize window"),
                ],
            ),
        ]
        return sections

    def reload_keybindings(self):
        """Load keybindings from config and rebuild lookup tables."""
        cfg = config.load()
        self._auto_insert_enabled = cfg.get("auto_insert_mode", True)
        self._global_tiling_bindings = cfg.get("global_tiling_bindings", {})
        self._bindings = config.load_keybindings()
        self._binding_lookup = _build_binding_lookup(self._bindings)
        self._hint_chars = _compute_hint_chars(self._bindings)
        if self._on_config_change:
            self._on_config_change()

    def _on_watermark_hide(self, mode):
        """Called when the watermark disappears."""
        # When normal mode is re-entered, check if we should auto-enter insert mode
        if self._auto_insert_enabled:
            element = accessibility.get_focused_element()
            if element:
                self._check_focus_and_auto_insert(element)

    # -- Helpers --

    def _notify_mode(self, mode):
        """Notify listener of mode change. mode is 'N', 'I', or None (dismissed)."""
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _hide_all_labels(self):
        """Hide all hint labels."""
        for _, label, _, _ in self.labels:
            label.setHidden_(True)

    def _update_target_app(self):
        """Update target to the current frontmost app (skip self)."""
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front.processIdentifier() != os.getpid():
            self._pid = front.processIdentifier()

    # -- Focus watching --

    def _start_watching_focus(self):
        """Register for workspace app-activation notifications."""
        ws = NSWorkspace.sharedWorkspace()
        self._ws_observer = ws.notificationCenter().addObserverForName_object_queue_usingBlock_(
            "NSWorkspaceDidActivateApplicationNotification",
            None,
            None,
            lambda note: AppHelper.callAfter(self._on_app_activated, note),
        )

    def _on_app_activated(self, note):
        """Called when any app gains focus. Refresh hints for the newly focused app."""
        if not self.window or self._clicking:
            return
        activated = note.userInfo()["NSWorkspaceApplicationKey"]
        activated_pid = activated.processIdentifier()
        if activated_pid == os.getpid():
            return

        self._hide_all_labels()
        if self._hints_visible:
            self.refresh(pid=activated_pid, auto_hide_after=2.0)
        else:
            self._pid = activated_pid

        if self._auto_insert_enabled:
            # Clear suppression when switching apps/windows
            self._last_auto_element = None
            # Start polling for this new app if not already polling
            if not self._is_polling:
                AppHelper.callAfter(self._poll_focus)

    def _poll_focus(self):
        """Poll the current focused element to detect input fields."""
        if not self.window or not self._auto_insert_enabled:
            self._is_polling = False
            return

        element = accessibility.get_focused_element()
        if element:
            # Only care about elements belonging to the active app
            if accessibility.get_element_pid(element) == self._pid:
                self._check_focus_and_auto_insert(element)
            else:
                self._check_focus_and_auto_insert(None)
        else:
            self._check_focus_and_auto_insert(None)

        # Re-schedule poll
        self._is_polling = True
        AppHelper.callLater(0.5, self._poll_focus)

    def _check_focus_and_auto_insert(self, element):
        """Enter insert mode if element is a text field, exit if it was auto-entered."""
        if not self.window or not self._auto_insert_enabled:
            return

        if element is None:
            if self._insert_mode and self._auto_insert:
                log.info("Auto-normal: focus lost")
                self._exit_insert_mode()
            self._last_auto_element = None
            return

        is_input = accessibility.is_input_element(element)
        if is_input:
            if not self._insert_mode:
                # Only re-trigger auto-insert if we are on a NEW element
                if element != self._last_auto_element:
                    log.info("Auto-insert: focus on input")
                    self._last_auto_element = element
                    self.enter_insert_mode(auto=True)
            else:
                # If we are in insert mode (manual or auto), update the last seen element
                self._last_auto_element = element
        else:
            if self._insert_mode and self._auto_insert:
                log.info("Auto-normal: focus lost from input")
                self._exit_insert_mode()
            self._last_auto_element = None

    def suspend_tap(self, suspended=True):
        """Temporarily suspend or resume the normal mode event tap and overlay window."""
        if suspended:
            self._remove_normal_tap()
            if self.window:
                self.window.orderOut_(None)
        else:
            if self.window:
                self.window.orderFrontRegardless()
            if not self._insert_mode:
                self._install_normal_tap()

    # -- Global event tap for normal mode --

    def _install_normal_tap(self):
        """Install a global event tap for normal mode key capture."""
        if self._normal_tap:
            return
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            self._normal_tap_callback,
            None,
        )
        if tap:
            self._normal_tap = tap
            self._normal_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), self._normal_source, Quartz.kCFRunLoopCommonModes
            )
            Quartz.CGEventTapEnable(tap, True)

    def _remove_normal_tap(self):
        """Remove the normal mode event tap."""
        if self._normal_tap:
            Quartz.CGEventTapEnable(self._normal_tap, False)
            if self._normal_source:
                Quartz.CFRunLoopRemoveSource(
                    Quartz.CFRunLoopGetCurrent(), self._normal_source, Quartz.kCFRunLoopCommonModes
                )
                self._normal_source = None
            self._normal_tap = None

    def _normal_tap_callback(self, proxy, event_type, event, refcon):
        """Global tap that handles all normal-mode keys."""
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            if self._normal_tap:
                Quartz.CGEventTapEnable(self._normal_tap, True)
            return event

        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        cmd = bool(flags & _CMD_FLAG)
        alt = bool(flags & _ALT_FLAG)
        ctrl = bool(flags & _CTRL_FLAG)
        shift = bool(flags & _SHIFT_FLAG)

        # 1. Block Escape and reset typing or drag
        if code == _KEY_ESCAPE:
            AppHelper.callAfter(self._watermark.hide)
            AppHelper.callAfter(self.cancel_drag)
            if not self._dragging:
                AppHelper.callAfter(self.reset_typing)
            return None

        if code == _KEY_BACKSPACE:
            AppHelper.callAfter(self.cancel_drag)
            AppHelper.callAfter(self.backspace)
            return None

        # 2. Check for registered normal mode actions
        action = self._binding_lookup.get((code, ctrl, shift, cmd, alt))
        repeat = bool(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat))

        if action:
            # If any action is triggered, hide the cheat sheet if it's up
            if self._cheat_sheet.is_visible() and action != "toggle_cheat_sheet":
                AppHelper.callAfter(self._cheat_sheet.hide)

            # Auto-cancel drag for non-movement actions
            if action not in ("move_left", "move_down", "move_up", "move_right", "toggle_drag"):
                AppHelper.callAfter(self.cancel_drag)

            if action == "move_left":
                AppHelper.callAfter(
                    lambda: self._mouse_ctrl.move_relative(-1, 0, repeat, self._dragging)
                )
            elif action == "move_down":
                AppHelper.callAfter(
                    lambda: self._mouse_ctrl.move_relative(0, 1, repeat, self._dragging)
                )
            elif action == "move_up":
                AppHelper.callAfter(
                    lambda: self._mouse_ctrl.move_relative(0, -1, repeat, self._dragging)
                )
            elif action == "move_right":
                AppHelper.callAfter(
                    lambda: self._mouse_ctrl.move_relative(1, 0, repeat, self._dragging)
                )
            elif action == "scroll_up":
                AppHelper.callAfter(lambda: self.scroll(3))
            elif action == "scroll_down":
                AppHelper.callAfter(lambda: self.scroll(-3))
            elif action == "volume_up":
                AppHelper.callAfter(self.volume_up)
            elif action == "volume_down":
                AppHelper.callAfter(self.volume_down)
            elif action == "volume_mute":
                AppHelper.callAfter(self.volume_mute)
            elif action == "back":
                AppHelper.callAfter(self.mouse_back)
            elif action == "forward":
                AppHelper.callAfter(self.mouse_forward)
            elif action == "click":
                AppHelper.callAfter(self.click_at_cursor)
            elif action == "right_click":
                AppHelper.callAfter(self.right_click_at_cursor)
            elif action == "toggle_drag":
                AppHelper.callAfter(self.toggle_drag)
            elif action == "insert_mode":
                AppHelper.callAfter(self.enter_insert_mode)
            elif action == "toggle_hints" or action == "toggle_all_hints":
                AppHelper.callAfter(self.toggle_all_hints)
            elif action == "toggle_cheat_sheet":
                sections = self._get_cheat_sheet_sections()
                AppHelper.callAfter(lambda: self._cheat_sheet.toggle(sections))
            elif action == "open_launcher":
                AppHelper.callAfter(self._open_launcher)
            return None

        # 4. Passthrough for Cmd/Alt combinations not caught above
        # This allows standard macOS shortcuts and our global tiling hotkeys (Cmd+Ctrl+...)
        # to reach the system and the other event tap.
        if cmd or alt:
            return event

        # No binding matched.
        if self._cheat_sheet.is_visible():
            AppHelper.callAfter(self._cheat_sheet.hide)
            return None

        # 5. Block and show overlay for remaining navigation and alphanumeric keys
        is_nav = code in _NAV_KEYCODES
        is_char = code in _KEYCODE_TO_CHAR

        if is_nav or is_char:
            AppHelper.callAfter(self.cancel_drag)

            if is_char and self._hints_visible:
                char = _KEYCODE_TO_CHAR[code].upper()
                # Hint chars are letters only. Non-alpha keys (space/tab/return) still show overlay if not bound.
                if char in _ALL_ALPHA:
                    AppHelper.callAfter(lambda c=char: self.type_char(c))
                    return None

            # Show "NORMAL" watermark for any other blocked navigation/alphanumeric key
            AppHelper.callAfter(lambda: self._watermark.set_mode("NORMAL"))
            return None

        return event

    def reset_typing(self):
        """Reset currently typed hint characters and show all labels. If none typed, dismiss hints."""
        if self._cheat_sheet.is_visible():
            AppHelper.callAfter(self._cheat_sheet.hide)
            # If we were just hiding the cheat sheet, don't dismiss hints too on first Esc
            if not self.typed:
                return

        if not self._hints_visible:
            self.typed = ""
            return

        if not self.typed:
            # Hints are visible but nothing is typed: dismiss them.
            self._hide_all_labels()
            self._hints_visible = False
            return

        # Hints are visible and something is typed: reset the filter.
        self.typed = ""
        for _, label, _, _ in self.labels:
            label.setHidden_(False)
        self._hints_gen += 1  # Cancel current timer
        # Start a fresh 2s timer for the reset state
        gen = self._hints_gen
        AppHelper.callLater(2.0, lambda: self._auto_hide_hints(gen))

    # -- Show / Normal mode --

    def return_to_normal(self):
        """Return to normal mode from insert mode (called by hotkey)."""
        if self._insert_mode:
            AppHelper.callAfter(self._exit_insert_mode)

    def show(self):
        """Activate the overlay: create window, install tap, start watching focus."""
        self._update_target_app()
        if self._pid:
            log.info("show: pid=%d", self._pid)
        self.window = HintWindow.alloc().init()
        self.window.orderFrontRegardless()
        self._install_normal_tap()
        self._start_watching_focus()

        if self._auto_insert_enabled:
            if not self._is_polling:
                AppHelper.callAfter(self._poll_focus)

        self._watermark.flash()
        self._notify_mode("N")

    # -- Hint population --

    def _get_visible_windows(self):
        """Get visible on-screen windows (excluding our own process)."""
        my_pid = os.getpid()
        win_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        windows = []
        for w in win_list:
            pid = w.get(Quartz.kCGWindowOwnerPID, 0)
            if pid == my_pid:
                continue
            
            # Layer 0 is the standard window layer.
            if w.get(Quartz.kCGWindowLayer, -1) != 0:
                continue
                
            # Filter out tiny windows or empty titles if they seem like non-windows
            bounds = w.get(Quartz.kCGWindowBounds, {})
            if bounds.get("Width", 0) < 100 or bounds.get("Height", 0) < 100:
                continue
                
            # Check AXRole to ensure it's a real window (optional but good)
            windows.append(w)
        return windows

    def _assign_window_hints(self, windows):
        """Assign single-char hints to windows, reusing cached assignments."""
        chars = self._hint_chars
        used = set()
        assignments = []

        available_iter = iter(c for c in chars)

        def next_available():
            while True:
                try:
                    c = next(available_iter)
                except StopIteration:
                    return None
                if c not in used:
                    return c

        new_cache = {}
        for w in windows:
            wid = w.get(Quartz.kCGWindowNumber, 0)
            cached = self._win_hint_cache.get(wid)
            if cached and cached not in used:
                hint = cached
            else:
                hint = next_available()
            if hint:
                used.add(hint)
                new_cache[wid] = hint
                assignments.append((hint, w))

        self._win_hint_cache = new_cache
        return assignments, used

    def _generate_element_hints(self, count, used_chars):
        """Generate two or three-letter hints from chars not used by windows."""
        chars = self._hint_chars
        remaining = [c for c in chars if c not in used_chars]

        # Use two-letter hints if they can fit all elements
        if count <= len(remaining) * len(chars):
            hints = []
            for first in remaining:
                for second in chars:
                    hints.append(first + second)
                    if len(hints) >= count:
                        return hints
            return hints

        # Fall back to three-letter hints
        hints = []
        for first in remaining:
            for second in chars:
                for third in chars:
                    hints.append(first + second + third)
                    if len(hints) >= count:
                        return hints
        return hints

    def _populate(self, elements):
        """Place hint labels on the overlay for elements and visible windows."""
        for _, label, _, _ in self.labels:
            label.removeFromSuperview()
        self.labels = []
        self.typed = ""

        # Reserve at least 10 first-chars for element hints (10 × 19 = 190 or 3,610 hints)
        max_win_hints = len(self._hint_chars) - 10
        windows = self._get_visible_windows()[:max_win_hints]
        win_assignments, used_chars = self._assign_window_hints(windows)
        el_hints = self._generate_element_hints(len(elements), used_chars)

        screen = NSScreen.mainScreen().frame()
        content = self.window.contentView()

        # Compute initial positions for window hints
        win_positions = []
        for hint, w in win_assignments:
            bounds = w[Quartz.kCGWindowBounds]
            cx = bounds["X"] + bounds["Width"] / 2
            cy = bounds["Y"] + bounds["Height"] / 2
            flipped_y = screen.size.height - cy
            win_positions.append((hint, w, cx, flipped_y))

        # Resolve overlaps: offset hints that share the same center
        spacing = WIN_HINT_PADDING_Y * 2 + WIN_HINT_ICON_SIZE + 4
        for i in range(len(win_positions)):
            hi, wi, cxi, cyi = win_positions[i]
            for j in range(i):
                hj, wj, cxj, cyj = win_positions[j]
                if abs(cxi - cxj) < spacing and abs(cyi - cyj) < spacing:
                    # Push this hint below the previous one
                    cyi = cyj - spacing
                    win_positions[i] = (hi, wi, cxi, cyi)

        for hint, w, cx, flipped_y in win_positions:
            pid = w.get(Quartz.kCGWindowOwnerPID, 0)
            view = self._create_window_hint_label(hint, cx, flipped_y, pid)
            content.addSubview_(view)
            self.labels.append((hint, view, w, "window"))

        elements.sort(key=lambda el: (_element_position(el)[1], _element_position(el)[0]))
        for hint, el in zip(el_hints, elements):
            x, y = _element_position(el)
            flipped_y = screen.size.height - y
            label = self._create_hint_label(hint, x, flipped_y)
            content.addSubview_(label)
            self.labels.append((hint, label, el, "element"))

    def _create_hint_label(self, hint_text, x, flipped_y):
        """Create a styled hint label at the given screen position."""
        label = ui.make_label(hint_text, HINT_FONT_SIZE, HINT_BG_COLOR, HINT_TEXT_COLOR)
        frame = label.frame()
        label.setFrame_(
            NSMakeRect(
                x - HINT_PADDING,
                flipped_y - frame.size.height,
                frame.size.width + HINT_PADDING * 2,
                frame.size.height,
            )
        )
        label.setWantsLayer_(True)
        label.layer().setCornerRadius_(HINT_CORNER_RADIUS)
        return label

    def _create_window_hint_label(self, hint_text, cx, flipped_cy, pid):
        """Create a window hint with app icon and label in a rounded box."""
        label = ui.make_label(
            hint_text, WIN_HINT_FONT_SIZE, None, WIN_HINT_TEXT_COLOR, draw_bg=False
        )
        lf = label.frame()

        # Check for icon
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        has_icon = app and app.icon()
        icon_w = (WIN_HINT_ICON_SIZE + WIN_HINT_GAP) if has_icon else 0

        content_w = icon_w + lf.size.width
        content_h = max(WIN_HINT_ICON_SIZE, lf.size.height) if has_icon else lf.size.height
        box_w = WIN_HINT_PADDING_X * 2 + content_w
        box_h = WIN_HINT_PADDING_Y * 2 + content_h

        box = ui.RoundedBoxView.alloc().initWithFrame_color_radius_(
            NSMakeRect(cx - box_w / 2, flipped_cy - box_h / 2, box_w, box_h),
            WIN_HINT_BG_COLOR,
            WIN_HINT_CORNER_RADIUS,
        )

        x_offset = WIN_HINT_PADDING_X
        if has_icon:
            icon_view = NSImageView.alloc().initWithFrame_(
                NSMakeRect(
                    x_offset,
                    (box_h - WIN_HINT_ICON_SIZE) / 2,
                    WIN_HINT_ICON_SIZE,
                    WIN_HINT_ICON_SIZE,
                )
            )
            icon = app.icon()
            icon.setSize_(NSMakeSize(WIN_HINT_ICON_SIZE, WIN_HINT_ICON_SIZE))
            icon_view.setImage_(icon)
            box.addSubview_(icon_view)
            x_offset += WIN_HINT_ICON_SIZE + WIN_HINT_GAP

        label.setFrame_(
            NSMakeRect(x_offset, (box_h - lf.size.height) / 2, lf.size.width, lf.size.height)
        )
        box.addSubview_(label)

        return box

    # -- Scrolling --

    def scroll(self, lines):
        """Scroll the target app. Dismiss hints if they are visible."""
        log.info("scroll: lines=%d", lines)
        mouse.scroll(lines)
        if self._hints_visible:
            self._hide_all_labels()
            self._hints_visible = False
            self.typed = ""
        self._hints_gen += 1  # Cancel any pending auto-hide

    # -- Volume Control --

    def _get_volume_status(self):
        """Get current volume and muted status via osascript."""
        try:
            res = subprocess.run(
                ["osascript", "-e", "get volume settings"], capture_output=True, text=True
            ).stdout.strip()
            # output: output volume:50, input volume:50, alert volume:100, output muted:false
            parts = res.split(",")
            vol = parts[0].split(":")[1]
            muted = parts[3].split(":")[1] == "true"
            return int(vol), muted
        except Exception:
            return None, None

    def _show_volume_watermark(self):
        """Update watermark with current volume level."""
        vol, muted = self._get_volume_status()
        if vol is not None:
            status = f"VOL {vol}%" if not muted else "VOL: MUTED"
            AppHelper.callAfter(lambda: self._watermark.set_mode(status))

    def volume_up(self):
        """Increase system volume via osascript."""
        log.info("volume: up")
        subprocess.run(
            ["osascript", "-e", "set volume output volume (output volume of (get volume settings) + 6)"]
        )
        self._show_volume_watermark()

    def volume_down(self):
        """Decrease system volume via osascript."""
        log.info("volume: down")
        subprocess.run(
            ["osascript", "-e", "set volume output volume (output volume of (get volume settings) - 6)"]
        )
        self._show_volume_watermark()

    def volume_mute(self):
        """Toggle system volume mute via osascript."""
        log.info("volume: toggle mute")
        subprocess.run(
            ["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"]
        )
        self._show_volume_watermark()

    # -- Clicking --

    def mouse_back(self):
        """Send mouse back button to target app."""
        mouse.back_button()

    def mouse_forward(self):
        """Send mouse forward button to target app."""
        mouse.forward_button()

    def click_at_cursor(self):
        """Click at the current cursor position, then dismiss hints."""
        x, y = mouse.get_cursor_position()
        log.info("click: cursor (%.0f, %.0f)", x, y)
        self._click_and_dismiss(x, y)

    def cancel_drag(self):
        """End mouse drag if active."""
        if self._dragging:
            self.toggle_drag()

    def toggle_drag(self):
        """Toggle mouse drag: first call presses mouse down, second releases."""
        x, y = mouse.get_cursor_position()
        if not self._dragging:
            log.info("drag: start (%.0f, %.0f)", x, y)
            mouse.mouse_down(x, y)
            self._dragging = True
            self._notify_mode("D")
            self._watermark.set_mode("DRAG")
        else:
            log.info("drag: end (%.0f, %.0f)", x, y)
            mouse.mouse_up(x, y)
            self._dragging = False
            self._notify_mode("N")
            self._watermark.set_mode("NORMAL")

        if self._hints_visible:
            self._hide_all_labels()
            self._hints_visible = False
            self.typed = ""
        self._hints_gen += 1

    def right_click_at_cursor(self):
        """Right-click at the current cursor position, then dismiss hints."""
        x, y = mouse.get_cursor_position()
        log.info("right_click: cursor (%.0f, %.0f)", x, y)
        self._right_click_and_dismiss(x, y)

    def _click_and_dismiss(self, x, y):
        """Hide hints and click at (x, y) in the target app."""
        self._clicking = True
        self._hide_all_labels()
        mouse.click(x, y)
        self._clicking = False
        self._update_target_app()
        self._hints_visible = False
        self.typed = ""

    def type_char(self, char):
        """Handle a typed letter: filter hints, click if unique match."""
        self.typed += char
        matching = []
        for hint, label, data, kind in self.labels:
            if hint.startswith(self.typed):
                label.setHidden_(False)
                matching.append((hint, label, data, kind))
            else:
                label.setHidden_(True)

        if len(matching) == 1:
            hint, label, data, kind = matching[0]
            if kind == "window":
                self._hide_all_labels()
                self._hints_visible = False
                self.typed = ""
                self._switch_to_window(data)
            else:
                if accessibility.is_element_stale(data["element"]):
                    log.warning("click: element is stale, refreshing")
                    self.refresh()
                    return
                cx, cy = mouse.element_center(data["position"], data["size"])
                log.info(
                    "click: hint=%s role=%s title=%r (%.0f, %.0f)",
                    hint,
                    data["role"],
                    data.get("title", ""),
                    cx,
                    cy,
                )
                self._click_and_dismiss(cx, cy)
        elif len(matching) == 0:
            # No match found - reset typing and show all labels again
            self.typed = ""
            for _, label, _, _ in self.labels:
                label.setHidden_(False)
            self._reset_hints_timer()
        else:
            # Multiple matches - just extend the timer
            self._reset_hints_timer()

    def backspace(self):
        """Remove last typed char and re-show matching hints."""
        if not self.typed:
            return
        self.typed = self.typed[:-1]
        if not self.typed:
            # Show everything
            for _, label, _, _ in self.labels:
                label.setHidden_(False)
        else:
            # Show only matches
            for hint, label, _, _ in self.labels:
                if hint.startswith(self.typed):
                    label.setHidden_(False)
                else:
                    label.setHidden_(True)
        self._reset_hints_timer()

    def _reset_hints_timer(self):
        """Extend the auto-hide timer."""
        if not self._hints_visible:
            return
        self._hints_gen += 1
        gen = self._hints_gen
        # Give them another 2s
        AppHelper.callLater(2.0, lambda: self._auto_hide_hints(gen))

    def _right_click_and_dismiss(self, x, y):
        """Right-click and enter menu mode with a global tap for mouse movement."""
        self._clicking = True
        self._hide_all_labels()
        self._remove_normal_tap()
        mouse.right_click(x, y)
        self._clicking = False
        self._install_menu_tap()

    def _install_menu_tap(self):
        """Install a global event tap to handle keys while a context menu is open."""
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            self._menu_tap_callback,
            None,
        )
        if tap:
            self._menu_tap = tap
            self._menu_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), self._menu_source, Quartz.kCFRunLoopCommonModes
            )
            Quartz.CGEventTapEnable(tap, True)

    def _remove_menu_tap(self):
        """Remove the menu-mode event tap."""
        if self._menu_tap:
            Quartz.CGEventTapEnable(self._menu_tap, False)
            if self._menu_source:
                Quartz.CFRunLoopRemoveSource(
                    Quartz.CFRunLoopGetCurrent(), self._menu_source, Quartz.kCFRunLoopCommonModes
                )
                self._menu_source = None
            self._menu_tap = None

    def _menu_tap_callback(self, proxy, event_type, event, refcon):
        """Global tap that intercepts movement keys during context menu."""
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            if self._menu_tap:
                Quartz.CGEventTapEnable(self._menu_tap, True)
            return event

        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        cmd = bool(flags & _CMD_FLAG)
        alt = bool(flags & _ALT_FLAG)
        ctrl = bool(flags & _CTRL_FLAG)
        shift = bool(flags & _SHIFT_FLAG)
        action = self._binding_lookup.get((code, ctrl, shift, cmd, alt))

        if action == "move_left":
            repeat = bool(
                Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            )
            AppHelper.callAfter(lambda: self._mouse_ctrl.move_relative(-1, 0, repeat))
            return None
        elif action == "move_down":
            repeat = bool(
                Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            )
            AppHelper.callAfter(lambda: self._mouse_ctrl.move_relative(0, 1, repeat))
            return None
        elif action == "move_up":
            repeat = bool(
                Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            )
            AppHelper.callAfter(lambda: self._mouse_ctrl.move_relative(0, -1, repeat))
            return None
        elif action == "move_right":
            repeat = bool(
                Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            )
            AppHelper.callAfter(lambda: self._mouse_ctrl.move_relative(1, 0, repeat))
            return None
        elif action == "click" or code == _KEY_ESCAPE:
            AppHelper.callAfter(self._exit_menu_mode)
            return event

        return event

    def _exit_menu_mode(self):
        """Exit menu mode and reclaim the overlay."""
        self._remove_menu_tap()
        if self.window:
            self._update_target_app()
            self._install_normal_tap()
            if self._hints_visible:
                self.refresh()

    # -- Refresh / Toggle --

    def refresh(self, pid=None, auto_hide_after=None):
        """Re-collect elements and refresh hints. Optionally specify a target PID and auto-hide timer."""
        if pid is not None:
            self._pid = pid
        else:
            self._update_target_app()

        elements = accessibility.get_clickable_elements(self._pid)
        if elements:
            self._populate(elements)
        else:
            for _, label, _, _ in self.labels:
                label.removeFromSuperview()
            self.labels = []
        self._hints_visible = True

        if auto_hide_after:
            self._hints_gen += 1
            gen = self._hints_gen
            AppHelper.callLater(auto_hide_after, lambda: self._auto_hide_hints(gen))

    def toggle_hints(self):
        """Show hints for 2 seconds, or dismiss if already visible."""
        log.info("toggle_hints visible=%s", self._hints_visible)
        if self._hints_visible:
            self._hide_all_labels()
            self._hints_visible = False
        else:
            self.refresh(auto_hide_after=2.0)

    def toggle_all_hints(self):
        """Show hints for all visible apps, or dismiss if already visible."""
        log.info("toggle_all_hints visible=%s", self._hints_visible)
        if self._hints_visible:
            self._hide_all_labels()
            self._hints_visible = False
        else:
            self._refresh_all()
            self._hints_gen += 1
            gen = self._hints_gen
            AppHelper.callLater(4.0, lambda: self._auto_hide_hints(gen))

    def _refresh_all(self):
        """Collect clickable elements from all visible windows."""
        windows = self._get_visible_windows()
        pid_bounds = {}
        for w in windows:
            pid = w.get(Quartz.kCGWindowOwnerPID, 0)
            b = w.get(Quartz.kCGWindowBounds, {})
            bounds = (b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0))
            pid_bounds.setdefault(pid, []).append(bounds)
        elements = accessibility.get_all_clickable_elements(pid_bounds)
        if elements:
            self._populate(elements)
        self._hints_visible = True

    def _auto_hide_hints(self, gen):
        """Hide hints if no new toggle happened since gen."""
        if gen != self._hints_gen or not self.window:
            return
        self._hide_all_labels()
        self._hints_visible = False
        self.typed = ""

    # -- Launcher --

    def _open_launcher(self):
        """Open the Alfred-like app launcher."""
        self._hide_all_labels()
        self._remove_normal_tap()
        self._launcher.show()

    def _on_launcher_dismiss(self):
        """Called when the launcher is dismissed."""
        self._update_target_app()
        self._install_normal_tap()

    # -- Insert mode --

    def enter_insert_mode(self, auto=False):
        """Enter insert mode: prefer current focused window, fallback to window under cursor."""
        if self._insert_mode:
            # If already in manual insert mode, don't downgrade to auto
            if not auto:
                self._auto_insert = False
            return

        self._auto_insert = auto

        # First priority: check if there's already a focused window
        system = AX.AXUIElementCreateSystemWide()
        err, focused_app = AX.AXUIElementCopyAttributeValue(system, "AXFocusedApplication", None)
        has_focused_window = False
        if err == 0 and focused_app:
            err2, focused_win = AX.AXUIElementCopyAttributeValue(
                focused_app, "AXFocusedWindow", None
            )
            if err2 == 0 and focused_win:
                has_focused_window = True

        # Second priority: find and focus window under cursor
        if not has_focused_window:
            mx, my = mouse.get_cursor_position()
            windows = self._get_visible_windows()
            for w in windows:
                b = w.get(Quartz.kCGWindowBounds, {})
                if b.get("X", 0) <= mx <= b.get("X", 0) + b.get("Width", 0) and b.get(
                    "Y", 0
                ) <= my <= b.get("Y", 0) + b.get("Height", 0):
                    self._switch_to_window(w)
                    break

        log.info("mode: INSERT (auto=%s)", auto)
        self._insert_mode = True
        self._notify_mode("I")
        self._remove_normal_tap()
        self._watermark.set_mode("INSERT")

    def _exit_insert_mode(self):
        """Exit insert mode and restore the overlay."""
        log.info("mode: NORMAL")
        self._insert_mode = False
        self._auto_insert = False

        if not self.window:
            self._notify_mode(None)
            return

        self._update_target_app()
        if self._dragging:
            self._notify_mode("D")
            self._watermark.set_mode("DRAG")
        else:
            self._notify_mode("N")
            self._watermark.set_mode("NORMAL")

        self._install_normal_tap()
        self._hide_all_labels()
        self._hints_visible = False

    # -- Window switching helpers --

    def _get_visible_windows(self):
        """Get visible on-screen windows (excluding our own process)."""
        my_pid = os.getpid()
        win_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        windows = []
        for w in win_list:
            pid = w.get(Quartz.kCGWindowOwnerPID, 0)
            if pid == my_pid:
                continue

            # Layer 0 is the standard window layer.
            if w.get(Quartz.kCGWindowLayer, -1) != 0:
                continue

            # Filter out tiny windows
            bounds = w.get(Quartz.kCGWindowBounds, {})
            width = bounds.get("Width", 0)
            height = bounds.get("Height", 0)
            if width < 100 or height < 100:
                continue

            # Most real windows have a name or a non-empty owner name
            owner = w.get(Quartz.kCGWindowOwnerName, "")
            
            # Filter out known "junk" windows
            if owner == "SystemUIServer" or owner == "Window Server":
                continue

            windows.append(w)
        return windows

    def _switch_to_window(self, win_info):
        """Activate the app owning the given window and raise it."""
        log.info("switch: window=%s", win_info.get(Quartz.kCGWindowOwnerName, "?"))
        bounds = win_info[Quartz.kCGWindowBounds]
        cx = bounds["X"] + bounds["Width"] / 2
        cy = bounds["Y"] + bounds["Height"] / 2
        mouse.move_cursor(cx, cy)
        pid = win_info[Quartz.kCGWindowOwnerPID]
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app:
            # 2 = NSApplicationActivateIgnoringOtherApps
            app.activateWithOptions_(2)
            self._pid = pid
        wid = win_info.get(Quartz.kCGWindowNumber, 0)
        self._raise_window(pid, bounds, wid)

    def _raise_window(self, pid, bounds, target_wid=0):
        """Raise a specific window by matching its position/size via Accessibility."""
        app_ref = AX.AXUIElementCreateApplication(pid)
        err, windows = AX.AXUIElementCopyAttributeValue(app_ref, "AXWindows", None)
        if err != 0 or not windows:
            log.info("_raise_window: no AXWindows for pid=%s (err=%s)", pid, err)
            return

        tx, ty = bounds["X"], bounds["Y"]
        tw, th = bounds["Width"], bounds["Height"]

        # 1. Match by window ID (most reliable)
        if target_wid:
            for w in windows:
                if accessibility.get_window_id(w) == target_wid:
                    AX.AXUIElementPerformAction(w, "AXRaise")
                    # Also try to set as main and focused
                    AX.AXUIElementSetAttributeValue(w, "AXMain", True)
                    AX.AXUIElementSetAttributeValue(w, "AXFocused", True)
                    log.info("  [wid=%s] MATCHED by window-ID — raised and focused", target_wid)
                    return

        # 2. Fallback to bounds matching
        for i, win in enumerate(windows):
            err, pos = AX.AXUIElementCopyAttributeValue(win, "AXPosition", None)
            err2, size = AX.AXUIElementCopyAttributeValue(win, "AXSize", None)
            if err == 0 and err2 == 0:
                _, p = AX.AXValueGetValue(pos, AX.kAXValueCGPointType, None)
                _, s = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
                if (
                    abs(p.x - tx) < 10
                    and abs(p.y - ty) < 10
                    and abs(s.width - tw) < 10
                    and abs(s.height - th) < 10
                ):
                    AX.AXUIElementPerformAction(win, "AXRaise")
                    AX.AXUIElementSetAttributeValue(win, "AXMain", True)
                    AX.AXUIElementSetAttributeValue(win, "AXFocused", True)
                    log.info("  [%d] MATCHED by bounds (%.0f,%.0f) — raised and focused", i, tx, ty)
                    return
        log.info("_raise_window: no match found")
