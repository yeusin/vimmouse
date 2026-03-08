import pytest
from unittest.mock import MagicMock
import Quartz
from vimlayer.hint_overlay import HintOverlay

@pytest.fixture
def overlay(mocker):
    mocker.patch("vimlayer.hint_overlay.MouseController")
    mocker.patch("vimlayer.hint_overlay.WatermarkManager")
    mock_cs = mocker.patch("vimlayer.hint_overlay.CheatSheetOverlay").return_value
    mock_cs.is_visible.return_value = False
    mocker.patch("vimlayer.hint_overlay.WindowManager")
    mocker.patch("vimlayer.hint_overlay.Launcher")
    mocker.patch("vimlayer.config.load_keybindings", return_value={})
    return HintOverlay()

def test_block_arrow_keys(overlay, mocker):
    # Mock CGEvent
    mock_event = MagicMock()
    
    # Mock CGEventGetIntegerValueField to return Left Arrow keycode (123)
    def get_int_value(ev, field):
        if field == Quartz.kCGKeyboardEventKeycode:
            return 123
        if field == Quartz.kCGKeyboardEventAutorepeat:
            return 0
        return 0
    
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=get_int_value)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    # Track AppHelper.callAfter
    mock_call_after = mocker.patch("PyObjCTools.AppHelper.callAfter")
    
    # Call the callback
    res = overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Should return None (blocked)
    assert res is None
    
    # Find the callback that sets mode to NORMAL
    found = False
    for call in mock_call_after.call_args_list:
        cb = call[0][0]
        cb()
        if overlay._watermark.set_mode.called:
            overlay._watermark.set_mode.assert_called_with("NORMAL")
            found = True
            break
    assert found

def test_block_unbound_alphanumeric_keys(overlay, mocker):
    mock_event = MagicMock()
    
    # Mock CGEventGetIntegerValueField to return 'z' keycode (6)
    def get_int_value(ev, field):
        if field == Quartz.kCGKeyboardEventKeycode:
            return 6
        return 0
    
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=get_int_value)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    mock_call_after = mocker.patch("PyObjCTools.AppHelper.callAfter")
    
    # Call the callback
    res = overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    assert res is None
    
    found = False
    for call in mock_call_after.call_args_list:
        cb = call[0][0]
        cb()
        if overlay._watermark.set_mode.called:
            overlay._watermark.set_mode.assert_called_with("NORMAL")
            found = True
            break
    assert found

def test_type_hint_char_when_hints_visible(overlay, mocker):
    mock_event = MagicMock()
    overlay._hints_visible = True
    
    # Mock CGEventGetIntegerValueField to return 'z' keycode (6)
    def get_int_value(ev, field):
        if field == Quartz.kCGKeyboardEventKeycode:
            return 6
        return 0
    
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=get_int_value)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    # We should NOT show watermark, we should call type_char
    mock_call_after = mocker.patch("PyObjCTools.AppHelper.callAfter")
    mock_type_char = mocker.patch.object(overlay, "type_char")
    
    res = overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    assert res is None
    
    # Execute callAfter lambdas
    for call in mock_call_after.call_args_list:
        call[0][0]()
        
    mock_type_char.assert_called_with("Z")
    # Watermark should NOT be shown
    assert not overlay._watermark.set_mode.called

def test_pass_other_keys(overlay, mocker):
    mock_event = MagicMock()
    
    # Mock CGEventGetIntegerValueField to return some other keycode (e.g., 1000 - unknown)
    def get_int_value(ev, field):
        if field == Quartz.kCGKeyboardEventKeycode:
            return 1000
        return 0
    
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=get_int_value)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    res = overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Should return the event (passed through)
    assert res == mock_event
