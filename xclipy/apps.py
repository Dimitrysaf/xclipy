"""Which application copied something, for the excluded applications.

An application is excluded by its desktop file (e.g. "org.keepassxc.KeePassXC.desktop").
What is copied comes from the window that has the keyboard focus: its class
and its program are compared with the names its desktop file gives (its id,
its StartupWMClass and its program).

On X11 the focused window comes from libwnck; on Wayland from Xclipy's helper in
Cinnamon, and without it no application is recognised.
"""

import os

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio

# Programs that start other programs: they say nothing about the application.
LAUNCHERS = {"env", "sh", "bash", "python", "python3", "perl", "java", "gjs", "flatpak", "snap", "electron"}


def _wnck():
    # libwnck only knows X11, and crashes without it.
    display = Gdk.Display.get_default()
    if display is None or display.__gtype__.name != "GdkX11Display":
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
    def __init__(self, helper=None):
        """helper: Xclipy's helper in Cinnamon, which knows the focused window on Wayland."""
        wnck = _wnck()
        self._helper = helper
        self._screen = None
        if wnck is not None:
            screen = wnck.Screen.get_default()
            if screen is not None:
                screen.force_update()
                self._screen = screen

    def names(self):
        """The lowercase names of the focused window's application: class and program."""
        if self._screen is None:
            return self._names_from_helper()
        window = self._screen.get_active_window()
        if window is None:
            return set()
        return _names(window.get_class_group_name(), window.get_class_instance_name(), window.get_pid())

    def _names_from_helper(self):
        focused = self._helper.focused_window() if self._helper is not None and self._helper.available else None
        if not focused:
            return set()
        wm_class, app_id, pid, _origin = focused
        return _names(wm_class, app_id, pid)


def _names(wm_class, wm_instance_or_app_id, pid):
    """The lowercase names of a window's application: its class or id, and its program."""
    names = {wm_class or "", wm_instance_or_app_id or ""}
    if pid > 0:
        try:
            with open("/proc/{}/comm".format(pid), encoding="utf-8") as stream:
                names.add(stream.read().strip())
            names.add(os.path.basename(os.readlink("/proc/{}/exe".format(pid))))
        except OSError:
            pass
    return {name.lower() for name in names if name} - LAUNCHERS
