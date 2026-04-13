from typing import List, Optional, Tuple, Callable, Any
from ..base import UIProvider
from .hint_overlay import X11HintOverlay
from .ui_components import Watermark, SettingsWindow
from .launcher import X11Launcher

class X11UI(UIProvider):
    def __init__(self):
        self._watermark = None
        self._settings_window = None
        self._launcher = None

    def show_watermark(self, mode: str, timeout: Optional[float] = None) -> None:
        if not self._watermark:
            self._watermark = Watermark(mode)
        self._watermark.show_mode(mode, timeout)

    def hide_watermark(self) -> None:
        if self._watermark:
            self._watermark.hide()
    def show_cheat_sheet(self, sections: List[Tuple[str, List[Tuple[str, str]]]]) -> None: pass
    def hide_cheat_sheet(self) -> None: pass
    def is_cheat_sheet_visible(self) -> bool: return False
    
    def show_launcher(self, on_dismiss: Optional[Callable] = None) -> None:
        if not self._launcher:
            self._launcher = X11Launcher(on_dismiss=on_dismiss)
        else:
            self._launcher._on_dismiss = on_dismiss
        self._launcher.show_launcher()

    def hide_launcher(self) -> None:
        if self._launcher:
            self._launcher.hide()

    def is_launcher_visible(self) -> bool:
        return self._launcher is not None and self._launcher.isVisible()
    
    def show_settings(self) -> None:
        if not self._settings_window:
            self._settings_window = SettingsWindow()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()
    
    def create_hint_overlay(self, on_mode_change: Optional[Callable] = None) -> Any:
        return X11HintOverlay(on_mode_change=on_mode_change)
