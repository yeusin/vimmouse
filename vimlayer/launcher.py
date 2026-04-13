"""Launcher (platform-agnostic wrapper)."""

from typing import Callable, Optional
from .platforms import get_platform

class Launcher:
    def __init__(self, on_dismiss: Optional[Callable] = None):
        self._on_dismiss = on_dismiss
        self._provider = get_platform().ui

    def show(self):
        self._provider.show_launcher(on_dismiss=self._on_dismiss)

    def dismiss(self):
        self._provider.hide_launcher()

    def is_visible(self):
        return self._provider.is_launcher_visible()
