"""Which application has the keyboard focus, and whether it's a terminal.

Applications describe their windows to assistive technologies (screen readers)
over AT-SPI. Xclipy follows which of them has the keyboard focus, so it can paste
with Ctrl+Shift+V into terminals.
"""

import os

import gi

from gi.repository import Gio, GLib

TIMEOUT_MS = 250  # don't wait long for an application that's busy


def _accessibility_bus():
    """Whether the accessibility bus runs (without it, Atspi aborts the process)."""
    if os.environ.get("AT_SPI_BUS_ADDRESS"):
        return True
    try:
        session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        session.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress",
                          None, GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 1000, None)
    except GLib.Error:
        return False
    return True


def _atspi():
    if not _accessibility_bus():
        return None
    try:
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError):
        return None
    return Atspi


class FocusTracker:
    def __init__(self):
        self._atspi = _atspi()
        self._focused = None
        if self._atspi is None:
            return
        self._atspi.init()
        self._atspi.set_timeout(TIMEOUT_MS, -1)
        self._listener = self._atspi.EventListener.new(self._on_focus)
        self._listener.register("object:state-changed:focused")

    def _on_focus(self, event):
        if not event.detail1 or event.source is None:
            return  # focus lost
        try:
            if event.source.get_process_id() == os.getpid():
                return  # the overlay itself
        except GLib.Error:
            return
        self._focused = event.source

    def _focused_accessible(self):
        accessible = self._focused
        if accessible is None:
            return None
        try:
            if accessible.get_state_set().contains(self._atspi.StateType.FOCUSED):
                return accessible
        except GLib.Error:
            pass
        return None

    def in_terminal(self):
        accessible = self._focused_accessible()
        try:
            return accessible is not None and accessible.get_role() == self._atspi.Role.TERMINAL
        except GLib.Error:
            return False
