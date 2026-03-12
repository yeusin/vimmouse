"""Settings window with hotkey recorder and key binding configuration."""

import objc
import Quartz
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSBezelStyleSmallSquare,
    NSButton,
    NSColor,
    NSEvent,
    NSFont,
    NSKeyDownMask,
    NSMakeRect,
    NSScrollView,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

from . import config
from . import hotkey
from .hotkey import MODIFIER_MASK

# Human-readable labels for keybinding actions
_ACTION_LABELS = {
    "move_left": "Mouse Left",
    "move_down": "Mouse Down",
    "move_up": "Mouse Up",
    "move_right": "Mouse Right",
    "scroll_up": "Scroll Up",
    "scroll_down": "Scroll Down",
    "toggle_all_hints": "Toggle Hints",
    "toggle_cheat_sheet": "Cheat Sheet",
    "click": "Click",
    "insert_mode": "Insert Mode",
    "forward": "Forward",
    "back": "Back",
    "right_click": "Right Click",
    "toggle_drag": "Toggle Drag",
    "open_launcher": "App Launcher",
}

_GLOBAL_TILING_LABELS = {
    "win_half_left": "Global Tile Left",
    "win_half_right": "Global Tile Right",
    "win_half_up": "Global Tile Top",
    "win_half_down": "Global Tile Bottom",
    "win_maximize": "Global Maximize",
    "win_center": "Global Center",
    "win_tile_1": "Global Quarter \u2196",
    "win_tile_2": "Global Quarter \u2197",
    "win_tile_3": "Global Quarter \u2199",
    "win_tile_4": "Global Quarter \u2198",
    "win_sixth_tl": "Global Sixth \u2196",
    "win_sixth_tc": "Global Sixth \u2191",
    "win_sixth_tr": "Global Sixth \u2197",
    "win_sixth_bl": "Global Sixth \u2199",
    "win_sixth_bc": "Global Sixth \u2193",
    "win_sixth_br": "Global Sixth \u2198",
}


class HotkeyRecorderField(NSTextField):
    """Text field that starts recording on click. Uses NSEvent local monitor
    to capture key events, bypassing the responder chain so Cmd+key combos
    aren't swallowed by the menu system."""

    def initWithFrame_(self, frame):
        self = objc.super(HotkeyRecorderField, self).initWithFrame_(frame)
        if self is None:
            return None
        self._recording = False
        self._monitor = None
        self._keycode = None
        self._flags = 0
        self.setEditable_(False)
        self.setAlignment_(1)  # center
        return self

    def mouseDown_(self, event):
        if self._recording:
            return
        self._recording = True
        hotkey.suspend(True)
        self.setStringValue_("Press shortcut...")
        # Capture self in a closure — avoids PyObjC trying to treat the
        # handler as an Objective-C method.
        field = self

        def handle(event):
            keycode = event.keyCode()
            flags = event.modifierFlags() & MODIFIER_MASK
            if not flags:
                return event
            field._keycode = keycode
            field._flags = flags
            field._stopRecording()
            field.setStringValue_(config.format_hotkey(keycode, flags))
            return None

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSKeyDownMask, handle)

    def _stopRecording(self):
        if self._monitor is not None:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        self._recording = False
        hotkey.suspend(False)


class KeyRecorderField(NSTextField):
    """Text field that records a single key press (with optional Ctrl modifier).
    Unlike HotkeyRecorderField, this accepts bare keys without requiring modifiers."""

    def initWithFrame_(self, frame):
        self = objc.super(KeyRecorderField, self).initWithFrame_(frame)
        if self is None:
            return None
        self._recording = False
        self._monitor = None
        self._keycode = None
        self._ctrl = False
        self._shift = False
        self.setEditable_(False)
        self.setAlignment_(1)  # center
        return self

    def mouseDown_(self, event):
        if self._recording:
            return
        self._recording = True
        hotkey.suspend(True)
        self.setStringValue_("Press key...")
        field = self

        def handle(event):
            keycode = event.keyCode()
            # Ignore modifier-only presses
            if keycode in (54, 55, 56, 57, 58, 59, 60, 61, 62, 63):
                return event
            mods = event.modifierFlags()
            ctrl = bool(mods & Quartz.kCGEventFlagMaskControl)
            shift = bool(mods & Quartz.kCGEventFlagMaskShift)
            field._keycode = keycode
            field._ctrl = ctrl
            field._shift = shift
            field._stopRecording()
            spec = {"keycode": keycode, "ctrl": ctrl, "shift": shift}
            field.setStringValue_(config.format_binding(spec))
            return None

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSKeyDownMask, handle)

    def _stopRecording(self):
        if self._monitor is not None:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        self._recording = False
        hotkey.suspend(False)


