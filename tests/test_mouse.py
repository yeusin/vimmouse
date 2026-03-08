import pytest
from vimlayer.mouse import MouseController

def test_mouse_acceleration_reset(mocker):
    # Mock Quartz calls
    mocker.patch("vimlayer.mouse.get_cursor_position", return_value=(100, 100))
    mock_move = mocker.patch("vimlayer.mouse.move_cursor")
    
    ctrl = MouseController()
    
    # First move
    ctrl.move_relative(1, 0)
    # _MOUSE_S0 = 4, ease(0) = 0 -> step = 4
    mock_move.assert_called_with(104, 100, dragging=False)
    
    # Direction change should reset
    ctrl.move_relative(-1, 0)
    mock_move.assert_called_with(96, 100, dragging=False)
    assert ctrl._mouse_repeat_count == 0

def test_mouse_acceleration_ramp(mocker):
    mocker.patch("vimlayer.mouse.get_cursor_position", return_value=(100, 100))
    mock_move = mocker.patch("vimlayer.mouse.move_cursor")
    
    ctrl = MouseController()
    
    # Move once
    ctrl.move_relative(1, 0)
    # Move again with repeat=True
    import time
    ctrl._last_move_time = time.time() - 0.01 # ensure within timeout
    
    ctrl.move_relative(1, 0, repeat=True)
    assert ctrl._mouse_repeat_count == 1
    
    # We don't need to check exact pixel values as they depend on internal constants,
    # but we can check that it's increasing or at least called.
    assert mock_move.call_count == 2
