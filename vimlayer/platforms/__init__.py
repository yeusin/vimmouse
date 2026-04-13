"""Platform-specific provider discovery."""

import sys
import logging
from .base import PlatformProvider

log = logging.getLogger(__name__)

_active_platform: PlatformProvider = None


def get_platform() -> PlatformProvider:
    """Return the active platform provider."""
    global _active_platform
    if _active_platform is None:
        if sys.platform == "darwin":
            from .mac.provider import MacPlatformProvider
            _active_platform = MacPlatformProvider()
        elif sys.platform == "linux":
            from .x11.provider import X11PlatformProvider
            _active_platform = X11PlatformProvider()
        else:
            raise NotImplementedError(f"Platform {sys.platform} not supported")
    return _active_platform
