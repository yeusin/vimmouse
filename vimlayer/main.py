"""VimLayer - Spotlight-like UI element search and click for macOS."""

import os
import sys

# Remove environment variables set by py2app that can interfere with subprocesses.
# These are set by the py2app bootstrapper but can break external subprocesses.
for var in ["ARGVZERO", "PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE"]:
    os.environ.pop(var, None)

import logging
import signal
import subprocess
from AppKit import (
    NSApplication,
    NSBundle,
    NSMenu,
    NSMenuItem,
    NSOffState,
    NSOnState,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)
from Foundation import NSObject
from PyObjCTools import AppHelper
import objc

objc.loadBundle(
    "ServiceManagement",
    globals(),
    "/System/Library/Frameworks/ServiceManagement.framework",
)

from vimlayer import config
from vimlayer import hotkey
from vimlayer import hint_overlay
from vimlayer.settings import SettingsController


class StatusBarController(NSObject):
    def init(self):
        self = objc.super(StatusBarController, self).init()
        if self is None:
            return None
        self._settings_ctrl = SettingsController.alloc().init()

        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._status_item.setTitle_("VL")

        menu = NSMenu.alloc().init()
        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings\u2026", b"openSettings:", ""
        )
        settings_item.setTarget_(self)
        menu.addItem_(settings_item)

        self._login_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Launch at Login", b"toggleLaunchAtLogin:", ""
        )
        self._login_item.setTarget_(self)
        self._updateLoginItemState()
        menu.addItem_(self._login_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", b"quit:", ""
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)
        return self

    @objc.typedSelector(b"v@:@")
    def openSettings_(self, sender):
        self._settings_ctrl.showWindow()

    @objc.typedSelector(b"v@:@")
    def toggleLaunchAtLogin_(self, sender):
        svc = SMAppService.mainAppService()  # noqa: F821
        if svc.status() == 1:  # enabled
            svc.unregisterAndReturnError_(None)
        else:
            svc.registerAndReturnError_(None)
        self._updateLoginItemState()

    def _updateLoginItemState(self):
        enabled = SMAppService.mainAppService().status() == 1  # noqa: F821
        self._login_item.setState_(NSOnState if enabled else NSOffState)

    @objc.typedSelector(b"v@:@")
    def quit_(self, sender):
        AppHelper.stopEventLoop()


def _ensure_accessibility():
    """Reset stale accessibility entry and re-prompt if needed."""
    log = logging.getLogger(__name__)
    if AXIsProcessTrusted():
        log.info("Accessibility: already trusted")
        return True

    bundle_id = NSBundle.mainBundle().bundleIdentifier()
    if bundle_id:
        log.info("Accessibility: resetting TCC entry for %s", bundle_id)
        subprocess.run(
            ["tccutil", "reset", "Accessibility", bundle_id],
            capture_output=True,
        )

    trusted = AXIsProcessTrustedWithOptions(
        {kAXTrustedCheckOptionPrompt: True}
    )
    if not trusted:
        log.warning("Accessibility: not yet trusted, prompting user")
    return trusted


def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    _ensure_accessibility()

    app = NSApplication.sharedApplication()
    # No Dock icon, no app switcher entry
    app.setActivationPolicy_(2)  # NSApplicationActivationPolicyProhibited

    status_bar_ctrl = StatusBarController.alloc().init()

    def on_mode_change(mode):
        if mode:
            status_bar_ctrl._status_item.setTitle_(f"VL:{mode}")
        else:
            status_bar_ctrl._status_item.setTitle_("VL")

    overlay = hint_overlay.HintOverlay(on_mode_change=on_mode_change)
    status_bar_ctrl._settings_ctrl._overlay = overlay

    def on_hotkey():
        # Schedule on main thread since CGEventTap callback runs on CF runloop
        AppHelper.callAfter(overlay.return_to_normal)

    cfg = config.load()
    if not hotkey.register(on_hotkey, keycode=cfg["keycode"], flags=cfg["flags"]):
        return

    overlay.show()

    signal.signal(signal.SIGINT, lambda *_: AppHelper.stopEventLoop())

    logging.getLogger(__name__).info("VimLayer running")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
