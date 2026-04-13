"""Hint overlay (platform-agnostic wrapper)."""

from .platforms import get_platform

def HintOverlay(on_mode_change=None):
    return get_platform().ui.create_hint_overlay(on_mode_change=on_mode_change)

# We need to expose _WINDOW_ACTIONS for main.py.
# This might be slightly different per platform, but the keys are consistent.
# For now, let's assume we can get it from the mac implementation if on mac,
# or define a common one if it's truly platform-independent logic that uses WindowManager.

try:
    import sys
    if sys.platform == 'darwin':
        from .platforms.mac.hint_overlay import _WINDOW_ACTIONS
    elif sys.platform == 'linux':
        from .platforms.x11.hint_overlay import _WINDOW_ACTIONS
    else:
        # Define a basic one for other platforms
        _WINDOW_ACTIONS = {} 
except ImportError:
    _WINDOW_ACTIONS = {}
