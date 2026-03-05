"""Vimium-style hint overlay for clicking UI elements."""

import logging
import os
import objc
import Quartz
from AppKit import (
    NSBezierPath,
    NSScreen,
    NSColor,
    NSFont,
    NSTextField,
    NSView,
    NSWindow,
    NSMakeRect,
    NSBackingStoreBuffered,
    NSApplication,
    NSFloatingWindowLevel,
    NSWorkspace,
    NSRunningApplication,
)
from PyObjCTools import AppHelper
import ApplicationServices as AX
from . import accessibility
from . import config
from . import mouse

log = logging.getLogger(__name__)

# Hint label style
HINT_FONT_SIZE = 12
HINT_BG_COLOR = (0.15, 0.15, 0.15, 0.85)  # dark gray
HINT_TEXT_COLOR = (1.0, 1.0, 1.0, 1.0)  # white
HINT_PADDING = 4
HINT_CORNER_RADIUS = 4

# Window hint style
WIN_HINT_FONT_SIZE = 28
WIN_HINT_BG_COLOR = (0.15, 0.15, 0.15, 0.85)  # dark gray
WIN_HINT_TEXT_COLOR = (1.0, 1.0, 1.0, 1.0)  # white
WIN_HINT_PADDING = 12
WIN_HINT_CORNER_RADIUS = 10

# Watermark style
_WM_VM_COLOR = (0.9, 0.70)  # white, alpha
_WM_VM_FONT_SIZE = 48
_WM_MODE_COLOR = (0.9, 0.60)
_WM_MODE_FONT_SIZE = 16
_WM_FLASH_DURATION = 2.0  # seconds to show watermark
_WM_BOX_BG = (0.0, 0.0, 0.0, 0.50)  # black, semi-transparent
_WM_BOX_CORNER = 14
_WM_BOX_PAD_X = 24
_WM_BOX_PAD_Y = 16


# macOS hardware key codes → Latin letters (input-source-independent)
_KEYCODE_TO_CHAR = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x",
    8: "c", 9: "v", 11: "b", 12: "q", 13: "w", 14: "e", 15: "r",
    16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
    30: "]", 31: "o", 32: "u", 33: "[", 34: "i", 35: "p", 37: "l",
    38: "j", 40: "k", 41: ";", 42: "'", 43: ",", 44: "/", 45: "n",
    46: "m", 47: ".",
}
_KEY_ESCAPE = 53
_KEY_BACKSPACE = 51
_MOUSE_S0 = 10        # base sensitivity (pixels per step)
_MOUSE_STEP_MAX = 100  # cap on maximum step size
_MOUSE_RAMP_FRAMES = 30  # frames to reach max speed
_CTRL_FLAG = 1 << 18  # NSEventModifierFlagControl

_ALL_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _build_binding_lookup(bindings):
    """Build a dict mapping (keycode, ctrl_bool) → action from keybindings config."""
    lookup = {}
    for action, spec in bindings.items():
        specs = spec if isinstance(spec, list) else [spec]
        for s in specs:
            key = (s["keycode"], bool(s.get("ctrl", False)))
            lookup[key] = action
    return lookup


def _compute_hint_chars(bindings):
    """Return hint chars string excluding keys bound to actions."""
    bound_keycodes = set()
    for spec in bindings.values():
        specs = spec if isinstance(spec, list) else [spec]
        for s in specs:
            if not s.get("ctrl"):
                bound_keycodes.add(s["keycode"])
    excluded = {_KEYCODE_TO_CHAR.get(kc, "").upper() for kc in bound_keycodes}
    return "".join(c for c in _ALL_ALPHA if c not in excluded)


def _element_position(el):
    """Extract (x, y) from an element's AXPosition."""
    err, pos = AX.AXValueGetValue(el["position"], AX.kAXValueCGPointType, None)
    return (pos.x, pos.y)


