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
