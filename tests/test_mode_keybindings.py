import sys
from unittest.mock import MagicMock, patch

# Mock Quartz and other macOS-specific modules
mock_quartz = MagicMock()
mock_quartz.kCGEventFlagMaskCommand = 1 << 20
mock_quartz.kCGEventFlagMaskShift = 1 << 17
mock_quartz.kCGEventFlagMaskAlternate = 1 << 19
mock_quartz.kCGEventFlagMaskControl = 1 << 18
mock_quartz.kCGEventKeyDown = 10
mock_quartz.kCGSessionEventTap = 0
mock_quartz.kCGHeadInsertEventTap = 0
mock_quartz.kCGEventTapOptionDefault = 0
mock_quartz.kCGKeyboardEventKeycode = 0
mock_quartz.kCGKeyboardEventAutorepeat = 1
mock_quartz.kCFRunLoopCommonModes = 0

mock_objc = MagicMock()
mock_appkit = MagicMock()
mock_app_services = MagicMock()
mock_pyobjc_tools = MagicMock()
mock_foundation = MagicMock()
mock_core_foundation = MagicMock()

sys.modules["objc"] = mock_objc
sys.modules["Quartz"] = mock_quartz
sys.modules["AppKit"] = mock_appkit
sys.modules["ApplicationServices"] = mock_app_services
sys.modules["PyObjCTools"] = mock_pyobjc_tools
sys.modules["PyObjCTools.AppHelper"] = mock_pyobjc_tools.AppHelper
sys.modules["Foundation"] = mock_foundation
sys.modules["CoreFoundation"] = mock_core_foundation

import pytest
from vimlayer.hint_overlay import HintOverlay

@pytest.fixture
def overlay(mocker):
    # Ensure Quartz in hint_overlay uses our mock
    mocker.patch("vimlayer.hint_overlay.Quartz", mock_quartz)
    
    # Mock dependencies within HintOverlay
    mocker.patch("vimlayer.hint_overlay.WindowManager")
    mocker.patch("vimlayer.hint_overlay.WatermarkManager")
    mocker.patch("vimlayer.hint_overlay.CheatSheetOverlay")
    mocker.patch("vimlayer.hint_overlay.Launcher")
    mocker.patch("vimlayer.hint_overlay.MouseController")
    mocker.patch("vimlayer.hint_overlay.config.load")
    mocker.patch("vimlayer.hint_overlay.config.load_keybindings")
    
    # Mocking internal constants that affect key blocking and flag detection
    mocker.patch("vimlayer.hint_overlay._KEYCODE_TO_CHAR", {
        4: "h", 38: "j", 40: "k", 37: "l", 49: "space", 34: "i", 9: "v", 11: "b", 3: "f", 13: "w", 44: "/", 53: "esc"
    })
    mocker.patch("vimlayer.hint_overlay._NAV_KEYCODES", set())
    mocker.patch("vimlayer.hint_overlay._KEY_ESCAPE", 53)
    mocker.patch("vimlayer.hint_overlay._KEY_BACKSPACE", 51)
    
    # Use simple bits for flags to ensure bitwise ops work as expected in mocks
    mocker.patch("vimlayer.hint_overlay._CMD_FLAG", 1)
    mocker.patch("vimlayer.hint_overlay._SHIFT_FLAG", 2)
    mocker.patch("vimlayer.hint_overlay._ALT_FLAG", 4)
    mocker.patch("vimlayer.hint_overlay._CTRL_FLAG", 8)
    
    # Ensure these are also used in test cases for CGEventGetFlags
    mock_quartz.kCGEventFlagMaskCommand = 1
    mock_quartz.kCGEventFlagMaskShift = 2
    mock_quartz.kCGEventFlagMaskAlternate = 4
    mock_quartz.kCGEventFlagMaskControl = 8
    
    # Mock Quartz.CGEventGetIntegerValueField to work correctly with mocked constants
    def side_effect(event, field):
        if field == 0: # kCGKeyboardEventKeycode
            return event.keycode
        if field == 1: # kCGKeyboardEventAutorepeat
            return getattr(event, "repeat", 0)
        return 0
    mock_quartz.CGEventGetIntegerValueField.side_effect = side_effect

    o = HintOverlay()
    o._binding_lookup = {
        (4, False, False, False, False): "move_left",
        (38, False, False, False, False): "move_down",
        (40, False, False, False, False): "move_up",
        (37, False, False, False, False): "move_right",
        (49, False, False, False, False): "click",
        (49, False, True, False, False): "right_click",
        (34, False, False, False, False): "insert_mode",
        (9, False, False, False, False): "toggle_drag",
        (11, True, False, False, False): "scroll_up",
        (3, True, False, False, False): "scroll_down",
        (11, False, False, False, False): "back",
        (13, False, False, False, False): "forward",
        (3, False, False, False, False): "toggle_all_hints",
        (44, False, False, False, False): "open_launcher",
        (44, False, True, False, False): "toggle_cheat_sheet",
    }
    # Mock the AppHelper.callAfter to execute the callback immediately for testing
    mock_pyobjc_tools.AppHelper.callAfter.side_effect = lambda f, *args: f(*args)
    return o

def test_normal_mode_navigation(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 4
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay._mouse_ctrl.move_relative.assert_called_with(-1, 0, False, False)

def test_drag_mode_navigation(overlay, mocker):
    overlay._dragging = True
    mock_event = MagicMock()
    mock_event.keycode = 38
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay._mouse_ctrl.move_relative.assert_called_with(0, 1, False, True)

def test_click_action(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 49
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    mocker.patch.object(overlay, "click_at_cursor")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay.click_at_cursor.assert_called_once()

def test_right_click_action(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 49
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 2 # Shift
    
    mocker.patch.object(overlay, "right_click_at_cursor")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay.right_click_at_cursor.assert_called_once()

def test_scroll_actions(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 3
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 8 # Ctrl
    
    mocker.patch.object(overlay, "scroll")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay.scroll.assert_called_with(-3)

def test_mouse_back_forward(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 11
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    mocker.patch.object(overlay, "mouse_back")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    assert result is None
    overlay.mouse_back.assert_called_once()

def test_toggle_hints(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 3
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    mocker.patch.object(overlay, "toggle_all_hints")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    assert result is None
    overlay.toggle_all_hints.assert_called_once()

def test_open_launcher(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 44
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    mocker.patch.object(overlay, "_open_launcher")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    assert result is None
    overlay._open_launcher.assert_called_once()

def test_escape_resets_typing(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 53
    mock_event.repeat = 0
    
    mocker.patch.object(overlay, "reset_typing")
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay.reset_typing.assert_called_once()

def test_enter_insert_mode(overlay, mocker):
    mock_event = MagicMock()
    mock_event.keycode = 34
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    mocker.patch.object(overlay, "enter_insert_mode")
    
    result = overlay._normal_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay.enter_insert_mode.assert_called_once()

def test_menu_mode_navigation(overlay, mocker):
    overlay._install_menu_tap()
    
    mock_event = MagicMock()
    mock_event.keycode = 40
    mock_event.repeat = 0
    mock_quartz.CGEventGetFlags.return_value = 0
    
    result = overlay._menu_tap_callback(None, mock_quartz.kCGEventKeyDown, mock_event, None)
    
    assert result is None
    overlay._mouse_ctrl.move_relative.assert_called_with(0, -1, False)
