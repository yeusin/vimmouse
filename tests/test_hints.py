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
    # Mock dependencies within HintOverlay
    mocker.patch("vimlayer.hint_overlay.WindowManager")
    mocker.patch("vimlayer.hint_overlay.WatermarkManager")
    mocker.patch("vimlayer.hint_overlay.CheatSheetOverlay")
    mocker.patch("vimlayer.hint_overlay.Launcher")
    mocker.patch("vimlayer.hint_overlay.MouseController")
    mocker.patch("vimlayer.hint_overlay.config.load")
    mocker.patch("vimlayer.hint_overlay.config.load_keybindings")
    mocker.patch("vimlayer.hint_overlay.accessibility.get_clickable_elements")
    mocker.patch("vimlayer.hint_overlay.accessibility.get_all_clickable_elements")
    mocker.patch("vimlayer.hint_overlay.accessibility.is_element_stale", return_value=False)
    mocker.patch("vimlayer.hint_overlay.mouse.element_center", return_value=(100, 100))
    mocker.patch("vimlayer.hint_overlay.mouse.click")
    
    # Mocking config.load_keybindings to return some default bindings
    from vimlayer import config
    config.load_keybindings.return_value = {
        "toggle_all_hints": {"keycode": 3}, # 'f'
    }
    
    o = HintOverlay()
    o._binding_lookup = {
        (3, False, False, False, False): "toggle_all_hints",
    }
    # Mock the window to avoid AttributeError: 'NoneType' object has no attribute 'contentView'
    o.window = MagicMock()
    
    # Mock the AppHelper.callAfter to execute the callback immediately for testing
    mock_pyobjc_tools.AppHelper.callAfter.side_effect = lambda f, *args: f(*args)
    return o

def test_toggle_hints_visibility(overlay, mocker):
    assert not overlay._hints_visible
    
    # Mock accessibility to return empty list so we don't crash in _populate
    mocker.patch.object(overlay, "_populate")
    
    # Toggle on
    overlay.toggle_hints()
    assert overlay._hints_visible
    
    # Toggle off
    overlay.toggle_hints()
    assert not overlay._hints_visible

def test_populate_and_filter_hints(overlay, mocker):
    # Mock elements
    mock_elements = [
        {"position": (10, 10), "size": (20, 20), "role": "button", "title": "Btn1"},
        {"position": (50, 50), "size": (20, 20), "role": "button", "title": "Btn2"},
    ]
    
    # Mock dependencies that _populate calls
    mocker.patch("vimlayer.hint_overlay._element_position", side_effect=lambda el: el["position"])
    mock_screen = MagicMock()
    mock_screen.size.width = 1920
    mock_screen.size.height = 1080
    mock_appkit.NSScreen.mainScreen.return_value.frame.return_value = mock_screen
    
    # We need to mock _create_hint_label to return a mock label
    mocker.patch.object(overlay, "_create_hint_label", return_value=MagicMock())
    mocker.patch.object(overlay, "_create_window_hint_label", return_value=MagicMock())
    mocker.patch.object(overlay, "_get_visible_windows", return_value=[])
    
    overlay._populate(mock_elements)
    
    # Should have 2 labels (Btn1 and Btn2)
    assert len(overlay.labels) == 2
    
    # Labels should be assigned hints based on _generate_element_hints
    hint1 = overlay.labels[0][0]
    hint2 = overlay.labels[1][0]
    
    assert hint1 != hint2
    
    # Test filtering
    overlay._hints_visible = True
    overlay.type_char(hint1[0]) # Type first char
    
    # If hint1[0] == hint2[0], both should be visible. If different, only one.
    if hint1[0] == hint2[0]:
        pass
    else:
        # One should be hidden
        hidden_count = 0
        for _, label, _, _ in overlay.labels:
            if any(call.args[0] is True for call in label.setHidden_.call_args_list):
                hidden_count += 1
        assert hidden_count == 1

def test_unique_hint_match_clicks(overlay, mocker):
    # Mock TWO labels so that 'A' is not a unique match
    mock_label1 = MagicMock()
    mock_label2 = MagicMock()
    mock_element_data1 = {"position": (10, 10), "size": (20, 20), "role": "button", "element": MagicMock()}
    mock_element_data2 = {"position": (20, 20), "size": (20, 20), "role": "button", "element": MagicMock()}
    
    # Ensure they start with same char but different full hints
    overlay.labels = [
        ("AB", mock_label1, mock_element_data1, "element"),
        ("AC", mock_label2, mock_element_data2, "element"),
    ]
    overlay._hints_visible = True
    
    mocker.patch.object(overlay, "_click_and_dismiss")
    
    # Type 'A' -> matches both, not unique
    overlay.type_char("A")
    overlay._click_and_dismiss.assert_not_called()
    
    # Type 'B' -> unique match 'AB'
    overlay.type_char("B")
    overlay._click_and_dismiss.assert_called_once()

def test_backspace_resets_filtering(overlay, mocker):
    mock_label1 = MagicMock()
    mock_label2 = MagicMock()
    mock_label3 = MagicMock()
    overlay.labels = [
        ("AAA", mock_label1, {"element": MagicMock()}, "element"),
        ("AAB", mock_label2, {"element": MagicMock()}, "element"),
        ("ABC", mock_label3, {"element": MagicMock()}, "element"),
    ]
    overlay._hints_visible = True
    
    # Type 'A' -> all three visible
    overlay.type_char("A")
    
    # Type 'A' -> AAA and AAB visible, ABC hidden
    overlay.type_char("A")
    mock_label3.setHidden_.assert_called_with(True)
    
    # Backspace
    overlay.backspace()
    assert overlay.typed == "A"
    # All three should be shown again
    mock_label1.setHidden_.assert_called_with(False)
    mock_label2.setHidden_.assert_called_with(False)
    mock_label3.setHidden_.assert_called_with(False)

def test_window_hint_switching(overlay, mocker):
    mock_label = MagicMock()
    mock_window_data = {"kCGWindowNumber": 123}
    overlay.labels = [("W", mock_label, mock_window_data, "window")]
    overlay._hints_visible = True
    
    mocker.patch.object(overlay, "_switch_to_window")
    
    overlay.type_char("W")
    
    assert not overlay._hints_visible
    overlay._switch_to_window.assert_called_with(mock_window_data)

def test_reset_typing(overlay):
    mock_label = MagicMock()
    overlay.labels = [("AB", mock_label, {}, "element")]
    overlay._hints_visible = True
    overlay.typed = "A"
    
    # Ensure cheat sheet is NOT visible
    overlay._cheat_sheet.is_visible.return_value = False
    
    # 1. Reset when something is typed -> clears typing but keeps hints visible
    overlay.reset_typing()
    assert overlay.typed == ""
    assert overlay._hints_visible
    mock_label.setHidden_.assert_called_with(False)
    
    # 2. Reset when nothing is typed -> dismisses hints
    overlay.reset_typing()
    assert not overlay._hints_visible
