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
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
    NSButtonTypeSwitch,
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
    """Text field that starts recording on click."""

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
        self.setBezeled_(True)
        self.setBezelStyle_(1)  # NSTextFieldSquareBezel
        return self

    def mouseDown_(self, event):
        if self._recording:
            return
        self._recording = True
        hotkey.suspend(True)
        self.setStringValue_("Recording...")
        self.setBackgroundColor_(NSColor.systemYellowColor().colorWithAlphaComponent_(0.2))
        self.setDrawsBackground_(True)
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
        self.setDrawsBackground_(False)
        hotkey.suspend(False)


class KeyRecorderField(NSTextField):
    """Text field that records a single key press."""

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
        self.setBezeled_(True)
        self.setBezelStyle_(1)  # NSTextFieldSquareBezel
        return self

    def mouseDown_(self, event):
        if self._recording:
            return
        self._recording = True
        hotkey.suspend(True)
        self.setStringValue_("?")
        self.setBackgroundColor_(NSColor.systemYellowColor().colorWithAlphaComponent_(0.2))
        self.setDrawsBackground_(True)
        field = self

        def handle(event):
            keycode = event.keyCode()
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
        self.setDrawsBackground_(False)
        hotkey.suspend(False)


_ROW_H = 34
_MAX_KEYS_PER_ACTION = 4
_LABEL_W = 130
_REC_W = 80
_BTN_W = 24
_SLOT_W = _REC_W + _BTN_W + 4
_KEYS_X = _LABEL_W + 10


