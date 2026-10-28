"""Paste into the application that had the keyboard focus before the overlay."""

import shutil
import subprocess


def paste_keys(terminal):
    # Terminals keep Ctrl+V for themselves.
    return "ctrl+shift+v" if terminal else "ctrl+v"


def paste(terminal=False):
    """Press the paste keys with xdotool (X11). False when that isn't possible."""
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        return False
    try:
        subprocess.Popen([xdotool, "key", "--clearmodifiers", paste_keys(terminal)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
