"""Path resolution for both development and a PyInstaller-frozen .exe.

Two distinct roots:

  resource_dir()  - bundled, read-only assets (templates, static, default config).
                    Frozen: PyInstaller's temp extraction (sys._MEIPASS).
                    Dev:    the project root.

  external_dir()  - writable, user-editable data (config/, results/) that must live
                    NEXT TO the executable so edits persist across restarts.
                    Frozen: the folder containing the .exe.
                    Dev:    the project root.

In development both point at the project root, so nothing changes when running from source.
"""

import os
import sys


def is_frozen():
    """True when running inside a PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def resource_dir():
    """Directory of bundled read-only assets (templates/static/default config)."""
    if is_frozen():
        # PyInstaller extracts --add-data payloads here at runtime.
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def external_dir():
    """Directory for writable data (config/, results/) beside the executable."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
