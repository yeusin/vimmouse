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
        return self

    def canBecomeKeyWindow(self):
        return True

    def resignKeyWindow(self):
        objc.super(HintWindow, self).resignKeyWindow()
        self.overlay.dismiss()

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

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1)  # Accessory — enables key window
        self.window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

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
            # Convert from top-left screen coords to bottom-left (AppKit)
            flipped_y = screen.size.height - y

            label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
            label.setStringValue_(hint)
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

            content.addSubview_(label)
            self.labels.append((hint, label, el))

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
        """Click at the current cursor position and dismiss."""
        x, y = mouse.get_cursor_position()
        self.dismiss()
        AppHelper.callLater(0.15, mouse.click, x, y)

    def refresh(self):
        """Re-collect elements and refresh hints."""
        elements = accessibility.get_clickable_elements(self._pid)
        if elements:
            self._populate(elements)

    def dismiss(self):
        """Dismiss the overlay without action."""
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
            self.dismiss()
            # Delay click to let the target app regain focus
            AppHelper.callLater(0.15, mouse.click, cx, cy)
        elif len(matching) == 0:
            # No match — dismiss
            self.dismiss()

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