_ROW_H = 30
_MAX_KEYS_PER_ACTION = 4
_LABEL_W = 100
_REC_W = 65
_BTN_W = 20
_SLOT_W = _REC_W + _BTN_W + 4  # recorder + × button + gap
_KEYS_X = _LABEL_W + 10  # where key slots start


class SettingsController(NSObject):
    """Controller for the settings window."""

    def init(self):
        self = objc.super(SettingsController, self).init()
        if self is None:
            return None
        self._window = None
        self._recorder = None
        self._key_recorders = {}  # action -> [KeyRecorderField, ...]
        self._global_recorders = {}  # action -> HotkeyRecorderField
        self._doc_view = None
        self._actions = list(_ACTION_LABELS.keys())
        self._global_actions = list(_GLOBAL_TILING_LABELS.keys())
        self._overlay = None  # set externally to reload bindings on save
        return self

    def showWindow(self):
        if self._overlay:
            self._overlay.suspend_tap(True)

        if self._window is not None:
            self._refresh_values()
            NSApp.setActivationPolicy_(1)
            self._window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
            return

        cfg = config.load()
        bindings = config.load_keybindings()
        global_bindings = cfg.get("global_tiling_bindings", {})
        
        # Window layout: shortcut row + separator + scrollable bindings + buttons
        shortcut_area = 50
        separator = 10
        button_area = 45
        
        # Count rows: normal actions + global actions + headers
        row_count = len(self._actions) + len(self._global_actions) + 2 # headers
        scroll_h = row_count * _ROW_H
        win_h = min(600, shortcut_area + separator + scroll_h + button_area)

        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 420, win_h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        w.setTitle_("VimLayer Settings")
        w.setReleasedWhenClosed_(False)
        w.setDelegate_(self)
        w.center()
        content = w.contentView()
        y = win_h - 40  # current y, top-down

        # --- Normal mode shortcut ---
        label = NSTextField.labelWithString_("Switch to Normal Mode:")
        label.setFrame_(NSMakeRect(15, y, 140, 20))
        content.addSubview_(label)

        recorder = HotkeyRecorderField.alloc().initWithFrame_(NSMakeRect(160, y, 185, 20))
        keycode, flags = hotkey.get_hotkey()
        recorder.setStringValue_(config.format_hotkey(keycode, flags))
        recorder.setFont_(NSFont.systemFontOfSize_(13))
        content.addSubview_(recorder)
        self._recorder = recorder
        y -= shortcut_area - 20 + separator

        # --- Separator ---
        sep_label = NSTextField.labelWithString_("Key Bindings:")
        sep_label.setFont_(NSFont.boldSystemFontOfSize_(11))
        sep_label.setFrame_(NSMakeRect(15, y, 250, 16))
        content.addSubview_(sep_label)
        y -= 5

        # --- Key binding rows ---
        scroll_view_h = y - button_area
        doc_h = (len(self._actions) + len(self._global_actions) + 2) * _ROW_H
        doc_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 390, doc_h))
        self._doc_view = doc_view

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(10, button_area, 400, scroll_view_h)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setDocumentView_(doc_view)
        content.addSubview_(scroll)

        # Initialize normal recorders
        self._key_recorders = {}
        for action in self._actions:
            spec = bindings.get(action, {"keycode": 0})
            specs = spec if isinstance(spec, list) else [spec]
            self._key_recorders[action] = [self._make_recorder(s) for s in specs]
            
        # Initialize global recorders
        self._global_recorders = {}
        for action in self._global_actions:
            spec = global_bindings.get(action)
            rec = HotkeyRecorderField.alloc().initWithFrame_(NSMakeRect(0, 0, _REC_W * 2, 20))
            rec.setFont_(NSFont.systemFontOfSize_(12))
            if spec and spec.get("keycode") is not None:
                # Convert config spec to (keycode, flags)
                f = 0
                if spec.get("cmd"): f |= Quartz.kCGEventFlagMaskCommand
                if spec.get("alt"): f |= Quartz.kCGEventFlagMaskAlternate
                if spec.get("ctrl"): f |= Quartz.kCGEventFlagMaskControl
                if spec.get("shift"): f |= Quartz.kCGEventFlagMaskShift
                rec._keycode = spec["keycode"]
                rec._flags = f
                rec.setStringValue_(config.format_hotkey(rec._keycode, rec._flags))
            else:
                rec.setStringValue_("Not set")
            self._global_recorders[action] = rec
            
        self._rebuild_binding_rows()

        # --- Buttons ---
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(95, 10, 80, 30))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_(b"save:")
        content.addSubview_(save_btn)

        reset_btn = NSButton.alloc().initWithFrame_(NSMakeRect(195, 10, 80, 30))
        reset_btn.setTitle_("Reset")
        reset_btn.setBezelStyle_(NSBezelStyleRounded)
        reset_btn.setTarget_(self)
        reset_btn.setAction_(b"resetDefaults:")
        content.addSubview_(reset_btn)

        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(295, 10, 80, 30))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(NSBezelStyleRounded)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_(b"cancel:")
        content.addSubview_(cancel_btn)

        self._window = w
        NSApp.setActivationPolicy_(1)
        w.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _make_recorder(self, spec):
        """Create a KeyRecorderField initialized from a binding spec."""
        rec = KeyRecorderField.alloc().initWithFrame_(NSMakeRect(0, 0, _REC_W, 20))
        rec.setFont_(NSFont.systemFontOfSize_(12))
        rec._keycode = spec["keycode"]
        rec._ctrl = spec.get("ctrl", False)
        rec._shift = spec.get("shift", False)
        rec.setStringValue_(config.format_binding(spec))
        return rec

    def _rebuild_binding_rows(self):
        """Clear and rebuild all keybinding rows in the doc view."""
        for sub in list(self._doc_view.subviews()):
            sub.removeFromSuperview()
        
        # Headers: "Normal Mode", "Global Tiling"
        extra_rows = 2
        doc_h = (len(self._actions) + len(self._global_actions) + extra_rows) * _ROW_H
        self._doc_view.setFrameSize_((self._doc_view.frame().size.width, doc_h))
        
        row_idx = 0
        
        # 1. Normal Mode Actions
        ry = doc_h - (row_idx + 1) * _ROW_H + 5
        sep = NSTextField.labelWithString_("Normal Mode Actions:")
        sep.setFont_(NSFont.boldSystemFontOfSize_(11))
        sep.setTextColor_(NSColor.secondaryLabelColor())
        sep.setFrame_(NSMakeRect(5, ry, 250, 16))
        self._doc_view.addSubview_(sep)
        row_idx += 1
        
        for action in self._actions:
            self._add_binding_row(action, doc_h, row_idx)
            row_idx += 1
            
        # 2. Global Tiling Bindings
        ry = doc_h - (row_idx + 1) * _ROW_H + 5
        sep = NSTextField.labelWithString_("Global Tiling Shortcuts (All Modes):")
        sep.setFont_(NSFont.boldSystemFontOfSize_(11))
        sep.setTextColor_(NSColor.secondaryLabelColor())
        sep.setFrame_(NSMakeRect(5, ry, 250, 16))
        self._doc_view.addSubview_(sep)
        row_idx += 1
        
        for action in self._global_actions:
            ry = doc_h - (row_idx + 1) * _ROW_H + 5
            lbl = NSTextField.labelWithString_(_GLOBAL_TILING_LABELS[action] + ":")
            lbl.setFrame_(NSMakeRect(5, ry, _LABEL_W + 40, 20))
            lbl.setFont_(NSFont.systemFontOfSize_(12))
            self._doc_view.addSubview_(lbl)
            
            rec = self._global_recorders[action]
            rec.setFrame_(NSMakeRect(_KEYS_X + 40, ry, _REC_W * 2, 20))
            self._doc_view.addSubview_(rec)
            row_idx += 1

    def _add_binding_row(self, action, doc_h, row_idx):
        ry = doc_h - (row_idx + 1) * _ROW_H + 5
        # Action label
        lbl = NSTextField.labelWithString_(_ACTION_LABELS[action] + ":")
        lbl.setFrame_(NSMakeRect(5, ry, _LABEL_W, 20))
        lbl.setFont_(NSFont.systemFontOfSize_(12))
        self._doc_view.addSubview_(lbl)
        # Key recorder slots
        recorders = self._key_recorders[action]
        for si, rec in enumerate(recorders):
            rx = _KEYS_X + si * _SLOT_W
            rec.setFrame_(NSMakeRect(rx, ry, _REC_W, 20))
            self._doc_view.addSubview_(rec)
            # × button (only if more than one key)
            if len(recorders) > 1:
                xbtn = NSButton.alloc().initWithFrame_(
                    NSMakeRect(rx + _REC_W + 1, ry, _BTN_W, 20)
                )
                xbtn.setTitle_("\u00d7")
                xbtn.setBezelStyle_(NSBezelStyleSmallSquare)
                xbtn.setFont_(NSFont.systemFontOfSize_(11))
                xbtn.setTarget_(self)
                xbtn.setAction_(b"removeKey:")
                xbtn.setAccessibilityIdentifier_(action)
                xbtn.setTag_(si)
                self._doc_view.addSubview_(xbtn)
        # + button (if under max)
        if len(recorders) < _MAX_KEYS_PER_ACTION:
            px = _KEYS_X + len(recorders) * _SLOT_W
            pbtn = NSButton.alloc().initWithFrame_(NSMakeRect(px, ry, _BTN_W, 20))
            pbtn.setTitle_("+")
            pbtn.setBezelStyle_(NSBezelStyleSmallSquare)
            pbtn.setFont_(NSFont.systemFontOfSize_(11))
            pbtn.setTarget_(self)
            pbtn.setAction_(b"addKey:")
            pbtn.setAccessibilityIdentifier_(action)
            self._doc_view.addSubview_(pbtn)

    def _refresh_values(self):
        """Refresh displayed values from current config."""
        keycode, flags = hotkey.get_hotkey()
        self._recorder.setStringValue_(config.format_hotkey(keycode, flags))
        self._recorder._keycode = None
        self._recorder._flags = 0
        
        cfg = config.load()
        bindings = config.load_keybindings()
        global_bindings = cfg.get("global_tiling_bindings", {})
        
        for action in self._actions:
            spec = bindings.get(action, {"keycode": 0})
            specs = spec if isinstance(spec, list) else [spec]
            self._key_recorders[action] = [self._make_recorder(s) for s in specs]
            
        for action in self._global_actions:
            spec = global_bindings.get(action)
            rec = self._global_recorders[action]
            if spec and spec.get("keycode") is not None:
                f = 0
                if spec.get("cmd"): f |= Quartz.kCGEventFlagMaskCommand
                if spec.get("alt"): f |= Quartz.kCGEventFlagMaskAlternate
                if spec.get("ctrl"): f |= Quartz.kCGEventFlagMaskControl
                if spec.get("shift"): f |= Quartz.kCGEventFlagMaskShift
                rec._keycode = spec["keycode"]
                rec._flags = f
                rec.setStringValue_(config.format_hotkey(rec._keycode, rec._flags))
            else:
                rec._keycode = None
                rec._flags = 0
                rec.setStringValue_("Not set")
                
        self._rebuild_binding_rows()

    def _collect_keybindings(self):
        """Collect keybinding values from the recorder fields."""
        bindings = {}
        for action, recorders in self._key_recorders.items():
            entries = []
            for rec in recorders:
                if rec._keycode is not None:
                    entry = {"keycode": rec._keycode}
                    if rec._ctrl:
                        entry["ctrl"] = True
                    if rec._shift:
                        entry["shift"] = True
                    entries.append(entry)
            if not entries:
                continue
            bindings[action] = entries[0] if len(entries) == 1 else entries
        return bindings

    def _stop_all_recording(self):
        """Stop recording on all fields."""
        self._recorder._stopRecording()
        for recorders in self._key_recorders.values():
            for rec in recorders:
                rec._stopRecording()
        for rec in self._global_recorders.values():
            rec._stopRecording()

    @objc.typedSelector(b"v@:@")
    def addKey_(self, sender):
        action = sender.accessibilityIdentifier()
        recorders = self._key_recorders[action]
        if len(recorders) >= _MAX_KEYS_PER_ACTION:
            return
        rec = KeyRecorderField.alloc().initWithFrame_(NSMakeRect(0, 0, _REC_W, 20))
        rec.setFont_(NSFont.systemFontOfSize_(12))
        rec.setStringValue_("...")
        recorders.append(rec)
        self._rebuild_binding_rows()

    @objc.typedSelector(b"v@:@")
    def removeKey_(self, sender):
        action = sender.accessibilityIdentifier()
        idx = sender.tag()
        recorders = self._key_recorders[action]
        if len(recorders) <= 1:
            return
        removed = recorders.pop(idx)
        removed._stopRecording()
        self._rebuild_binding_rows()

    @objc.typedSelector(b"v@:@")
    def save_(self, sender):
        self._stop_all_recording()
        data = config.load()
        # Save activation hotkey
        rec = self._recorder
        if rec._keycode is not None:
            hotkey.update_hotkey(rec._keycode, rec._flags)
            data["keycode"] = rec._keycode
            data["flags"] = rec._flags
            
        # Save keybindings
        data["keybindings"] = self._collect_keybindings()
        
        # Save global tiling bindings
        global_bindings = {}
        for action, rec in self._global_recorders.items():
            if rec._keycode is not None:
                entry = {"keycode": rec._keycode}
                f = rec._flags
                if f & Quartz.kCGEventFlagMaskCommand: entry["cmd"] = True
                if f & Quartz.kCGEventFlagMaskAlternate: entry["alt"] = True
                if f & Quartz.kCGEventFlagMaskControl: entry["ctrl"] = True
                if f & Quartz.kCGEventFlagMaskShift: entry["shift"] = True
                global_bindings[action] = entry
        data["global_tiling_bindings"] = global_bindings
        
        config.save(data)
        if self._overlay:
            self._overlay.reload_keybindings()
            self._overlay.suspend_tap(False)
        self._window.orderOut_(None)
        NSApp.setActivationPolicy_(2)

    @objc.typedSelector(b"v@:@")
    def resetDefaults_(self, sender):
        self._stop_all_recording()
        defaults = config.default_keybindings()
        for action in self._actions:
            spec = defaults.get(action, {"keycode": 0})
            specs = spec if isinstance(spec, list) else [spec]
            self._key_recorders[action] = [self._make_recorder(s) for s in specs]
        self._rebuild_binding_rows()

    @objc.typedSelector(b"v@:@")
    def cancel_(self, sender):
        self._stop_all_recording()
        if self._overlay:
            self._overlay.suspend_tap(False)
        self._window.orderOut_(None)
        NSApp.setActivationPolicy_(2)

    def windowWillClose_(self, notification):
        self._stop_all_recording()
        if self._overlay:
            self._overlay.suspend_tap(False)
        NSApp.setActivationPolicy_(2)
