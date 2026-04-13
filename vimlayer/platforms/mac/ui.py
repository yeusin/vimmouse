"""macOS implementation of UI provider."""

from typing import Callable, List, Optional, Tuple
from .hint_overlay import HintOverlay
from .ui_components import WatermarkManager, CheatSheetOverlay
from .launcher import Launcher
from .settings import SettingsController
from ..base import UIProvider


class MacUI(UIProvider):
    def __init__(self):
        self._watermark = WatermarkManager()
        self._cheat_sheet = CheatSheetOverlay()
        self._launcher = Launcher()
        self._settings_ctrl = SettingsController.alloc().init()

    def show_watermark(self, mode: str, timeout: Optional[float] = None) -> None:
        self._watermark.set_mode(mode, timeout=timeout)

    def hide_watermark(self) -> None:
        self._watermark.hide()

    def show_cheat_sheet(self, sections: List[Tuple[str, List[Tuple[str, str]]]]) -> None:
        self._cheat_sheet.show(sections)

    def hide_cheat_sheet(self) -> None:
        self._cheat_sheet.hide()

    def is_cheat_sheet_visible(self) -> bool:
        return self._cheat_sheet.is_visible()

    def show_launcher(self, on_dismiss: Optional[Callable] = None) -> None:
        if on_dismiss: self._launcher._on_dismiss = on_dismiss
        self._launcher.show()

    def hide_launcher(self) -> None:
        self._launcher.dismiss()

    def is_launcher_visible(self) -> bool:
        return self._launcher.is_visible()

    def show_settings(self) -> None:
        self._settings_ctrl.showWindow()

    def create_hint_overlay(self, on_mode_change: Optional[Callable] = None) -> HintOverlay:
        overlay = HintOverlay(on_mode_change=on_mode_change)
        self._settings_ctrl._overlay = overlay
        return overlay
