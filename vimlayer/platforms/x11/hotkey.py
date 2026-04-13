import logging
from typing import Tuple, Callable, Dict, List, Optional
from Xlib import display, X
from Xlib.protocol import event

log = logging.getLogger(__name__)

class X11Hotkey:
    def __init__(self):
        self._display = display.Display()
        self._root = self._display.screen().root
        self._root.change_attributes(event_mask=X.KeyPressMask)
        self._callbacks: Dict[Tuple[int, int], Callable] = {}
        self._primary_key: Optional[Tuple[int, int]] = None
        self._key_handler: Optional[Callable[[int, int], bool]] = None

    def set_key_handler(self, handler: Optional[Callable[[int, int], bool]]) -> None:
        """Set a modal key handler. If it returns True, the key is consumed."""
        self._key_handler = handler

    def register(self, callback: Callable, keycode: int, flags: int, is_primary: bool = False) -> bool:
        log.info("Registering hotkey: keycode=%d, flags=%d", keycode, flags)
        # X11 modifiers: ShiftMask, ControlMask, Mod1Mask (Alt), Mod4Mask (Super)
        # We also need to grab with LockMask (Caps Lock) and NumLock if we want it to work regardless of their state.
        # For simplicity, let's just grab the requested flags for now.
        
        try:
            self._root.grab_key(keycode, flags, True, X.GrabModeAsync, X.GrabModeAsync)
            self._callbacks[(keycode, flags)] = callback
            if is_primary:
                self._primary_key = (keycode, flags)
            return True
        except Exception as e:
            log.error("Failed to grab key: %s", e)
            return False

    def unregister_all(self) -> None:
        for (keycode, flags) in self._callbacks:
            if (keycode, flags) != self._primary_key:
                self._root.ungrab_key(keycode, flags, self._root)
        self._callbacks = {k: v for k, v in self._callbacks.items() if k == self._primary_key}

    def update_hotkey(self, keycode: int, flags: int) -> None:
        if self._primary_key:
            self._root.ungrab_key(self._primary_key[0], self._primary_key[1], self._root)
        self._primary_key = (keycode, flags)
        # Re-registering is done by the caller usually

    def get_hotkey(self) -> Tuple[int, int]:
        return self._primary_key or (0, 0)

    def suspend(self, value: bool = True) -> None:
        # Potentially ungrab everything
        pass

    def process_events(self) -> None:
        """Poll and process pending X11 events."""
        while self._display.pending_events():
            ev = self._display.next_event()
            if ev.type == X.KeyPress:
                keycode = ev.detail
                state = ev.state & (X.ShiftMask | X.ControlMask | X.Mod1Mask | X.Mod4Mask)
                
                # Check global hotkey callbacks first
                callback = self._callbacks.get((keycode, state))
                if callback:
                    log.info("Hotkey triggered: keycode=%d, state=%d", keycode, state)
                    callback()
                    continue

                # Modal handler takes precedence for other keys
                if self._key_handler:
                    if self._key_handler(keycode, state):
                        continue

            elif ev.type == X.MappingNotify:
                self._display.refresh_keyboard_mapping()

    def grab_keyboard(self) -> bool:
        """Grab all keyboard input (for modal navigation)."""
        res = self._root.grab_keyboard(True, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
        return res == X.GrabSuccess

    def ungrab_keyboard(self) -> None:
        self._display.ungrab_keyboard(X.CurrentTime)
        self._display.flush()
