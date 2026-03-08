import json
import os
from vimlayer import config

def test_default_keybindings():
    bindings = config.default_keybindings()
    assert "move_left" in bindings
    assert bindings["move_left"]["keycode"] == 4

def test_load_defaults(tmp_path, monkeypatch):
    # Redirect config path to a temp file
    temp_config = tmp_path / "config.json"
    monkeypatch.setattr(config, "_CONFIG_PATH", str(temp_config))
    
    # Should return defaults when file doesn't exist
    data = config.load()
    assert data["keycode"] == 49
    
def test_save_and_load(tmp_path, monkeypatch):
    temp_config = tmp_path / "config.json"
    monkeypatch.setattr(config, "_CONFIG_PATH", str(temp_config))
    
    test_data = {"keycode": 123, "keybindings": {"move_left": {"keycode": 99}}}
    config.save(test_data)
    
    loaded = config.load()
    assert loaded["keycode"] == 123
    assert loaded["keybindings"]["move_left"]["keycode"] == 99

def test_load_keybindings_merge(tmp_path, monkeypatch):
    temp_config = tmp_path / "config.json"
    monkeypatch.setattr(config, "_CONFIG_PATH", str(temp_config))
    
    # Save a user override
    user_data = {"keybindings": {"move_left": {"keycode": 99}}}
    config.save(user_data)
    
    merged = config.load_keybindings()
    # Overridden
    assert merged["move_left"]["keycode"] == 99
    # Still has other defaults
    assert merged["move_right"]["keycode"] == 37
