import sys
from unittest.mock import MagicMock
import Quartz as mock_quartz
import objc as mock_objc
import AppKit as mock_appkit
import ApplicationServices as mock_app_services
import PyObjCTools as mock_pyobjc_tools
import Foundation as mock_foundation
import CoreFoundation as mock_core_foundation

import pytest

@pytest.fixture
def overlay(mocker):
    # Mock dependencies within HintOverlay
    mock_overlay = MagicMock()
    return mock_overlay

def test_register_global_hotkeys(overlay, mocker):
    from vimlayer.platforms.mac.provider import MacPlatformProvider
    provider = MacPlatformProvider()
    mock_hotkey = mocker.patch.object(provider, "_hotkey")
    
    cfg = {
        "global_tiling_bindings": {
            "win_tile_1": {"keycode": 18, "cmd": True, "ctrl": True},  # Cmd+Ctrl+1
            "win_center": {"keycode": 8, "cmd": True, "ctrl": True},   # Cmd+Ctrl+C
        }
    }
    
    provider._register_global_hotkeys(overlay, cfg)
    
    # Check that hotkey.unregister_all was called
    mock_hotkey.unregister_all.assert_called_once()
    
    # Check that hotkey.register was called for both actions
    assert mock_hotkey.register.call_count == 2
    
    # Verify first registration (win_tile_1)
    # The callback is a nested function, so we can't easily check equality,
    # but we can check keycode and flags.
    calls = mock_hotkey.register.call_args_list
    
    # Map keycodes to actions for verification
    registered = {call[0][1]: call[0][2] for call in calls}
    
    expected_flags = mock_quartz.kCGEventFlagMaskCommand | mock_quartz.kCGEventFlagMaskControl
    assert registered[18] == expected_flags
    assert registered[8] == expected_flags
