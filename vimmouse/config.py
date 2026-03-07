"""Simple JSON config persistence."""

import json
import os
from typing import Any, Dict, Union, List

import Quartz

_CONFIG_PATH = os.path.expanduser("~/.config/vimmouse/config.json")

_DEFAULTS: Dict[str, Any] = {
    "keycode": 49,  # Space
    "flags": Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift,
}

BindingSpec = Dict[str, Union[int, bool]]
BindingEntry = Union[BindingSpec, List[BindingSpec]]

_DEFAULT_KEYBINDINGS: Dict[str, BindingEntry] = {
    "move_left": {"keycode": 4},            # h
    "move_down": {"keycode": 38},           # j
    "move_up": {"keycode": 40},             # k
    "move_right": {"keycode": 37},          # l
    "scroll_up": {"keycode": 11, "ctrl": True},    # ctrl+b
    "scroll_down": {"keycode": 3, "ctrl": True},   # ctrl+f
    "toggle_all_hints": {"keycode": 3},                   # f
    "toggle_cheat_sheet": {"keycode": 44, "shift": True},  # ? (shift+/)
    "open_launcher": {"keycode": 44},                    # /
    "click": {"keycode": 49},              # space
    "insert_mode": {"keycode": 34},        # i
    "forward": {"keycode": 13},            # w
    "back": {"keycode": 11},               # b
    "right_click": {"keycode": 49, "shift": True},  # shift+space
    "toggle_drag": {"keycode": 9},                 # v
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

# Mapping flag bits to both symbols and text
_MODIFIER_MAP = [
    (Quartz.kCGEventFlagMaskControl, "\u2303", "Ctrl+"),   # ⌃
    (Quartz.kCGEventFlagMaskAlternate, "\u2325", "Alt+"),  # ⌥
    (Quartz.kCGEventFlagMaskShift, "\u21e7", "Shift+"),    # ⇧
    (Quartz.kCGEventFlagMaskCommand, "\u2318", "Cmd+"),    # ⌘
]

_KEYCODE_NAMES = {
    49: "Space", 36: "Return", 48: "Tab", 51: "Delete", 53: "Escape",
    123: "\u2190", 124: "\u2192", 125: "\u2193", 126: "\u2191",  # arrows
    122: "F1", 120: "F2", 99: "F3", 118: "F4", 96: "F5", 97: "F6",
    98: "F7", 100: "F8", 101: "F9", 109: "F10", 103: "F11", 111: "F12",
}
_KEYCODE_LETTERS = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X",
    8: "C", 9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R",
    16: "Y", 17: "T", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
    30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P", 37: "L",
    38: "J", 39: "'", 40: "K", 41: ";", 42: "\\", 43: ",", 44: "/",
    45: "N", 46: "M", 47: ".", 50: "`",
}
_KEYCODE_NAMES.update(_KEYCODE_LETTERS)

def format_hotkey(keycode: int, flags: int, use_symbols: bool = True) -> str:
    """Return a human-readable hotkey string like '⌘⇧Space' or 'Cmd+Shift+Space'."""
    parts = []
    for mask, sym, text in _MODIFIER_MAP:
        if flags & mask:
            parts.append(sym if use_symbols else text)
    parts.append(_KEYCODE_NAMES.get(keycode, f"Key{keycode}"))
    return "".join(parts)

def format_binding(spec: BindingEntry, use_symbols: bool = True) -> str:
    """Format a keybinding spec (or list of specs) for display."""
    if isinstance(spec, list):
        return " / ".join(format_binding(s, use_symbols) for s in spec)
    keycode = spec["keycode"]
    ctrl = spec.get("ctrl", False)
    shift = spec.get("shift", False)
    name = _KEYCODE_NAMES.get(keycode, f"Key{keycode}")
    
    if use_symbols:
        prefix = ("\u2303" if ctrl else "") + ("\u21e7" if shift else "")
    else:
        prefix = ("Ctrl+" if ctrl else "") + ("Shift+" if shift else "")
        
    return f"{prefix}{name}"

def default_keybindings() -> Dict[str, BindingEntry]:
    """Return a deep copy of the default keybindings."""
    return json.loads(json.dumps(_DEFAULT_KEYBINDINGS))


def load() -> Dict[str, Any]:
    """Read config from disk, returning defaults if missing or invalid."""
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def load_keybindings() -> Dict[str, BindingEntry]:
    """Return merged keybindings (defaults + user overrides)."""
    bindings = default_keybindings()
    data = load()
    user = data.get("keybindings")
    if isinstance(user, dict):
        bindings.update(user)
    return bindings


def save(data: Dict[str, Any]) -> None:
    """Write config dict to disk."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(data, f)