def _make_label(text, font_size, bg_color, text_color, draw_bg=True, bold=True):
    """Create a styled NSTextField label."""
    label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
    label.setStringValue_(text)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setBezeled_(False)
    label.setDrawsBackground_(draw_bg)
    if draw_bg:
        label.setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(*bg_color)
        )
    label.setTextColor_(
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*text_color)
        if len(text_color) == 4
        else NSColor.colorWithWhite_alpha_(*text_color)
    )
    font = NSFont.boldSystemFontOfSize_(font_size) if bold else NSFont.systemFontOfSize_(font_size)
    label.setFont_(font)
    label.sizeToFit()
    return label


class _RoundedBoxView(NSView):
    """NSView that draws a rounded semi-transparent rectangle."""

    def drawRect_(self, rect):
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*_WM_BOX_BG).set()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), _WM_BOX_CORNER, _WM_BOX_CORNER,
        )
        path.fill()


def _add_watermark(container, screen_size, mode_text):
    """Add VM + mode watermark labels in a rounded box. Returns (box, vm_label, mode_label)."""
    vm = _make_label("VM", _WM_VM_FONT_SIZE, None, _WM_VM_COLOR, draw_bg=False)
    vm_f = vm.frame()

    mode = _make_label(mode_text, _WM_MODE_FONT_SIZE, None, _WM_MODE_COLOR, draw_bg=False, bold=False)
    mode.setAlignment_(1)  # center
    mode_f = mode.frame()

    # Size the box to fit both labels + padding
    content_w = max(vm_f.size.width, mode_f.size.width + 4)
    content_h = vm_f.size.height + mode_f.size.height + 4
    box_w = content_w + _WM_BOX_PAD_X * 2
    box_h = content_h + _WM_BOX_PAD_Y * 2

    cx = screen_size.width / 2
    cy = screen_size.height / 2

    box = _RoundedBoxView.alloc().initWithFrame_(
        NSMakeRect(cx - box_w / 2, cy - box_h / 2, box_w, box_h)
    )

    # Position labels relative to box
    vm.setFrameOrigin_(((box_w - vm_f.size.width) / 2,
                        _WM_BOX_PAD_Y + mode_f.size.height + 4))
    mw = mode_f.size.width + 4
    mode.setFrame_(NSMakeRect((box_w - mw) / 2, _WM_BOX_PAD_Y, mw, mode_f.size.height))

    box.addSubview_(vm)
    box.addSubview_(mode)
    container.addSubview_(box)
    return box, vm, mode


