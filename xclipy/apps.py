"""Which application copied something, for the excluded applications.

An application is excluded by its desktop file (e.g. "org.keepassxc.KeePassXC.desktop").
What is copied comes from the window that has the keyboard focus: its class
and its program are compared with the names its desktop file gives (its id,
its StartupWMClass and its program).

This needs X11: on Wayland, no application is recognised.
"""

import os

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio

# Programs that start other programs: they say nothing about the application.
LAUNCHERS = {"env", "sh", "bash", "python", "python3", "perl", "java", "gjs", "flatpak", "snap", "electron"}


def _wnck():
    # libwnck only knows X11, and crashes without it.
    if not type(Gdk.Display.get_default()).__name__.startswith("X11"):
        return None
    try:
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck
    except (ImportError, ValueError):
        return None
    return Wnck


def desktop_names(desktop_id, wm_class=None, executable=None):
    """The lowercase names an application's windows and programs can have."""
    stem = desktop_id[:-len(".desktop")] if desktop_id.endswith(".desktop") else desktop_id
    names = {stem.lower(), stem.split(".")[-1].lower()}
    if wm_class:
        names.add(wm_class.lower())
    if executable:
        program = os.path.basename(executable).lower()
        if program not in LAUNCHERS:
            names.add(program)
    return names - {""}


def is_excluded(window_names, excluded, names_of=None):
    """Whether a window with these (lowercase) names belongs to an excluded application."""
    names_of = names_of or _names_of_desktop_file
    return any(names_of(desktop_id) & window_names for desktop_id in excluded)


def _names_of_desktop_file(desktop_id):
    try:
        info = Gio.DesktopAppInfo.new(desktop_id)
    except TypeError:
        info = None
    if info is None:
        return desktop_names(desktop_id)
    return desktop_names(desktop_id, info.get_startup_wm_class(), info.get_executable())


class FocusedApplication:
    def __init__(self):
        wnck = _wnck()
        self._screen = None
        if wnck is not None:
            screen = wnck.Screen.get_default()
            if screen is not None:
                screen.force_update()
                self._screen = screen

    def names(self):
        """The lowercase names of the focused window's application: class and program."""
        window = self._screen.get_active_window() if self._screen is not None else None
        if window is None:
            return set()
        names = {window.get_class_group_name() or "", window.get_class_instance_name() or ""}
        pid = window.get_pid()
        if pid > 0:
            for path in ("/proc/{}/comm".format(pid), "/proc/{}/exe".format(pid)):
                try:
                    if path.endswith("comm"):
                        with open(path, encoding="utf-8") as stream:
                            names.add(stream.read().strip())
                    else:
                        names.add(os.path.basename(os.readlink(path)))
                except OSError:
                    pass
        return {name.lower() for name in names if name} - LAUNCHERS
