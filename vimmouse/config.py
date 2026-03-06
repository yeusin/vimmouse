"""Simple JSON config persistence."""

import json
import os

import Quartz

_CONFIG_PATH = os.path.expanduser("~/.config/vimmouse/config.json")

_DEFAULTS = {
    "keycode": 49,  # Space
    "flags": Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift,
}

_DEFAULT_KEYBINDINGS = {
    "move_left": {"keycode": 4},            # h
    "move_down": {"keycode": 38},           # j
    "move_up": {"keycode": 40},             # k
    "move_right": {"keycode": 37},          # l
    "scroll_up": {"keycode": 11, "ctrl": True},    # ctrl+b
    "scroll_down": {"keycode": 3, "ctrl": True},   # ctrl+f
    "toggle_hints": {"keycode": 3, "shift": True},         # shift+f
    "toggle_all_hints": {"keycode": 3},                   # f
    "open_launcher": {"keycode": 44},                    # /
    "click": {"keycode": 49},              # space
    "insert_mode": {"keycode": 34},        # i
    "forward": {"keycode": 13},            # w
    "back": {"keycode": 11},               # b
    "right_click": {"keycode": 49, "shift": True},  # shift+space
    "window_prefix": {"keycode": 13, "ctrl": True},  # ctrl+w
    "win_cycle": {"keycode": 13, "ctrl": True},       # ctrl+w (after prefix)
    "win_tile_1": {"keycode": 18},                     # 1
    "win_tile_2": {"keycode": 19},                     # 2
    "win_tile_3": {"keycode": 20},                     # 3
    "win_tile_4": {"keycode": 21},                     # 4
    "win_sixth_tl": {"keycode": 12},                   # q
    "win_sixth_tc": {"keycode": 13},                   # w
    "win_sixth_tr": {"keycode": 14},                   # e
    "win_sixth_bl": {"keycode": 0},                    # a
    "win_sixth_bc": {"keycode": 1},                    # s
    "win_sixth_br": {"keycode": 2},                    # d
    "win_half_left": {"keycode": 4},                   # h
    "win_half_down": {"keycode": 38},                  # j
    "win_half_up": {"keycode": 40},                    # k
    "win_half_right": {"keycode": 37},                 # l
    "win_center": {"keycode": 8},                      # c
    "win_maximize": {"keycode": 36},                   # enter
}


def default_keybindings():
    """Return a deep copy of the default keybindings."""
    return json.loads(json.dumps(_DEFAULT_KEYBINDINGS))


def load():
    """Read config from disk, returning defaults if missing or invalid."""
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def load_keybindings():
    """Return merged keybindings (defaults + user overrides)."""
    bindings = default_keybindings()
    data = load()
    user = data.get("keybindings")
    if isinstance(user, dict):
        bindings.update(user)
    return bindings


def save(data):
    """Write config dict to disk."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(data, f)
