import logging
from typing import Optional, Callable
from Xlib import X

log = logging.getLogger(__name__)

_WINDOW_ACTIONS = {
    "win_tile_1": lambda o: lambda: o._win_mgr.tile_window(1),
    "win_tile_2": lambda o: lambda: o._win_mgr.tile_window(2),
    "win_tile_3": lambda o: lambda: o._win_mgr.tile_window(3),
    "win_tile_4": lambda o: lambda: o._win_mgr.tile_window(4),
    "win_sixth_tl": lambda o: lambda: o._win_mgr.tile_window_sixth(0, 0),
    "win_sixth_tc": lambda o: lambda: o._win_mgr.tile_window_sixth(1, 0),
    "win_sixth_tr": lambda o: lambda: o._win_mgr.tile_window_sixth(2, 0),
    "win_sixth_bl": lambda o: lambda: o._win_mgr.tile_window_sixth(0, 1),
    "win_sixth_bc": lambda o: lambda: o._win_mgr.tile_window_sixth(1, 1),
    "win_sixth_br": lambda o: lambda: o._win_mgr.tile_window_sixth(2, 1),
    "win_half_left": lambda o: lambda: o._win_mgr.tile_window_half("left"),
    "win_half_down": lambda o: lambda: o._win_mgr.tile_window_half("bottom"),
    "win_half_up": lambda o: lambda: o._win_mgr.tile_window_half("top"),
    "win_half_right": lambda o: lambda: o._win_mgr.tile_window_half("right"),
    "win_center": lambda o: o._win_mgr.center_window,
    "win_maximize": lambda o: o._win_mgr.toggle_maximize,
}

class X11HintOverlay:
    def __init__(self, on_mode_change: Optional[Callable] = None):
        from .. import get_platform
        from ...mouse import MouseController
        from ...launcher import Launcher
        platform = get_platform()
        self._on_mode_change = on_mode_change
        self._win_mgr = platform.window_manager
        self._mouse = platform.mouse
        self._mouse_ctrl = MouseController()
        self._hotkey = platform.hotkey
        self._accessibility = platform.accessibility
        self._launcher = Launcher(on_dismiss=self._on_launcher_dismiss)
        self._insert_mode = False
        self._bindings = {}
        self._binding_lookup = {}
        self._last_keycode = None
        self._last_state = None
        self.reload_keybindings()

    def reload_keybindings(self):
        from ... import config
        self._bindings = config.load_keybindings()
        self._binding_lookup = {}
        for action, spec in self._bindings.items():
            specs = spec if isinstance(spec, list) else [spec]
            for s in specs:
                key = (
                    s["keycode"],
                    bool(s.get("ctrl", False)),
                    bool(s.get("shift", False)),
                    bool(s.get("alt", False)),
                    bool(s.get("super", False)),
                )
                self._binding_lookup[key] = action

    def show(self):
        log.info("X11HintOverlay.show()")
        self._install_normal_tap()
        if self._on_mode_change:
            self._on_mode_change("NORMAL")

    def return_to_normal(self):
        log.info("X11HintOverlay.return_to_normal()")
        if self._insert_mode:
            self._exit_insert_mode()
        else:
            self.show()

    def enter_insert_mode(self):
        log.info("mode: INSERT")
        self._insert_mode = True
        self._remove_normal_tap()
        if self._on_mode_change:
            self._on_mode_change("INSERT")

    def _exit_insert_mode(self):
        log.info("mode: NORMAL")
        self._insert_mode = False
        self._install_normal_tap()
        if self._on_mode_change:
            self._on_mode_change("NORMAL")

    def _install_normal_tap(self):
        if self._hotkey.grab_keyboard():
            self._hotkey.set_key_handler(self._handle_key)
        else:
            log.error("Failed to grab keyboard for NORMAL mode")

    def _remove_normal_tap(self):
        self._hotkey.ungrab_keyboard()
        self._hotkey.set_key_handler(None)

    def _handle_key(self, keycode: int, state: int) -> bool:
        ctrl = bool(state & X.ControlMask)
        shift = bool(state & X.ShiftMask)
        alt = bool(state & X.Mod1Mask)
        super_key = bool(state & X.Mod4Mask)
        
        log.debug("Normal Mode Key: keycode=%d, ctrl=%s, shift=%s, alt=%s, super=%s", 
                  keycode, ctrl, shift, alt, super_key)

        # Check for Escape (keycode 9 usually on X11)
        if keycode == 9:
            log.info("Escape pressed, dismissing NORMAL mode")
            self.dismiss()
            return True

        # Simple repeat detection for X11 polling loop
        repeat = (keycode == self._last_keycode and state == self._last_state)
        self._last_keycode = keycode
        self._last_state = state

        action = self._binding_lookup.get((keycode, ctrl, shift, alt, super_key))
        if action:
            log.info("Key matched action: %s", action)
            self._execute_action(action, repeat=repeat)
            return True

        log.debug("No match for keycode %d in NORMAL mode", keycode)
        # Consume all other keys in normal mode
        return True

    def _execute_action(self, action: str, repeat: bool = False):
        log.info("Executing action: %s, repeat=%s", action, repeat)
        handler_factory = _WINDOW_ACTIONS.get(action)
        if handler_factory:
            handler = handler_factory(self)
            handler()
            return

        if action == "move_left": self._mouse_ctrl.move_relative(-1, 0, repeat)
        elif action == "move_down": self._mouse_ctrl.move_relative(0, 1, repeat)
        elif action == "move_up": self._mouse_ctrl.move_relative(0, -1, repeat)
        elif action == "move_right": self._mouse_ctrl.move_relative(1, 0, repeat)
        elif action == "scroll_up": self._mouse.scroll(3)
        elif action == "scroll_down": self._mouse.scroll(-3)
        elif action == "click":
            x, y = self._mouse.get_cursor_position()
            self._mouse.click(x, y)
        elif action == "right_click":
            x, y = self._mouse.get_cursor_position()
            self._mouse.right_click(x, y)
        elif action == "insert_mode":
            self.enter_insert_mode()
        elif action == "open_launcher":
            log.info("Opening launcher")
            self._remove_normal_tap()
            if self._on_mode_change:
                self._on_mode_change("LAUNCHER")
            self._launcher.show()
        elif action == "toggle_drag":
            # self._dragging = not self._dragging ... needs state management
            pass
        elif action.startswith("volume_"):
            # handle volume ...
            pass

    def _on_launcher_dismiss(self):
        log.info("Launcher dismissed")
        self._install_normal_tap()
        if self._on_mode_change:
            self._on_mode_change("NORMAL")

    def dismiss(self):
        log.info("Dismissing NORMAL mode")
        self._remove_normal_tap()
        if self._on_mode_change:
            self._on_mode_change(None)
