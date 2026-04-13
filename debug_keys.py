import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

log.info("--- SYSTEM INFO ---")
log.info(f"OS: {sys.platform}")
log.info(f"XDG_SESSION_TYPE: {os.environ.get('XDG_SESSION_TYPE')}")
log.info(f"WAYLAND_DISPLAY: {os.environ.get('WAYLAND_DISPLAY')}")
log.info(f"DISPLAY: {os.environ.get('DISPLAY')}")

try:
    from pynput import keyboard
    log.info("pynput is installed.")
    # Check backend
    try:
        from pynput.keyboard._xorg import Listener as X11Listener
        log.info("Backend: X11")
    except ImportError:
        try:
            from pynput.keyboard._win32 import Listener as WinListener
            log.info("Backend: Windows")
        except ImportError:
            log.info("Backend: evdev / Other")
except ImportError:
    log.error("pynput is NOT installed.")
    sys.exit(1)

def on_press(key):
    try:
        k_str = f"{key}"
        vk = getattr(key, 'vk', 'N/A')
        log.info(f"Key: {k_str:<15} | vk: {vk:<5}")
    except Exception as e:
        log.error(f"Error in on_press: {e}")

def on_release(key):
    if key == keyboard.Key.esc:
        log.info("Escape pressed. Stopping...")
        return False

log.info("\nStarting global listener... (Press ESC to stop)")
try:
    # Use suppress=False to let keys through to other apps
    with keyboard.Listener(on_press=on_press, on_release=on_release, suppress=False) as listener:
        listener.join()
except Exception as e:
    log.error(f"Error starting listener: {e}")
    log.info("\nTIP: If on Linux, ensure you have libxtst6 installed.")
    log.info("Run: sudo apt install libxtst6")