class SettingsController(NSObject):
    """Controller for the tabbed settings window."""

    def init(self):
        self = objc.super(SettingsController, self).init()
        if self is None:
            return None
        self._window = None
        self._recorder = None
        self._auto_insert_btn = None
        self._key_recorders = {}
        self._global_recorders = {}
        self._normal_doc = None
        self._global_doc = None
        self._actions = list(_ACTION_LABELS.keys())
        self._global_actions = list(_GLOBAL_TILING_LABELS.keys())
        self._overlay = None
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
        
        win_w, win_h = 520, 560
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, win_w, win_h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        w.setTitle_("VimLayer Settings")
        w.setReleasedWhenClosed_(False)
        w.setDelegate_(self)
        w.center()
        content = w.contentView()

        # --- Tabs ---
        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(10, 55, win_w - 20, win_h - 75))
        
        # 1. General Tab
        gen_item = NSTabViewItem.alloc().initWithIdentifier_("General")
        gen_item.setLabel_("General")
        gen_view = NSView.alloc().initWithFrame_(tabs.bounds())
        
        gy = tabs.bounds().size.height - 70
        label = NSTextField.labelWithString_("Activation Shortcut:")
        label.setFont_(NSFont.boldSystemFontOfSize_(13))
        label.setFrame_(NSMakeRect(20, gy, 180, 20))
        gen_view.addSubview_(label)

        recorder = HotkeyRecorderField.alloc().initWithFrame_(NSMakeRect(205, gy - 2, 200, 24))
        keycode, flags = hotkey.get_hotkey()
        recorder.setStringValue_(config.format_hotkey(keycode, flags))
        gen_view.addSubview_(recorder)
        self._recorder = recorder
        
        gy -= 40
        hint = NSTextField.labelWithString_("This shortcut toggles Normal Mode from any application.")
        hint.setFont_(NSFont.systemFontOfSize_(11))
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setFrame_(NSMakeRect(20, gy, 400, 16))
        gen_view.addSubview_(hint)
        
        gy -= 50
        self._auto_insert_btn = NSButton.alloc().initWithFrame_(NSMakeRect(20, gy, 400, 20))
        self._auto_insert_btn.setButtonType_(NSButtonTypeSwitch)
        self._auto_insert_btn.setTitle_("Auto-enter Insert Mode in text fields")
        self._auto_insert_btn.setState_(1 if cfg.get("auto_insert_mode", True) else 0)
        gen_view.addSubview_(self._auto_insert_btn)
        
        gen_item.setView_(gen_view)
        tabs.addTabViewItem_(gen_item)

        # 2. Normal Mode Tab
        norm_item = NSTabViewItem.alloc().initWithIdentifier_("Normal")
        norm_item.setLabel_("Normal Mode")
        
        scroll_n = NSScrollView.alloc().initWithFrame_(tabs.bounds())
        scroll_n.setHasVerticalScroller_(True)
        self._normal_doc = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, win_w - 40, len(self._actions) * _ROW_H + 20))
        scroll_n.setDocumentView_(self._normal_doc)
        
        norm_item.setView_(scroll_n)
        tabs.addTabViewItem_(norm_item)

        # 3. Global Tiling Tab
        tile_item = NSTabViewItem.alloc().initWithIdentifier_("Tiling")
        tile_item.setLabel_("Window Tiling")
        
        scroll_t = NSScrollView.alloc().initWithFrame_(tabs.bounds())
        scroll_t.setHasVerticalScroller_(True)
        self._global_doc = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, win_w - 40, len(self._global_actions) * _ROW_H + 20))
        scroll_t.setDocumentView_(self._global_doc)
        
        tile_item.setView_(scroll_t)
        tabs.addTabViewItem_(tile_item)

        content.addSubview_(tabs)

        # Initialize recorders
        self._key_recorders = {}
        for action in self._actions:
            spec = bindings.get(action, {"keycode": 0})
            specs = spec if isinstance(spec, list) else [spec]
            self._key_recorders[action] = [self._make_recorder(s) for s in specs]
            
        self._global_recorders = {}
        for action in self._global_actions:
            spec = global_bindings.get(action)
            rec = HotkeyRecorderField.alloc().initWithFrame_(NSMakeRect(0, 0, _REC_W * 2, 24))
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
                rec.setStringValue_("Not set")
            self._global_recorders[action] = rec
            
        self._rebuild_binding_rows()

        # --- Buttons ---
        bx = win_w - 95
        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(bx, 12, 80, 32))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(NSBezelStyleRounded)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_(b"cancel:")
        content.addSubview_(cancel_btn)

        bx -= 90
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(bx, 12, 80, 32))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_(b"save:")
        content.addSubview_(save_btn)

        reset_btn = NSButton.alloc().initWithFrame_(NSMakeRect(15, 12, 120, 32))
        reset_btn.setTitle_("Reset Defaults")
        reset_btn.setBezelStyle_(NSBezelStyleRounded)
        reset_btn.setTarget_(self)
        reset_btn.setAction_(b"resetDefaults:")
        content.addSubview_(reset_btn)

        self._window = w
        NSApp.setActivationPolicy_(1)
        w.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _make_recorder(self, spec):
        rec = KeyRecorderField.alloc().initWithFrame_(NSMakeRect(0, 0, _REC_W, 24))
        rec._keycode = spec["keycode"]
        rec._ctrl = spec.get("ctrl", False)
        rec._shift = spec.get("shift", False)
        rec.setStringValue_(config.format_binding(spec))
        return rec

    def _rebuild_binding_rows(self):
        # 1. Normal Mode
        for sub in list(self._normal_doc.subviews()):
            sub.removeFromSuperview()
        
        doc_h = len(self._actions) * _ROW_H + 20
        self._normal_doc.setFrameSize_((self._normal_doc.frame().size.width, doc_h))
        
        for idx, action in enumerate(self._actions):
            ry = doc_h - (idx + 1) * _ROW_H - 10
            lbl = NSTextField.labelWithString_(_ACTION_LABELS[action] + ":")
            lbl.setFrame_(NSMakeRect(10, ry, _LABEL_W, 20))
            lbl.setFont_(NSFont.systemFontOfSize_(12))
            self._normal_doc.addSubview_(lbl)
            
            recorders = self._key_recorders[action]
            for si, rec in enumerate(recorders):
                rx = _KEYS_X + si * _SLOT_W
                rec.setFrame_(NSMakeRect(rx, ry, _REC_W, 24))
                self._normal_doc.addSubview_(rec)
                if len(recorders) > 1:
                    xbtn = NSButton.alloc().initWithFrame_(NSMakeRect(rx + _REC_W + 2, ry, _BTN_W, 24))
                    xbtn.setTitle_("\u00d7")
                    xbtn.setBezelStyle_(NSBezelStyleSmallSquare)
                    xbtn.setTarget_(self)
                    xbtn.setAction_(b"removeKey:")
                    xbtn.setAccessibilityIdentifier_(action)
                    xbtn.setTag_(si)
                    self._normal_doc.addSubview_(xbtn)
            
            if len(recorders) < _MAX_KEYS_PER_ACTION:
                px = _KEYS_X + len(recorders) * _SLOT_W
                pbtn = NSButton.alloc().initWithFrame_(NSMakeRect(px, ry, _BTN_W, 24))
                pbtn.setTitle_("+")
                pbtn.setBezelStyle_(NSBezelStyleSmallSquare)
                pbtn.setTarget_(self)
                pbtn.setAction_(b"addKey:")
                pbtn.setAccessibilityIdentifier_(action)
                self._normal_doc.addSubview_(pbtn)

        # 2. Global Tiling
        for sub in list(self._global_doc.subviews()):
            sub.removeFromSuperview()
            
        doc_h = len(self._global_actions) * _ROW_H + 20
        self._global_doc.setFrameSize_((self._global_doc.frame().size.width, doc_h))
        
        for idx, action in enumerate(self._global_actions):
            ry = doc_h - (idx + 1) * _ROW_H - 10
            lbl = NSTextField.labelWithString_(_GLOBAL_TILING_LABELS[action] + ":")
            lbl.setFrame_(NSMakeRect(10, ry, _LABEL_W + 60, 20))
            lbl.setFont_(NSFont.systemFontOfSize_(12))
            self._global_doc.addSubview_(lbl)
            
            rec = self._global_recorders[action]
            rec.setFrame_(NSMakeRect(_KEYS_X + 60, ry, _REC_W * 2, 24))
            self._global_doc.addSubview_(rec)

    def _refresh_values(self):
        keycode, flags = hotkey.get_hotkey()
        self._recorder.setStringValue_(config.format_hotkey(keycode, flags))
        self._recorder._keycode = None
        self._recorder._flags = 0
        
        cfg = config.load()
        self._auto_insert_btn.setState_(1 if cfg.get("auto_insert_mode", True) else 0)
        
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
        bindings = {}
        for action, recorders in self._key_recorders.items():
            entries = []
            for rec in recorders:
                if rec._keycode is not None:
                    entry = {"keycode": rec._keycode}
                    if rec._ctrl: entry["ctrl"] = True
                    if rec._shift: entry["shift"] = True
                    entries.append(entry)
            if entries:
                bindings[action] = entries[0] if len(entries) == 1 else entries
        return bindings

    def _stop_all_recording(self):
        self._recorder._stopRecording()
        for recorders in self._key_recorders.values():
            for rec in recorders: rec._stopRecording()
        for rec in self._global_recorders.values(): rec._stopRecording()

    @objc.typedSelector(b"v@:@")
    def addKey_(self, sender):
        action = sender.accessibilityIdentifier()
        recorders = self._key_recorders[action]
        if len(recorders) >= _MAX_KEYS_PER_ACTION: return
        rec = KeyRecorderField.alloc().initWithFrame_(NSMakeRect(0, 0, _REC_W, 24))
        rec.setStringValue_("...")
        recorders.append(rec)
        self._rebuild_binding_rows()

    @objc.typedSelector(b"v@:@")
    def removeKey_(self, sender):
        action = sender.accessibilityIdentifier()
        idx = sender.tag()
        recorders = self._key_recorders[action]
        if len(recorders) <= 1: return
        removed = recorders.pop(idx)
        removed._stopRecording()
        self._rebuild_binding_rows()

    @objc.typedSelector(b"v@:@")
    def save_(self, sender):
        self._stop_all_recording()
        data = config.load()
        rec = self._recorder
        if rec._keycode is not None:
            hotkey.update_hotkey(rec._keycode, rec._flags)
            data["keycode"] = rec._keycode
            data["flags"] = rec._flags
            
        data["auto_insert_mode"] = bool(self._auto_insert_btn.state())
        data["keybindings"] = self._collect_keybindings()
        
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
        if self._overlay: self._overlay.suspend_tap(False)
        self._window.orderOut_(None)
        NSApp.setActivationPolicy_(2)

    def windowWillClose_(self, notification):
        self._stop_all_recording()
        if self._overlay: self._overlay.suspend_tap(False)
        NSApp.setActivationPolicy_(2)
