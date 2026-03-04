"""Vimium-style hint overlay for clicking UI elements."""

import os
import objc
from AppKit import (
    NSScreen,
    NSColor,
    NSFont,
    NSTextField,
    NSWindow,
    NSMakeRect,
    NSBackingStoreBuffered,
    NSApplication,
    NSFloatingWindowLevel,
    NSWorkspace,
)
from PyObjCTools import AppHelper
import ApplicationServices as AX
import accessibility
import mouse

# Hint label style
HINT_FONT_SIZE = 11
HINT_BG_COLOR = (1.0, 0.9, 0.0, 0.9)  # yellow
HINT_TEXT_COLOR = (0.0, 0.0, 0.0, 1.0)  # black
HINT_PADDING = 2


_HINT_CHARS = "ABCDEFGIMNOPQRSTUVWXYZ"  # excludes H, J, K, L (used for movement)

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
_KEY_H = 4
_KEY_J = 38
_KEY_K = 40
_KEY_L = 37
_KEY_B = 11
_KEY_F = 3
_KEY_SLASH = 44
_KEY_SPACE = 49
_MOUSE_STEP = 20
_CTRL_FLAG = 1 << 18  # NSEventModifierFlagControl


def _generate_hints(count):
    """Generate hint strings. Uses single letters when they suffice, otherwise all two-letter."""
    chars = _HINT_CHARS
    if count <= len(chars):
        return list(chars[:count])
    # All two-letter to avoid prefix conflicts (e.g. "A" matching "AA", "AB", …)
    hints = []
    for first in chars:
        for second in chars:
            hints.append(first + second)
            if len(hints) >= count:
                return hints
    return hints


def _element_position(el):
    """Extract (x, y) from an element's AXPosition."""
    err, pos = AX.AXValueGetValue(el["position"], AX.kAXValueCGPointType, None)
    return (pos.x, pos.y)


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

        # Centered "VM" watermark
        vm_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
        vm_label.setStringValue_("VM")
        vm_label.setEditable_(False)
        vm_label.setSelectable_(False)
        vm_label.setBezeled_(False)
        vm_label.setDrawsBackground_(False)
        vm_label.setTextColor_(NSColor.colorWithWhite_alpha_(0.5, 0.30))
        vm_label.setFont_(NSFont.boldSystemFontOfSize_(48))
        vm_label.sizeToFit()
        f = vm_label.frame()
        vm_label.setFrameOrigin_(((screen.size.width - f.size.width) / 2,
                                   (screen.size.height - f.size.height) / 2))
        self.contentView().addSubview_(vm_label)

        return self

    def canBecomeKeyWindow(self):
        return True

    def resignKeyWindow(self):
        objc.super(HintWindow, self).resignKeyWindow()

    def keyDown_(self, event):
        code = event.keyCode()
        flags = event.modifierFlags()
        ctrl = flags & _CTRL_FLAG
        if code == _KEY_ESCAPE:
            self.overlay.dismiss()
        elif code == _KEY_BACKSPACE:
            self.overlay.backspace()
        elif ctrl and code == _KEY_B:
            self.overlay.scroll(3)
        elif ctrl and code == _KEY_F:
            self.overlay.scroll(-3)
        elif code == _KEY_H:
            self.overlay.move_mouse(-_MOUSE_STEP, 0)
        elif code == _KEY_J:
            self.overlay.move_mouse(0, _MOUSE_STEP)
        elif code == _KEY_K:
            self.overlay.move_mouse(0, -_MOUSE_STEP)
        elif code == _KEY_L:
            self.overlay.move_mouse(_MOUSE_STEP, 0)
        elif code == _KEY_SPACE:
            self.overlay.click_at_cursor()
        elif code == _KEY_SLASH:
            self.overlay.refresh()
        elif code in _KEYCODE_TO_CHAR and _KEYCODE_TO_CHAR[code].isalpha():
            self.overlay.type_char(_KEYCODE_TO_CHAR[code].upper())


