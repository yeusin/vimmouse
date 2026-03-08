import pytest
import Quartz
from unittest.mock import MagicMock
from vimlayer.hint_overlay import HintOverlay
from vimlayer.ui import WatermarkManager

_CTRL_FLAG = 1 << 18

@pytest.fixture
def overlay(mocker):
    mocker.patch("vimlayer.hint_overlay.MouseController")
    # Patch WatermarkManager to capture the callback
    mocker.patch("vimlayer.hint_overlay.WatermarkManager")
    mock_cs = mocker.patch("vimlayer.hint_overlay.CheatSheetOverlay").return_value
    mock_cs.is_visible.return_value = False
    mocker.patch("vimlayer.hint_overlay.WindowManager")
    mocker.patch("vimlayer.hint_overlay.Launcher")
    mocker.patch("vimlayer.config.load_keybindings", return_value={})
    return HintOverlay()

def test_window_mode_deactivation_on_watermark_hide(overlay):
    # Set window mode pending
    overlay._window_cmd_pending = True
    
    # Simulate watermark hiding with "WINDOW" mode
    overlay._on_watermark_hide("WINDOW")
    
    # Should be deactivated
    assert overlay._window_cmd_pending is False

def test_window_mode_not_deactivated_on_other_watermark_hide(overlay):
    # Set window mode pending
    overlay._window_cmd_pending = True
    
    # Simulate watermark hiding with "NORMAL" mode
    overlay._on_watermark_hide("NORMAL")
    
    # Should still be pending
    assert overlay._window_cmd_pending is True

def test_watermark_manager_callback_invocation(mocker):
    # Test that WatermarkManager calls the callback when flash timeout occurs
    mock_callback = MagicMock()
    # Mock AppHelper.callLater to invoke the callback immediately
    mocker.patch("PyObjCTools.AppHelper.callLater", side_effect=lambda delay, cb: cb())
    
    wm = WatermarkManager(on_hide=mock_callback)
    wm.set_mode("TEST")
    
    mock_callback.assert_called_with("TEST")

def test_watermark_manager_hide_invocation(mocker):
    # Test that WatermarkManager calls the callback when hide is called manually
    mock_callback = MagicMock()
    wm = WatermarkManager(on_hide=mock_callback)
    wm.hide()
    
    # "NORMAL" is the default mode
    mock_callback.assert_called_with("NORMAL")

def test_escape_hides_watermark(overlay, mocker):
    mock_event = MagicMock()
    # 53 is Escape
    mocker.patch("Quartz.CGEventGetIntegerValueField", return_value=53)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    # Track AppHelper.callAfter
    mock_call_after = mocker.patch("PyObjCTools.AppHelper.callAfter")
    
    # Call the callback
    overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Check if self._watermark.hide was called via AppHelper.callAfter
    found_hide = False
    for call in mock_call_after.call_args_list:
        cb = call[0][0]
        if cb == overlay._watermark.hide:
            found_hide = True
            break
    assert found_hide

def test_window_prefix_any_key_hides_watermark(overlay, mocker):
    overlay._window_cmd_pending = True
    mock_event = MagicMock()
    # Any key (e.g. 'z')
    mocker.patch("Quartz.CGEventGetIntegerValueField", return_value=6)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    mock_call_after = mocker.patch("PyObjCTools.AppHelper.callAfter")
    
    overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Should have called watermark.hide
    found_hide = False
    for call in mock_call_after.call_args_list:
        cb = call[0][0]
        if cb == overlay._watermark.hide:
            found_hide = True
            break
    assert found_hide
    assert overlay._window_cmd_pending is False

def test_window_mode_deactivation_triggers_auto_insert(overlay, mocker):
    overlay.window = MagicMock()
    overlay._pid = 123
    overlay._window_cmd_pending = True
    overlay._auto_insert_enabled = True
    
    # Mock focused element as an input element
    mock_element = MagicMock()
    mocker.patch("vimlayer.accessibility.get_focused_element", return_value=mock_element)
    mocker.patch("vimlayer.accessibility.is_input_element", return_value=True)
    mocker.patch("vimlayer.accessibility.get_element_pid", return_value=overlay._pid)
    
    # Track enter_insert_mode
    mock_enter_insert = mocker.patch.object(overlay, "enter_insert_mode")
    
    # Simulate watermark hiding with "WINDOW" mode
    overlay._on_watermark_hide("WINDOW")
    
    # Should have called enter_insert_mode(auto=True)
    mock_enter_insert.assert_called_with(auto=True)

def test_window_mode_notifies_status_bar(overlay, mocker):
    mock_event = MagicMock()
    # Mock window_prefix keybinding
    overlay._binding_lookup = {(1, False, False): "window_prefix"}
    # keycode 1, ctrl=False, shift=False
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=lambda ev, field: 1 if field == Quartz.kCGKeyboardEventKeycode else 0)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    mock_notify = mocker.patch.object(overlay, "_notify_mode")
    
    overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    mock_notify.assert_called_with("W")

def test_window_mode_restores_previous_mode(overlay, mocker):
    overlay._window_cmd_pending = True
    overlay._dragging = True
    mock_event = MagicMock()
    # Any key (e.g. 'z')
    mocker.patch("Quartz.CGEventGetIntegerValueField", return_value=6)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    mock_notify = mocker.patch.object(overlay, "_notify_mode")
    
    overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Should restore "D" if dragging
    mock_notify.assert_called_with("D")

def test_auto_insert_suppressed_during_window_mode(overlay, mocker):
    overlay.window = MagicMock()
    overlay._pid = 123
    overlay._window_cmd_pending = True
    overlay._auto_insert_enabled = True
    
    # Mock focused element as an input element
    mock_element = MagicMock()
    mocker.patch("vimlayer.accessibility.get_focused_element", return_value=mock_element)
    mocker.patch("vimlayer.accessibility.is_input_element", return_value=True)
    mocker.patch("vimlayer.accessibility.get_element_pid", return_value=overlay._pid)
    
    # Track enter_insert_mode
    mock_enter_insert = mocker.patch.object(overlay, "enter_insert_mode")
    
    # Directly call _check_focus_and_auto_insert
    overlay._check_focus_and_auto_insert(mock_element)
    
    # Should NOT have called enter_insert_mode because _window_cmd_pending is True
    mock_enter_insert.assert_not_called()

def test_window_cycle_keeps_window_mode(overlay, mocker):
    overlay._window_cmd_pending = True
    mock_event = MagicMock()
    # Mock win_cycle action
    overlay._window_binding_lookup = {(13, False): "win_cycle"}  # 'w' keycode 13
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=lambda ev, field: 13 if field == Quartz.kCGKeyboardEventKeycode else 0)
    mocker.patch("Quartz.CGEventGetFlags", return_value=0)
    
    mock_cycle = mocker.patch.object(overlay, "cycle_window")
    
    overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Mode should still be pending
    assert overlay._window_cmd_pending is True

def test_nested_window_prefix_keeps_window_mode(overlay, mocker):
    overlay._window_cmd_pending = True
    mock_event = MagicMock()
    # Mock window_prefix action
    overlay._binding_lookup = {(13, True, False): "window_prefix"} # ctrl+w
    mocker.patch("Quartz.CGEventGetIntegerValueField", side_effect=lambda ev, field: 13 if field == Quartz.kCGKeyboardEventKeycode else 0)
    mocker.patch("Quartz.CGEventGetFlags", return_value=_CTRL_FLAG)
    
    overlay._normal_tap_callback(None, Quartz.kCGEventKeyDown, mock_event, None)
    
    # Mode should still be pending
    assert overlay._window_cmd_pending is True
