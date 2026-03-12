"""Reusable UI components for VimLayer."""

import objc
from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSTextField,
    NSView,
    NSWindow,
    NSMakeRect,
    NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSScreen,
)
from PyObjCTools import AppHelper

# Watermark style defaults
_WM_VL_COLOR = (0.9, 0.70)  # white, alpha
_WM_VL_FONT_SIZE = 48
_WM_MODE_COLOR = (0.9, 0.60)
_WM_MODE_FONT_SIZE = 16
_WM_FLASH_DURATION = 2.0  # seconds to show watermark
_WM_BOX_BG = (0.0, 0.0, 0.0, 0.50)  # black, semi-transparent
_WM_BOX_CORNER = 14
_WM_BOX_PAD_X = 24
_WM_BOX_PAD_Y = 16

# Cheat sheet style defaults
_CS_BG_COLOR = (0.05, 0.05, 0.05, 0.95)
_CS_TEXT_COLOR = (0.95, 0.95, 0.95, 1.0)
_CS_DIM_COLOR = (0.6, 0.6, 0.6, 1.0)
_CS_ACCENT_COLOR = (0.3, 0.6, 1.0, 1.0)
_CS_CORNER = 16
_CS_PAD = 25
_CS_TITLE_SIZE = 22
_CS_SECTION_SIZE = 13
_CS_KEY_SIZE = 12
_CS_DESC_SIZE = 12
_CS_WIDTH = 520


def make_label(text, font_size, bg_color, text_color, draw_bg=True, bold=True):
    """Create a styled NSTextField label."""
    label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
    label.setStringValue_(text)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setBezeled_(False)
    label.setDrawsBackground_(draw_bg)
    if draw_bg and bg_color:
        label.setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(*bg_color))
    if text_color:
        if len(text_color) == 4:
            label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(*text_color))
        else:
            label.setTextColor_(NSColor.colorWithWhite_alpha_(*text_color))
    font = NSFont.boldSystemFontOfSize_(font_size) if bold else NSFont.systemFontOfSize_(font_size)
    label.setFont_(font)
    label.sizeToFit()
    return label


class RoundedBoxView(NSView):
    """NSView that draws a rounded semi-transparent rectangle."""

    def initWithFrame_color_radius_(self, frame, color, radius):
        self = objc.super(RoundedBoxView, self).initWithFrame_(frame)
        if self:
            self._bg_color = color
            self._corner_radius = radius
        return self

    def drawRect_(self, rect):
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*self._bg_color).set()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(),
            self._corner_radius,
            self._corner_radius,
        )
        path.fill()


class WatermarkManager:
    """Manages a floating watermark window for mode transitions."""

    def __init__(self, mode_text="NORMAL", on_hide=None):
        self._window = None
        self._flash_gen = 0
        self._mode_text = mode_text
        self._on_hide = on_hide
        self._setup_window()

    def _setup_window(self):
        screen = NSScreen.mainScreen().frame()
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, screen.size.width, screen.size.height),
            0,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.0, 0.0))
        self._window.setIgnoresMouseEvents_(True)
        self._window.setHasShadow_(False)
        self._add_watermark(screen.size)
        self._box.setHidden_(True)

    def _add_watermark(self, screen_size):
        vl = make_label("VL", _WM_VL_FONT_SIZE, None, _WM_VL_COLOR, draw_bg=False)
        vl_f = vl.frame()

        self._mode_label = make_label(
            self._mode_text, _WM_MODE_FONT_SIZE, None, _WM_MODE_COLOR, draw_bg=False, bold=False
        )
        self._mode_label.setAlignment_(1)  # center
        mode_f = self._mode_label.frame()

        content_w = max(vl_f.size.width, mode_f.size.width + 4)
        content_h = vl_f.size.height + mode_f.size.height + 4
        box_w = content_w + _WM_BOX_PAD_X * 2
        box_h = content_h + _WM_BOX_PAD_Y * 2

        cx, cy = screen_size.width / 2, screen_size.height / 2
        self._box = RoundedBoxView.alloc().initWithFrame_color_radius_(
            NSMakeRect(cx - box_w / 2, cy - box_h / 2, box_w, box_h), _WM_BOX_BG, _WM_BOX_CORNER
        )

        vl.setFrameOrigin_(((box_w - vl_f.size.width) / 2, _WM_BOX_PAD_Y + mode_f.size.height + 4))
        mw = mode_f.size.width + 4
        self._mode_label.setFrame_(
            NSMakeRect((box_w - mw) / 2, _WM_BOX_PAD_Y, mw, mode_f.size.height)
        )

        self._box.addSubview_(vl)
        self._box.addSubview_(self._mode_label)
        self._window.contentView().addSubview_(self._box)

    def set_mode(self, text):
        self._mode_label.setStringValue_(text)
        self._mode_label.sizeToFit()
        f = self._mode_label.frame()
        w = f.size.width + 4

        # Dynamically resize the box to fit new text if it's wider than original content
        screen = NSScreen.mainScreen().frame()
        vl_f = self._box.subviews()[0].frame()  # "VL" label is first subview
        content_w = max(vl_f.size.width, w)
        box_w = content_w + _WM_BOX_PAD_X * 2
        box_h = self._box.frame().size.height

        cx, cy = screen.size.width / 2, screen.size.height / 2
        self._box.setFrame_(NSMakeRect(cx - box_w / 2, cy - box_h / 2, box_w, box_h))

        # Re-center "VL" and the mode label
        self._box.subviews()[0].setFrameOrigin_(((box_w - vl_f.size.width) / 2, vl_f.origin.y))
        self._mode_label.setFrame_(NSMakeRect((box_w - w) / 2, _WM_BOX_PAD_Y, w, f.size.height))

        self.flash()

    def flash(self):
        self._flash_gen += 1
        gen = self._flash_gen
        self._box.setHidden_(False)
        self._window.orderFrontRegardless()

        def _hide():
            if self._flash_gen == gen:
                self._box.setHidden_(True)
                self._window.orderOut_(None)
                if self._on_hide:
                    self._on_hide(self._mode_label.stringValue())

        AppHelper.callLater(_WM_FLASH_DURATION, _hide)

    def hide(self):
        self._flash_gen += 1
        self._box.setHidden_(True)
        self._window.orderOut_(None)
        if self._on_hide:
            self._on_hide(self._mode_label.stringValue())


