"""Simple JSON config persistence (platform-agnostic wrapper)."""

import json
import os
from typing import Any, Dict, Union, List
from .platforms import get_platform

_CONFIG_PATH = os.path.expanduser("~/.config/vimlayer/config.json")

def format_hotkey(keycode: int, flags: int, use_symbols: bool = True) -> str:
    return get_platform().format_hotkey(keycode, flags, use_symbols=use_symbols)

def format_binding(spec: Any, use_symbols: bool = True) -> str:
    return get_platform().format_binding(spec, use_symbols=use_symbols)

def default_keybindings() -> Dict[str, Any]:
    return get_platform().get_default_keybindings()

def load() -> Dict[str, Any]:
    data = get_platform().get_default_config()
    try:
        with open(_CONFIG_PATH) as f:
            user_data = json.load(f)
            if isinstance(user_data, dict):
                data.update(user_data)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return data

def load_keybindings() -> Dict[str, Any]:
    bindings = default_keybindings()
    data = load()
    user = data.get("keybindings")
    if isinstance(user, dict):
        bindings.update(user)
    return bindings

def save(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(data, f)