class HintWindow(NSWindow):
    """Transparent full-screen window that captures keystrokes."""

    def initWithOverlay_(self, overlay):
        screen = NSScreen.mainScreen().frame()
        self = objc.super(HintWindow, self).initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, screen.size.width, screen.size.height),
            0,  # borderless
            NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self.overlay = overlay
        self.setLevel_(NSFloatingWindowLevel)
        self.setOpaque_(False)
        self.setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.0, 0.01))
        self.setIgnoresMouseEvents_(True)
        self.setHasShadow_(False)

        self._screen_size = screen.size
        self._wm_box, self._vm_label, self._mode_label = _add_watermark(
            self.contentView(), screen.size, "NORMAL"
        )
        self._wm_box.setHidden_(True)
        self._flash_gen = 0

        return self

    def _set_mode(self, text):
        self._mode_label.setStringValue_(text)
        self._mode_label.sizeToFit()
        f = self._mode_label.frame()
        w = f.size.width + 4
        box_w = self._wm_box.frame().size.width
        self._mode_label.setFrame_(NSMakeRect((box_w - w) / 2,
                                               _WM_BOX_PAD_Y, w, f.size.height))
        self._flash_watermark()

    def _flash_watermark(self):
        """Show watermark box for _WM_FLASH_DURATION seconds then hide."""
        self._flash_gen += 1
        gen = self._flash_gen
        self._wm_box.setHidden_(False)

        def _hide():
            if self._flash_gen == gen:
                self._wm_box.setHidden_(True)

        AppHelper.callLater(_WM_FLASH_DURATION, _hide)

    def canBecomeKeyWindow(self):
        return not self.overlay._insert_mode

    def keyDown_(self, event):
        code = event.keyCode()
        flags = event.modifierFlags()
        cmd = flags & (1 << 20)  # NSEventModifierFlagCommand
        ctrl = bool(flags & _CTRL_FLAG)
        # Pass Cmd+key combos through to the target app (Cmd+W, Cmd+Tab, Cmd+`, etc.)
        if cmd and not ctrl:
            self.overlay.passthrough_key(event)
            return
        if code == _KEY_ESCAPE:
            return
        if code == _KEY_BACKSPACE:
            self.overlay.backspace()
            return

        action = self.overlay._binding_lookup.get((code, ctrl))
        if action == "move_left":
            self.overlay.move_mouse(-1, 0, event.isARepeat())
        elif action == "move_down":
            self.overlay.move_mouse(0, 1, event.isARepeat())
        elif action == "move_up":
            self.overlay.move_mouse(0, -1, event.isARepeat())
        elif action == "move_right":
            self.overlay.move_mouse(1, 0, event.isARepeat())
        elif action == "scroll_up":
            self.overlay.scroll(3)
        elif action == "scroll_down":
            self.overlay.scroll(-3)
        elif action == "back":
            self.overlay.mouse_back()
        elif action == "forward":
            self.overlay.mouse_forward()
        elif action == "click":
            self.overlay.click_at_cursor()
        elif action == "insert_mode":
            self.overlay.enter_insert_mode()
        elif action == "toggle_hints":
            self.overlay.toggle_hints()
        elif code in _KEYCODE_TO_CHAR and _KEYCODE_TO_CHAR[code].isalpha():
            self.overlay.type_char(_KEYCODE_TO_CHAR[code].upper())


