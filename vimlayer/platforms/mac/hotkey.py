"""macOS implementation of global hotkeys."""

import logging
from typing import Callable, Tuple
import Quartz
from ..base import HotkeyProvider

log = logging.getLogger(__name__)

MODIFIER_MASK = (
    Quartz.kCGEventFlagMaskCommand
    | Quartz.kCGEventFlagMaskShift
    | Quartz.kCGEventFlagMaskAlternate
    | Quartz.kCGEventFlagMaskControl
)


class MacHotkey(HotkeyProvider):
    def __init__(self):
        self.hotkeys = {}
        self.primary_hotkey = (49, Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift)
        self.suspended = False
        self.tap = None

    def suspend(self, value=True):
        self.suspended = value

    def get_hotkey(self):
        return self.primary_hotkey

    def register(self, callback: Callable, keycode: int, flags: int, is_primary: bool = False) -> bool:
        self.hotkeys[(keycode, flags)] = callback
        if is_primary:
            self.primary_hotkey = (keycode, flags)

        if self.tap is None:
            self.tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault,
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
                self._tap_callback,
                None,
            )
            if self.tap is None:
                log.error("Could not create event tap.")
                return False

            source = Quartz.CFMachPortCreateRunLoopSource(None, self.tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
            )
            Quartz.CGEventTapEnable(self.tap, True)
        return True

    def _tap_callback(self, proxy, event_type, event, refcon):
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            Quartz.CGEventTapEnable(self.tap, True)
            return event
        if self.suspended:
            return event
        if event_type == Quartz.kCGEventKeyDown:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event) & MODIFIER_MASK
            callback = self.hotkeys.get((keycode, flags))
            if callback:
                callback()
                return None
        return event

    def unregister_all(self):
        primary_cb = self.hotkeys.get(self.primary_hotkey)
        self.hotkeys = {}
        if primary_cb:
            self.hotkeys[self.primary_hotkey] = primary_cb

    def update_hotkey(self, keycode: int, flags: int):
        old_primary = self.primary_hotkey
        callback = self.hotkeys.pop(old_primary, None)
        self.primary_hotkey = (keycode, flags)
        if callback:
            self.hotkeys[self.primary_hotkey] = callback
