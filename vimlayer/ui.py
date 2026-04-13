"""Reusable UI components (platform-agnostic wrapper)."""

from .platforms import get_platform

class WatermarkManager:
    def __init__(self, mode_text="NORMAL", on_hide=None):
        self._provider = get_platform().ui

    def set_mode(self, text, timeout=None):
        self._provider.show_watermark(text, timeout=timeout)

    def flash(self, timeout=None):
        self._provider.show_watermark("NORMAL", timeout=timeout)

    def hide(self):
        self._provider.hide_watermark()

class CheatSheetOverlay:
    def __init__(self):
        self._provider = get_platform().ui

    def toggle(self, sections):
        if self._provider.is_cheat_sheet_visible():
            self._provider.hide_cheat_sheet()
        else:
            self._provider.show_cheat_sheet(sections)

    def show(self, sections):
        self._provider.show_cheat_sheet(sections)

    def hide(self):
        self._provider.hide_cheat_sheet()

    def is_visible(self):
        return self._provider.is_cheat_sheet_visible()

def ensure_edit_menu():
    # Only relevant for macOS
    import sys
    if sys.platform == 'darwin':
        from .platforms.mac.ui_components import ensure_edit_menu as mac_ensure
        mac_ensure()