class CheatSheetView(NSView):
    """Rich overlay showing all shortcuts in a clean single-column layout."""

    def initWithFrame_sections_(self, frame, sections):
        self = objc.super(CheatSheetView, self).initWithFrame_(frame)
        if self:
            self._sections = sections
            self._setup_ui()
        return self

    def _setup_ui(self):
        w, h = self.frame().size.width, self.frame().size.height
        y = h - _CS_PAD

        # Title
        title = make_label("VimLayer Shortcuts", _CS_TITLE_SIZE, None, _CS_TEXT_COLOR, draw_bg=False)
        title.setFrameOrigin_((_CS_PAD, y - title.frame().size.height))
        self.addSubview_(title)
        
        hint = make_label("Esc to close", 11, None, _CS_DIM_COLOR, draw_bg=False, bold=False)
        hint.setFrameOrigin_((w - _CS_PAD - hint.frame().size.width, y - title.frame().size.height + 4))
        self.addSubview_(hint)
        
        y -= title.frame().size.height + 30

        for section_title, keys in self._sections:
            sec = make_label(
                section_title.upper(), _CS_SECTION_SIZE, None, _CS_ACCENT_COLOR, draw_bg=False
            )
            sec.setFrameOrigin_((_CS_PAD, y - sec.frame().size.height))
            self.addSubview_(sec)
            y -= sec.frame().size.height + 12

            for key_text, desc_text in keys:
                # Key label: Right-aligned in a 140px wide slot
                key = make_label(key_text, _CS_KEY_SIZE, None, _CS_TEXT_COLOR, draw_bg=False)
                kw = key.frame().size.width
                key.setFrameOrigin_((_CS_PAD + 140 - kw, y - key.frame().size.height))
                self.addSubview_(key)

                # Description label: Left-aligned with a gap
                desc = make_label(
                    desc_text, _CS_DESC_SIZE, None, _CS_TEXT_COLOR, draw_bg=False, bold=False
                )
                desc.setFrameOrigin_((_CS_PAD + 155, y - desc.frame().size.height))
                self.addSubview_(desc)

                y -= max(key.frame().size.height, desc.frame().size.height) + 10

            y -= 20

    def drawRect_(self, rect):
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*_CS_BG_COLOR).set()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(),
            _CS_CORNER,
            _CS_CORNER,
        )
        path.fill()


class CheatSheetOverlay:
    """Manages the visibility of the shortcut cheat sheet."""

    def __init__(self):
        self._window = None

    def toggle(self, sections):
        if self._window and self._window.isVisible():
            self.hide()
        else:
            self.show(sections)

    def show(self, sections):
        if self._window:
            self._window.orderOut_(None)
            self._window = None

        screen = NSScreen.mainScreen().frame()

        # Calculate height for single column
        total_items = sum(len(k) for _, k in sections)
        h = 100 + (len(sections) * 45) + (total_items * 24)
        h = min(h, screen.size.height - 100)

        win_rect = NSMakeRect(
            (screen.size.width - _CS_WIDTH) / 2, (screen.size.height - h) / 2, _CS_WIDTH, h
        )

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            win_rect, 0, NSBackingStoreBuffered, False
        )
        self._window.setLevel_(NSFloatingWindowLevel + 1)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setIgnoresMouseEvents_(True)
        self._window.setHasShadow_(True)

        view = CheatSheetView.alloc().initWithFrame_sections_(
            NSMakeRect(0, 0, _CS_WIDTH, h), sections
        )
        self._window.setContentView_(view)
        self._window.orderFrontRegardless()

    def hide(self):
        if self._window:
            self._window.orderOut_(None)

    def is_visible(self):
        return self._window and self._window.isVisible()
