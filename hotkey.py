"""Global hotkey registration via CGEventTap."""

import Quartz

MODIFIER_MASK = (
    Quartz.kCGEventFlagMaskCommand
    | Quartz.kCGEventFlagMaskShift
    | Quartz.kCGEventFlagMaskAlternate
    | Quartz.kCGEventFlagMaskControl
)


class HotkeyManager:
    def __init__(self):
        self.keycode = 49  # Space (default: Cmd+Shift+Space)
        self.flags = Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift
        self.callback = None
        self.suspended = False
        self.capture_all = False
        self.tap = None

    def suspend(self, value=True):
        """Temporarily suspend/resume hotkey interception."""
        self.suspended = value

    def set_capture_all(self, value=True):
        """When True, all key events are swallowed (except the hotkey itself)."""
        self.capture_all = value

    def get_hotkey(self):
        """Return current (keycode, flags) tuple."""
        return self.keycode, self.flags

    def update_hotkey(self, keycode, flags):
        """Change the active hotkey at runtime."""
        self.keycode = keycode
        self.flags = flags

    def register(self, callback, keycode=None, flags=None):
        """Register a global hotkey that calls `callback`."""
        self.callback = callback
        if keycode is not None:
            self.update_hotkey(keycode, flags)

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            self._tap_callback,
            None,
        )
        self.tap = tap
        if tap is None:
            print("ERROR: Could not create event tap.")
            print("Grant Accessibility permission in System Settings → Privacy & Security.")
            return False

        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(tap, True)
        return True

    def _tap_callback(self, proxy, event_type, event, refcon):
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            Quartz.CGEventTapEnable(self.tap, True)
            return event
        if self.suspended:
            return event
        if event_type == Quartz.kCGEventKeyDown:
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode
            )
            flags = Quartz.CGEventGetFlags(event) & MODIFIER_MASK
            
            # If it's the hotkey, always handle it
            if keycode == self.keycode and flags == self.flags:
                if self.callback:
                    self.callback()
                return None  # Suppress the event

            # If we're capturing all, swallow everything else
            if self.capture_all:
                return None

        return event


_manager = HotkeyManager()


def suspend(value=True):
    _manager.suspend(value)


def set_capture_all(value=True):
    _manager.set_capture_all(value)


def get_hotkey():
    return _manager.get_hotkey()


def update_hotkey(keycode, flags):
    _manager.update_hotkey(keycode, flags)


def register(callback, keycode=None, flags=None):
    return _manager.register(callback, keycode, flags)
