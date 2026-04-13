"""Global hotkey registration (platform-agnostic wrapper)."""

import logging
from .platforms import get_platform

log = logging.getLogger(__name__)


def suspend(value=True):
    get_platform().hotkey.suspend(value)


def get_hotkey():
    return get_platform().hotkey.get_hotkey()


def register(callback, keycode, flags, is_primary=False):
    return get_platform().hotkey.register(callback, keycode, flags, is_primary)


def unregister_all():
    get_platform().hotkey.unregister_all()


def update_hotkey(keycode, flags):
    get_platform().hotkey.update_hotkey(keycode, flags)
