"""Abstract base classes for platform-specific providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Callable


class WindowManagerProvider(ABC):
    @abstractmethod
    def tile_window(self, quadrant: int) -> None:
        """Tile the focused window to a quadrant (1-4)."""
        pass

    @abstractmethod
    def tile_window_sixth(self, col: int, row: int) -> None:
        """Tile the focused window to a sixth of the screen."""
        pass

    @abstractmethod
    def tile_window_half(self, side: str) -> None:
        """Tile the focused window to a half (left, right, top, bottom)."""
        pass

    @abstractmethod
    def center_window(self) -> None:
        """Center the focused window."""
        pass

    @abstractmethod
    def toggle_maximize(self) -> None:
        """Toggle maximize state of the focused window."""
        pass


class MouseProvider(ABC):
    @abstractmethod
    def move_relative(self, dx: int, dy: int, repeat: bool = False, dragging: bool = False) -> None:
        """Move the mouse cursor with smooth acceleration."""
        pass

    @abstractmethod
    def get_cursor_position(self) -> Tuple[float, float]:
        """Return the current cursor position as (x, y)."""
        pass

    @abstractmethod
    def move_cursor(self, x: float, y: float, dragging: bool = False) -> None:
        """Move the mouse cursor to (x, y)."""
        pass

    @abstractmethod
    def click(self, x: float, y: float) -> None:
        """Perform a left click at (x, y)."""
        pass

    @abstractmethod
    def right_click(self, x: float, y: float) -> None:
        """Perform a right click at (x, y)."""
        pass

    @abstractmethod
    def mouse_down(self, x: float, y: float) -> None:
        """Press and hold left mouse button at (x, y)."""
        pass

    @abstractmethod
    def mouse_up(self, x: float, y: float) -> None:
        """Release left mouse button at (x, y)."""
        pass

    @abstractmethod
    def back_button(self) -> None:
        """Simulate mouse back button."""
        pass

    @abstractmethod
    def forward_button(self) -> None:
        """Simulate mouse forward button."""
        pass

    @abstractmethod
    def scroll(self, lines: int) -> None:
        """Scroll vertically."""
        pass

    @abstractmethod
    def element_center(self, position: Any, size: Any) -> Tuple[float, float]:
        """Get center of a UI element from its position/size attributes."""
        pass


class HotkeyProvider(ABC):
    @abstractmethod
    def register(self, callback: Callable, keycode: int, flags: int, is_primary: bool = False) -> bool:
        """Register a global hotkey."""
        pass

    @abstractmethod
    def unregister_all(self) -> None:
        """Unregister all hotkeys except primary."""
        pass

    @abstractmethod
    def update_hotkey(self, keycode: int, flags: int) -> None:
        """Update the primary hotkey."""
        pass

    @abstractmethod
    def get_hotkey(self) -> Tuple[int, int]:
        """Get current primary hotkey (keycode, flags)."""
        pass

    @abstractmethod
    def suspend(self, value: bool = True) -> None:
        """Suspend/resume hotkey interception."""
        pass


class AccessibilityProvider(ABC):
    @abstractmethod
    def get_focused_element(self) -> Optional[Any]:
        """Get the globally focused UI element."""
        pass

    @abstractmethod
    def get_element_pid(self, element: Any) -> Optional[int]:
        """Get the PID of the application owning this element."""
        pass

    @abstractmethod
    def is_input_element(self, element: Any) -> bool:
        """Check if an element is a text input."""
        pass

    @abstractmethod
    def is_element_stale(self, element: Any) -> bool:
        """Check if an element is no longer valid."""
        pass

    @abstractmethod
    def get_clickable_elements(self, pid: int) -> List[Dict[str, Any]]:
        """Get clickable elements visible on screen for a PID."""
        pass

    @abstractmethod
    def get_all_clickable_elements(self, pid_bounds_map: Dict[int, List[Tuple[float, float, float, float]]]) -> List[Dict[str, Any]]:
        """Get clickable elements for multiple PIDs."""
        pass


class UIProvider(ABC):
    @abstractmethod
    def show_watermark(self, mode: str, timeout: Optional[float] = None) -> None:
        """Show the mode watermark."""
        pass

    @abstractmethod
    def hide_watermark(self) -> None:
        """Hide the mode watermark."""
        pass

    @abstractmethod
    def show_cheat_sheet(self, sections: List[Tuple[str, List[Tuple[str, str]]]]) -> None:
        """Show the shortcuts cheat sheet."""
        pass

    @abstractmethod
    def hide_cheat_sheet(self) -> None:
        """Hide the shortcuts cheat sheet."""
        pass

    @abstractmethod
    def is_cheat_sheet_visible(self) -> bool:
        """Is the cheat sheet visible?"""
        pass

    @abstractmethod
    def show_launcher(self, on_dismiss: Optional[Callable] = None) -> None:
        """Show the app launcher."""
        pass

    @abstractmethod
    def hide_launcher(self) -> None:
        """Hide the app launcher."""
        pass

    @abstractmethod
    def is_launcher_visible(self) -> bool:
        """Is the launcher visible?"""
        pass

    @abstractmethod
    def show_settings(self) -> None:
        """Show the settings window."""
        pass

    @abstractmethod
    def create_hint_overlay(self, on_mode_change: Optional[Callable] = None) -> Any:
        """Create and return the HintOverlay instance."""
        pass


class PlatformProvider(ABC):
    @property
    @abstractmethod
    def window_manager(self) -> WindowManagerProvider: pass

    @property
    @abstractmethod
    def mouse(self) -> MouseProvider: pass

    @property
    @abstractmethod
    def hotkey(self) -> HotkeyProvider: pass

    @property
    @abstractmethod
    def accessibility(self) -> AccessibilityProvider: pass

    @property
    @abstractmethod
    def ui(self) -> UIProvider: pass

    @abstractmethod
    def get_default_config(self) -> Dict[str, Any]:
        """Return the default configuration for this platform."""
        pass

    @abstractmethod
    def get_default_keybindings(self) -> Dict[str, Any]:
        """Return the default keybindings for this platform."""
        pass

    @abstractmethod
    def format_hotkey(self, keycode: int, flags: int, use_symbols: bool = True) -> str:
        """Format a hotkey for display."""
        pass

    @abstractmethod
    def format_binding(self, spec: Any, use_symbols: bool = True) -> str:
        """Format a keybinding for display."""
        pass

    @abstractmethod
    def run(self) -> None:
        """Start the application event loop."""
        pass
