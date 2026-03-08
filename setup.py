import os
import atexit
import zlib
from setuptools import setup

# Hack for py2app: zlib has no __file__ in some Python builds
if not hasattr(zlib, "__file__"):
    dummy_zlib = os.path.abspath("dummy_zlib.so")
    if not os.path.exists(dummy_zlib):
        with open(dummy_zlib, "wb") as f:
            pass
    zlib.__file__ = dummy_zlib

# Hack for PyObjCTools namespace issue with py2app
try:
    import PyObjCTools
    if not os.path.exists(os.path.join(PyObjCTools.__path__[0], "__init__.py")):
        with open(os.path.join(PyObjCTools.__path__[0], "__init__.py"), "w") as f:
            pass
except (ImportError, AttributeError, IndexError):
    pass

# Hack to avoid py2app error: install_requires is no longer supported
# when pyproject.toml is present.
if os.path.exists("pyproject.toml"):
    os.rename("pyproject.toml", "_pyproject.toml")
    atexit.register(lambda: os.rename("_pyproject.toml", "pyproject.toml") if os.path.exists("_pyproject.toml") else None)

version = os.environ.get("VIMLAYER_VERSION", "dev")

setup(
    app=["vimlayer/main.py"],
    options={
        "py2app": {
            "argv_emulation": False,
            "plist": {
                "CFBundleName": "VimLayer",
                "CFBundleIdentifier": "com.vimlayer.app",
                "CFBundleVersion": version,
                "CFBundleShortVersionString": version,
                "LSUIElement": True,
                "NSAccessibilityUsageDescription": "VimLayer needs Accessibility access to detect UI elements and simulate clicks.",
            },
            "packages": [
                "objc",
                "AppKit",
                "Foundation",
                "Quartz",
                "CoreFoundation",
                "CoreText",
                "ApplicationServices",
                "HIServices",
                "PyObjCTools",
            ],
        }
    },
)
