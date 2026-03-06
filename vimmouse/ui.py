"""Reusable UI components for VimMouse."""

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
_WM_VM_COLOR = (0.9, 0.70)  # white, alpha
_WM_VM_FONT_SIZE = 48
_WM_MODE_COLOR = (0.9, 0.60)
_WM_MODE_FONT_SIZE = 16
_WM_FLASH_DURATION = 2.0  # seconds to show watermark
_WM_BOX_BG = (0.0, 0.0, 0.0, 0.50)  # black, semi-transparent
_WM_BOX_CORNER = 14
_WM_BOX_PAD_X = 24
_WM_BOX_PAD_Y = 16

def make_label(text, font_size, bg_color, text_color, draw_bg=True, bold=True):
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
            self.bounds(), self._corner_radius, self._corner_radius,
        )
        path.fill()

class WatermarkManager:
    """Manages a floating watermark window for mode transitions."""
    def __init__(self, mode_text="NORMAL"):
        self._window = None
        self._flash_gen = 0
        self._mode_text = mode_text
        self._setup_window()

    def _setup_window(self):
        screen = NSScreen.mainScreen().frame()
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, screen.size.width, screen.size.height),
            0, NSBackingStoreBuffered, False,
        )
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.0, 0.0))
        self._window.setIgnoresMouseEvents_(True)
        self._window.setHasShadow_(False)
        self._add_watermark(screen.size)
        self._box.setHidden_(True)

    def _add_watermark(self, screen_size):
        vm = make_label("VM", _WM_VM_FONT_SIZE, None, _WM_VM_COLOR, draw_bg=False)
        vm_f = vm.frame()

        self._mode_label = make_label(self._mode_text, _WM_MODE_FONT_SIZE, None, _WM_MODE_COLOR, draw_bg=False, bold=False)
        self._mode_label.setAlignment_(1)  # center
        mode_f = self._mode_label.frame()

        content_w = max(vm_f.size.width, mode_f.size.width + 4)
        content_h = vm_f.size.height + mode_f.size.height + 4
        box_w = content_w + _WM_BOX_PAD_X * 2
        box_h = content_h + _WM_BOX_PAD_Y * 2

        cx, cy = screen_size.width / 2, screen_size.height / 2
        self._box = RoundedBoxView.alloc().initWithFrame_color_radius_(
            NSMakeRect(cx - box_w / 2, cy - box_h / 2, box_w, box_h),
            _WM_BOX_BG, _WM_BOX_CORNER
        )

        vm.setFrameOrigin_(((box_w - vm_f.size.width) / 2,
                            _WM_BOX_PAD_Y + mode_f.size.height + 4))
        mw = mode_f.size.width + 4
        self._mode_label.setFrame_(NSMakeRect((box_w - mw) / 2, _WM_BOX_PAD_Y, mw, mode_f.size.height))

        self._box.addSubview_(vm)
        self._box.addSubview_(self._mode_label)
        self._window.contentView().addSubview_(self._box)

    def set_mode(self, text):
        self._mode_label.setStringValue_(text)
        self._mode_label.sizeToFit()
        f = self._mode_label.frame()
        w = f.size.width + 4
        box_w = self._box.frame().size.width
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

        AppHelper.callLater(_WM_FLASH_DURATION, _hide)

    def hide(self):
        self._flash_gen += 1
        self._box.setHidden_(True)
        self._window.orderOut_(None)