class HintOverlay:
    def __init__(self, on_mode_change=None):
        self._on_mode_change = on_mode_change
        self.window = None
        self.labels = []  # [(hint_string, NSTextField, data, kind)]
        self.typed = ""
        self._prev_app = None
        self._pid = None
        self._scroll_gen = 0
        self._scroll_pending = False
        self._ws_observer = None
        self._clicking = False
        self._hints_visible = False
        self._hints_gen = 0
        self._win_hint_cache = {}  # kCGWindowNumber -> hint char
        self._mouse_dir = None
        self._mouse_repeat_count = 0
        self._insert_mode = False
        self._insert_tap = None
        self._insert_source = None
        self._insert_window = None
        self.reload_keybindings()

    def reload_keybindings(self):
        """Load keybindings from config and rebuild lookup tables."""
        self._bindings = config.load_keybindings()
        self._binding_lookup = _build_binding_lookup(self._bindings)
        self._hint_chars = _compute_hint_chars(self._bindings)

    # -- Helpers --

    def _notify_mode(self, mode):
        """Notify listener of mode change. mode is 'N', 'I', or None (dismissed)."""
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _activate_overlay_window(self):
        """Activate the overlay window so it captures keystrokes."""
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1)  # Accessory — enables key window
        self.window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

    def _hide_all_labels(self):
        """Hide all hint labels."""
        for _, label, _, _ in self.labels:
            label.setHidden_(True)

    def _update_target_app(self):
        """Update target to the current frontmost app (skip self)."""
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front.processIdentifier() != os.getpid():
            self._prev_app = front
            self._pid = front.processIdentifier()

    # -- Show / Dismiss --

    def toggle(self):
        """Cycle: deactivated→activate, normal→deactivate, insert→normal."""
        if not self.window:
            self.show()
        elif self._insert_mode:
            AppHelper.callAfter(self._exit_insert_mode)
        else:
            self.dismiss()

    def show(self):
        """Show hint overlay on clickable elements of the frontmost app."""
        my_pid = os.getpid()
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front.processIdentifier() == my_pid:
            return
        self._prev_app = front
        self._pid = self._prev_app.processIdentifier()
        log.info("show: app=%s pid=%d", front.localizedName(), self._pid)
        elements = accessibility.get_clickable_elements(self._pid)

        if not elements:
            log.info("show: no clickable elements found")
            return

        self._center_cursor_on_app()
        self.window = HintWindow.alloc().initWithOverlay_(self)
        self._populate(elements)
        self._hide_all_labels()
        self._activate_overlay_window()
        self._start_watching_focus()
        self.window._flash_watermark()
        self._notify_mode("N")

    def dismiss(self):
        """Dismiss the overlay without action."""
        log.info("dismiss")
        if self._insert_mode:
            self._exit_insert_mode()
        self._hide_insert_watermark()
        self._stop_watching_focus()
        if self.window:
            self.window.orderOut_(None)
            self.window = None
        self.labels = []
        self.typed = ""
        self._win_hint_cache = {}
        NSApplication.sharedApplication().setActivationPolicy_(2)  # Prohibited
        if self._prev_app:
            self._prev_app.activateWithOptions_(0)
            self._prev_app = None
        self._notify_mode(None)

    # -- Cursor --

    def _center_cursor_on_app(self):
        """Move the cursor to the center of the focused window of the target app."""
        app_ref = AX.AXUIElementCreateApplication(self._pid)
        err, focused = AX.AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
        if err != 0 or focused is None:
            return
        err, pos = AX.AXUIElementCopyAttributeValue(focused, "AXPosition", None)
        _, size = AX.AXUIElementCopyAttributeValue(focused, "AXSize", None)
        if pos is None or size is None:
            return
        _, p = AX.AXValueGetValue(pos, AX.kAXValueCGPointType, None)
        _, s = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
        mouse.move_cursor(p.x + s.width / 2, p.y + s.height / 2)

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

    def _stop_watching_focus(self):
        """Remove the workspace observer."""
        if self._ws_observer:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self._ws_observer)
            self._ws_observer = None

    def _on_app_activated(self, note):
        """Called when any app gains focus. Refresh hints for the newly focused app."""
        if not self.window or self._clicking or self._insert_mode:
            return
        activated = note.userInfo()["NSWorkspaceApplicationKey"]
        activated_pid = activated.processIdentifier()
        if activated_pid == os.getpid():
            return
        self._hide_all_labels()
        self._prev_app = activated
        self._pid = activated_pid
        if self._hints_visible:
            elements = accessibility.get_clickable_elements(self._pid)
            if elements:
                self._populate(elements)
        self._activate_overlay_window()

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
            if w.get(Quartz.kCGWindowLayer, -1) != 0:
                continue
            bounds = w.get(Quartz.kCGWindowBounds, {})
            if bounds.get("Width", 0) == 0 or bounds.get("Height", 0) == 0:
                continue
            windows.append(w)
        return windows

    def _assign_window_hints(self, windows):
        """Assign single-char hints to windows, reusing cached assignments."""
        chars = self._hint_chars
        used = set()
        assignments = []

        # Single pass: reuse cache or assign new
        available_iter = iter(c for c in chars)
        available_next = [None]  # mutable container for the next available char

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
        """Generate two-letter hints from chars not used by windows."""
        chars = self._hint_chars
        remaining = [c for c in chars if c not in used_chars]
        hints = []
        for first in remaining:
            for second in chars:
                hints.append(first + second)
                if len(hints) >= count:
                    return hints
        return hints

    def _populate(self, elements):
        """Place hint labels on the overlay for elements and visible windows."""
        for _, label, _, _ in self.labels:
            label.removeFromSuperview()
        self.labels = []
        self.typed = ""

        # Reserve at least 10 first-chars for element hints (10 × 19 = 190 hints)
        max_win_hints = len(self._hint_chars) - 10
        windows = self._get_visible_windows()[:max_win_hints]
        win_assignments, used_chars = self._assign_window_hints(windows)
        el_hints = self._generate_element_hints(len(elements), used_chars)

        screen = NSScreen.mainScreen().frame()
        content = self.window.contentView()

        for hint, w in win_assignments:
            bounds = w[Quartz.kCGWindowBounds]
            cx = bounds["X"] + bounds["Width"] / 2
            cy = bounds["Y"] + bounds["Height"] / 2
            flipped_y = screen.size.height - cy
            label = self._create_window_hint_label(hint, cx, flipped_y)
            content.addSubview_(label)
            self.labels.append((hint, label, w, "window"))

        elements.sort(key=lambda el: (_element_position(el)[1], _element_position(el)[0]))
        for hint, el in zip(el_hints, elements):
            x, y = _element_position(el)
            flipped_y = screen.size.height - y
            label = self._create_hint_label(hint, x, flipped_y)
            content.addSubview_(label)
            self.labels.append((hint, label, el, "element"))

    def _create_hint_label(self, hint_text, x, flipped_y):
        """Create a styled hint label at the given screen position."""
        label = _make_label(hint_text, HINT_FONT_SIZE, HINT_BG_COLOR, HINT_TEXT_COLOR)
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

    def _create_window_hint_label(self, hint_text, cx, flipped_cy):
        """Create a large centered hint label for window switching."""
        label = _make_label(hint_text, WIN_HINT_FONT_SIZE, WIN_HINT_BG_COLOR, WIN_HINT_TEXT_COLOR)
        label.setAlignment_(1)  # NSTextAlignmentCenter
        frame = label.frame()
        w = frame.size.width + WIN_HINT_PADDING * 2
        h = frame.size.height
        label.setFrame_(NSMakeRect(cx - w / 2, flipped_cy - h / 2, w, h))
        label.setWantsLayer_(True)
        label.layer().setCornerRadius_(WIN_HINT_CORNER_RADIUS)
        return label

    # -- Mouse movement --

    def move_mouse(self, dx, dy, repeat=False):
        """Move the mouse cursor with easeOutCubic acceleration."""
        direction = (dx, dy)
        if repeat and self._mouse_dir == direction:
            self._mouse_repeat_count = min(self._mouse_repeat_count + 1, _MOUSE_RAMP_FRAMES)
        else:
            self._mouse_repeat_count = 0
        self._mouse_dir = direction
        t = self._mouse_repeat_count / _MOUSE_RAMP_FRAMES
        ease = 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2  # easeInOutCubic
        step = int(_MOUSE_S0 + (_MOUSE_STEP_MAX - _MOUSE_S0) * ease)
        x, y = mouse.get_cursor_position()
        mouse.move_cursor(x + dx * step, y + dy * step)

    # -- Scrolling --

    def scroll(self, lines):
        """Scroll the target app. Hints hide during scrolling, refresh when idle."""
        log.info("scroll: lines=%d", lines)
        mouse.scroll(lines)
        if not self._scroll_pending:
            self._hide_all_labels()
        self._scroll_gen += 1
        self._scroll_pending = True
        gen = self._scroll_gen
        AppHelper.callLater(1.0, lambda: self._refresh_if_idle(gen))

    def _refresh_if_idle(self, gen):
        """Refresh hints only if no further scrolling happened since gen."""
        if gen != self._scroll_gen or not self.window:
            return
        self._scroll_pending = False
        if self._hints_visible:
            elements = accessibility.get_clickable_elements(self._pid)
            self._populate(elements)

    # -- Key passthrough --

    def passthrough_key(self, event):
        """Forward a key event to the target app by briefly activating it."""
        cg_event = event.CGEvent()
        if not cg_event or not self._prev_app:
            return
        # Hide overlay so target app can receive focus and process the key
        char = _KEYCODE_TO_CHAR.get(Quartz.CGEventGetIntegerValueField(cg_event, Quartz.kCGKeyboardEventKeycode), "?")
        log.info("passthrough: key=%s", char)
        self._clicking = True
        if self.window:
            self.window.orderOut_(None)
        self._prev_app.activateWithOptions_(0)
        # Post both keydown and keyup
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, cg_event)
        keyup = Quartz.CGEventCreateCopy(cg_event)
        Quartz.CGEventSetType(keyup, Quartz.kCGEventKeyUp)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, keyup)
        # Reclaim overlay after a short delay to let the app process the key
        AppHelper.callLater(0.1, self._reclaim_and_refresh)

    # -- Clicking --

    def mouse_back(self):
        """Send mouse back button to target app."""
        mouse.back_button()

    def mouse_forward(self):
        """Send mouse forward button to target app."""
        mouse.forward_button()

    def click_at_cursor(self):
        """Click at the current cursor position, then refresh hints."""
        x, y = mouse.get_cursor_position()
        log.info("click: cursor (%.0f, %.0f)", x, y)
        self._click_and_refresh(x, y)

    def _click_and_refresh(self, x, y):
        """Hide hints, click at (x, y) in the target app, then refresh hints."""
        self._clicking = True
        self._hide_all_labels()
        if self._prev_app:
            self._prev_app.activateWithOptions_(0)
        self._perform_click_and_refresh(x, y)

    def _perform_click_and_refresh(self, x, y):
        """Execute the click and refresh hints afterward."""
        if not self.window:
            return
        self.window.orderOut_(None)
        mouse.click(x, y)
        self._reclaim_and_refresh()

    def _reclaim_and_refresh(self):
        """Reclaim key window and refresh hints after a click."""
        self._clicking = False
        if not self.window:
            return
        self._update_target_app()
        self._activate_overlay_window()
        if self._hints_visible:
            self.refresh()

    # -- Refresh / Toggle --

    def refresh(self):
        """Re-collect elements and refresh hints."""
        elements = accessibility.get_clickable_elements(self._pid)
        if elements:
            self._populate(elements)
        self._hints_visible = True

    def toggle_hints(self):
        """Show hints for 2 seconds, or dismiss if already visible."""
        log.info("toggle_hints visible=%s", self._hints_visible)
        if self._hints_visible:
            self._hide_all_labels()
            self._hints_visible = False
        else:
            self.refresh()
            self._hints_gen += 1
            gen = self._hints_gen
            AppHelper.callLater(2.0, lambda: self._auto_hide_hints(gen))

    def _auto_hide_hints(self, gen):
        """Hide hints if no new toggle happened since gen."""
        if gen != self._hints_gen or not self.window:
            return
        self._hide_all_labels()
        self._hints_visible = False

    # -- Insert mode --

    def enter_insert_mode(self):
        """Enter insert mode: pass all keys to the target app until Escape."""
        if self._insert_mode:
            return
        log.info("mode: INSERT")
        self._insert_mode = True
        self._notify_mode("I")

        if self.window:
            self.window.orderOut_(None)
        self._show_insert_watermark()

        NSApplication.sharedApplication().setActivationPolicy_(2)  # Prohibited
        if self._prev_app:
            self._prev_app.activateWithOptions_(0)

        # Install a global tap to catch Escape
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            self._insert_tap_callback,
            None,
        )
        if tap:
            self._insert_tap = tap
            self._insert_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), self._insert_source, Quartz.kCFRunLoopCommonModes
            )
            Quartz.CGEventTapEnable(tap, True)

    def _insert_tap_callback(self, proxy, event_type, event, refcon):
        """Global tap callback that catches Escape to exit insert mode."""
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            if self._insert_tap:
                Quartz.CGEventTapEnable(self._insert_tap, True)
            return event
        return event

    def _exit_insert_mode(self):
        """Exit insert mode and restore the overlay."""
        log.info("mode: NORMAL")
        self._insert_mode = False
        self._notify_mode("N")

        if self._insert_tap:
            Quartz.CGEventTapEnable(self._insert_tap, False)
            if self._insert_source:
                Quartz.CFRunLoopRemoveSource(
                    Quartz.CFRunLoopGetCurrent(), self._insert_source, Quartz.kCFRunLoopCommonModes
                )
                self._insert_source = None
            self._insert_tap = None

        if not self.window:
            return

        self._update_target_app()
        self._hide_insert_watermark()
        self.window._set_mode("NORMAL")
        self._activate_overlay_window()
        self._hide_all_labels()
        self._hints_visible = False

    def _show_insert_watermark(self):
        """Show a passive floating watermark for INSERT mode, auto-hides after 2s."""
        self._hide_insert_watermark()
        self._insert_wm_gen = getattr(self, "_insert_wm_gen", 0) + 1
        gen = self._insert_wm_gen
        screen = NSScreen.mainScreen().frame()
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, screen.size.width, screen.size.height),
            0, NSBackingStoreBuffered, False,
        )
        win.setLevel_(NSFloatingWindowLevel)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.0, 0.0))
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(False)
        _add_watermark(win.contentView(), screen.size, "INSERT")
        win.orderFrontRegardless()
        self._insert_window = win

        def _hide():
            if getattr(self, "_insert_wm_gen", 0) == gen:
                self._hide_insert_watermark()

        AppHelper.callLater(_WM_FLASH_DURATION, _hide)

    def _hide_insert_watermark(self):
        """Remove the INSERT watermark window."""
        if self._insert_window:
            self._insert_window.orderOut_(None)
            self._insert_window = None

    # -- Window switching --

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
            app.activateWithOptions_(0)
            self._prev_app = app
            self._pid = pid
        self._raise_window(pid, bounds)
        self._activate_and_refresh()

    def _raise_window(self, pid, bounds):
        """Raise a specific window by matching its position/size via Accessibility."""
        app_ref = AX.AXUIElementCreateApplication(pid)
        err, windows = AX.AXUIElementCopyAttributeValue(app_ref, "AXWindows", None)
        if err != 0 or not windows:
            return
        tx, ty = bounds["X"], bounds["Y"]
        tw, th = bounds["Width"], bounds["Height"]
        for win in windows:
            err, pos = AX.AXUIElementCopyAttributeValue(win, "AXPosition", None)
            _, size = AX.AXUIElementCopyAttributeValue(win, "AXSize", None)
            if pos is None or size is None:
                continue
            _, p = AX.AXValueGetValue(pos, AX.kAXValueCGPointType, None)
            _, s = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
            if abs(p.x - tx) < 2 and abs(p.y - ty) < 2 and abs(s.width - tw) < 2 and abs(s.height - th) < 2:
                AX.AXUIElementPerformAction(win, "AXRaise")
                return

    def _activate_and_refresh(self):
        """Re-activate overlay and refresh element hints after window switch."""
        if not self.window:
            return
        self._activate_overlay_window()
        self.refresh()

    # -- Hint typing --

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
                self._switch_to_window(data)
            else:
                cx, cy = mouse.element_center(data["position"], data["size"])
                log.info("click: hint=%s role=%s title=%r (%.0f, %.0f)", hint, data["role"], data.get("title", ""), cx, cy)
                self._click_and_refresh(cx, cy)
        elif len(matching) == 0:
            self.typed = ""
            for _, label, _, _ in self.labels:
                label.setHidden_(False)

    def backspace(self):
        """Remove last typed char and re-show matching hints."""
        if not self.typed:
            return
        self.typed = self.typed[:-1]
        for hint, label, _, _ in self.labels:
            if hint.startswith(self.typed):
                label.setHidden_(False)
            else:
                label.setHidden_(True)
