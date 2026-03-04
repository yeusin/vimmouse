"""VimMouse - Spotlight-like UI element search and click for macOS."""

import logging
import signal
from AppKit import (
    NSApplication,
    NSApp,
    NSMenu,
    NSMenuItem,
    NSOffState,
    NSOnState,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject
from PyObjCTools import AppHelper
import objc

objc.loadBundle(
    "ServiceManagement",
    globals(),
    "/System/Library/Frameworks/ServiceManagement.framework",
)

import config
import hotkey
import hint_overlay
from settings import SettingsController


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
        self._status_item.setTitle_("VM")

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


def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    app = NSApplication.sharedApplication()
    # No Dock icon, no app switcher entry
    app.setActivationPolicy_(2)  # NSApplicationActivationPolicyProhibited

    status_bar_ctrl = StatusBarController.alloc().init()

    def on_mode_change(mode):
        if mode:
            status_bar_ctrl._status_item.setTitle_(f"VM:{mode}")
        else:
            status_bar_ctrl._status_item.setTitle_("VM")

    overlay = hint_overlay.HintOverlay(on_mode_change=on_mode_change)
    status_bar_ctrl._settings_ctrl._overlay = overlay

    def on_hotkey():
        # Schedule on main thread since CGEventTap callback runs on CF runloop
        AppHelper.callAfter(overlay.toggle)

    cfg = config.load()
    if not hotkey.register(on_hotkey, keycode=cfg["keycode"], flags=cfg["flags"]):
        return

    signal.signal(signal.SIGINT, lambda *_: AppHelper.stopEventLoop())

    logging.getLogger(__name__).info("VimMouse running")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