class HintOverlay:
    def __init__(self):
        self.window = None
        self.labels = []  # (hint_string, NSTextField, element)
        self.typed = ""
        self._prev_app = None
        self._pid = None
        self._scroll_gen = 0
        self._scroll_pending = False
        self._ws_observer = None
        self._clicking = False

    def _activate_overlay_window(self):
        """Activate the overlay window so it captures keystrokes."""
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1)  # Accessory — enables key window
        self.window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

    def show(self):
        """Show hint overlay on clickable elements of the frontmost app."""
        my_pid = os.getpid()
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front.processIdentifier() == my_pid:
            # Already showing hints on ourselves — skip
            return
        self._prev_app = front
        self._pid = self._prev_app.processIdentifier()
        elements = accessibility.get_clickable_elements(self._pid)

        if not elements:
            print("No clickable elements found.")
            return

        # Move cursor to center of the frontmost app's focused window
        self._center_cursor_on_app()

        self.window = HintWindow.alloc().initWithOverlay_(self)
        self._populate(elements)
        self._activate_overlay_window()

        # Watch for target app gaining focus (alt-tab, mouse click, etc.)
        self._start_watching_focus()

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
        if not self.window or self._clicking:
            return
        activated = note.userInfo()["NSWorkspaceApplicationKey"]
        activated_pid = activated.processIdentifier()
        # Ignore our own activation (we're about to reclaim key window)
        if activated_pid == os.getpid():
            return
        # Clear old hints immediately
        for _, label, _ in self.labels:
            label.setHidden_(True)
        # Switch target to the newly focused app
        self._prev_app = activated
        self._pid = activated_pid
        elements = accessibility.get_clickable_elements(self._pid)
        if elements:
            self._populate(elements)
        self._activate_overlay_window()

    def _populate(self, elements):
        """Place hint labels on the overlay for the given elements."""
        # Clear existing labels
        for _, label, _ in self.labels:
            label.removeFromSuperview()
        self.labels = []
        self.typed = ""

        elements.sort(key=lambda el: _element_position(el))
        hints = _generate_hints(len(elements))
        screen = NSScreen.mainScreen().frame()
        content = self.window.contentView()

        for hint, el in zip(hints, elements):
            x, y = _element_position(el)
            flipped_y = screen.size.height - y
            label = self._create_hint_label(hint, x, flipped_y)
            content.addSubview_(label)
            self.labels.append((hint, label, el))

    def _create_hint_label(self, hint_text, x, flipped_y):
        """Create a styled hint label at the given screen position."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
        label.setStringValue_(hint_text)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(True)
        label.setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(*HINT_BG_COLOR)
        )
        label.setTextColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(*HINT_TEXT_COLOR)
        )
        label.setFont_(NSFont.boldSystemFontOfSize_(HINT_FONT_SIZE))
        label.sizeToFit()

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
        label.layer().setCornerRadius_(3)
        label.layer().setBorderWidth_(0.5)
        label.layer().setBorderColor_(
            NSColor.colorWithWhite_alpha_(0.0, 0.3).CGColor()
        )
        return label

    def move_mouse(self, dx, dy):
        """Move the mouse cursor by (dx, dy) pixels."""
        x, y = mouse.get_cursor_position()
        mouse.move_cursor(x + dx, y + dy)

    def scroll(self, lines):
        """Scroll the target app. Hints hide during scrolling, refresh when idle."""
        mouse.scroll(lines)
        # Hide hints on first scroll
        if not self._scroll_pending:
            for _, label, _ in self.labels:
                label.setHidden_(True)
        # Bump the generation so earlier scheduled refreshes become no-ops
        self._scroll_gen += 1
        self._scroll_pending = True
        gen = self._scroll_gen
        AppHelper.callLater(1.0, lambda: self._refresh_if_idle(gen))

    def _refresh_if_idle(self, gen):
        """Refresh hints only if no further scrolling happened since gen."""
        if gen != self._scroll_gen or not self.window:
            return
        self._scroll_pending = False
        elements = accessibility.get_clickable_elements(self._pid)
        self._populate(elements)

    def click_at_cursor(self):
        """Click at the current cursor position, then refresh hints."""
        x, y = mouse.get_cursor_position()
        print(f"[space click] ({x:.0f}, {y:.0f})")
        self._click_and_refresh(x, y)

    def _click_and_refresh(self, x, y):
        """Hide hints, click at (x, y) in the target app, then refresh hints."""
        self._clicking = True
        for _, label, _ in self.labels:
            label.setHidden_(True)
        # Give focus to target app so click lands correctly
        if self._prev_app:
            self._prev_app.activateWithOptions_(0)
        AppHelper.callLater(0.15, lambda: self._perform_click_and_refresh(x, y))

    def _perform_click_and_refresh(self, x, y):
        """Execute the click and refresh hints afterward."""
        if not self.window:
            return
        # Hide overlay so the click lands on the target app
        self.window.orderOut_(None)
        mouse.click(x, y)
        AppHelper.callLater(0.3, self._reclaim_and_refresh)

    def _reclaim_and_refresh(self):
        """Reclaim key window and refresh hints after a click."""
        self._clicking = False
        if not self.window:
            return
        # Update target to whichever app is now frontmost
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front.processIdentifier() != os.getpid():
            self._prev_app = front
            self._pid = front.processIdentifier()
        self.refresh()
        self._activate_overlay_window()

    def refresh(self):
        """Re-collect elements and refresh hints."""
        elements = accessibility.get_clickable_elements(self._pid)
        if elements:
            self._populate(elements)

    def dismiss(self):
        """Dismiss the overlay without action."""
        self._stop_watching_focus()
        if self.window:
            self.window.orderOut_(None)
            self.window = None
        self.labels = []
        self.typed = ""
        NSApplication.sharedApplication().setActivationPolicy_(2)  # Prohibited
        if self._prev_app:
            self._prev_app.activateWithOptions_(0)
            self._prev_app = None

    def type_char(self, char):
        """Handle a typed letter: filter hints, click if unique match."""
        self.typed += char
        matching = []
        for hint, label, el in self.labels:
            if hint.startswith(self.typed):
                label.setHidden_(False)
                matching.append((hint, label, el))
            else:
                label.setHidden_(True)

        if len(matching) == 1:
            hint, label, el = matching[0]
            cx, cy = mouse.element_center(el["position"], el["size"])
            print(f"[hint {hint}] role={el['role']} title={el.get('title', '')!r} desc={el.get('description', '')!r} ({cx:.0f}, {cy:.0f})")
            self._click_and_refresh(cx, cy)
        elif len(matching) == 0:
            # No match — reset typed filter and re-show all hints
            self.typed = ""
            for h, lbl, _ in self.labels:
                lbl.setHidden_(False)

    def backspace(self):
        """Remove last typed char and re-show matching hints."""
        if not self.typed:
            return
        self.typed = self.typed[:-1]
        for hint, label, el in self.labels:
            if hint.startswith(self.typed):
                label.setHidden_(False)
            else:
                label.setHidden_(True)
