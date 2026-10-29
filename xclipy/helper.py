"""Xclipy's helper in Cinnamon: what only the desktop can do, on Wayland.

On Wayland an application only sees the clipboard while it has the keyboard
focus, can't place its windows or press keys in other applications. The
helper is a Cinnamon extension (installed with Xclipy, uuid HELPER_UUID) that
does it for Xclipy, on the session bus:

    org.x.Xclipy.Cinnamon, /org/x/Xclipy/Cinnamon, interface org.x.Xclipy.Cinnamon

    signal ClipboardChanged(as mimetypes)
        Something was copied. Only the kinds of content, never the content:
        any application on the bus can see signals.
    method ReadClipboard(s mimetype) -> (ay data)
        The clipboard's content. Only for the owner of org.x.Xclipy.
    method FocusedWindow() -> (s wm_class, s app_id, u pid, (iiii) origin)
        The window with the keyboard focus, for the excluded applications
        and where its text cursor is: origin is where the window's own
        coordinates start on the screen (empty for no window; pid 0 if
        unknown). Only for the owner of org.x.Xclipy.
    method PlaceOverlay((iiii) caret)
        Place Xclipy's overlay under the text cursor (x, y, width, height on
        the screen; width -1 for none: the bottom right corner), keep it above
        the other windows and out of the window list.
    method Paste(b terminal)
        Press Ctrl+V (Ctrl+Shift+V in terminals). Only for the owner of org.x.Xclipy.
    property u Version

On X11 Xclipy needs none of it.
"""

from gi.repository import Gio, GLib

HELPER_UUID = "xclipy@dimitrysaf"
NAME = "org.x.Xclipy.Cinnamon"
PATH = "/org/x/Xclipy/Cinnamon"
INTERFACE = "org.x.Xclipy.Cinnamon"
TIMEOUT_MS = 500


class CinnamonHelper:
    def __init__(self):
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.available = False
        self.on_clipboard_changed = None  # (mimetypes) when something is copied
        Gio.bus_watch_name_on_connection(self._bus, NAME, Gio.BusNameWatcherFlags.NONE,
                                         self._appeared, self._vanished)
        self._bus.signal_subscribe(NAME, INTERFACE, "ClipboardChanged", PATH, None,
                                   Gio.DBusSignalFlags.NONE, self._on_signal)

    def _appeared(self, *_args):
        self.available = True

    def _vanished(self, *_args):
        self.available = False

    def _on_signal(self, _bus, _sender, _path, _interface, _signal, parameters):
        if self.on_clipboard_changed is not None:
            self.on_clipboard_changed(parameters.unpack()[0])

    def _call(self, method, parameters, reply_type, callback=None):
        """A call to the helper: with a callback(result or None), or waiting for it."""
        reply = GLib.VariantType(reply_type) if reply_type else None
        if callback is None:
            try:
                result = self._bus.call_sync(NAME, PATH, INTERFACE, method, parameters, reply,
                                             Gio.DBusCallFlags.NO_AUTO_START, TIMEOUT_MS, None)
            except GLib.Error:
                return None
            return result.unpack() if result is not None else None

        def done(bus, task):
            try:
                result = bus.call_finish(task)
            except GLib.Error:
                result = None
            callback(result.unpack() if result is not None else None)
        self._bus.call(NAME, PATH, INTERFACE, method, parameters, reply,
                       Gio.DBusCallFlags.NO_AUTO_START, TIMEOUT_MS, None, done)
        return None

    def read_clipboard(self, mimetype, callback):
        """callback(bytes or None)."""
        self._call("ReadClipboard", GLib.Variant("(s)", (mimetype,)), "(ay)",
                   lambda result: callback(bytes(result[0]) if result else None))

    def focused_window(self):
        """(wm_class, app_id, pid, (x, y, width, height)), or None."""
        return self._call("FocusedWindow", None, "(ssu(iiii))")

    def place_overlay(self, caret):
        rect = tuple(int(v) for v in caret) if caret else (-1, -1, -1, -1)
        self._call("PlaceOverlay", GLib.Variant("((iiii))", (rect,)), None, lambda _result: None)

    def paste(self, terminal):
        self._call("Paste", GLib.Variant("(b)", (terminal,)), None, lambda _result: None)


def running():
    """Whether the helper runs (e.g. for the settings, outside Xclipy)."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                               "NameHasOwner", GLib.Variant("(s)", (NAME,)), GLib.VariantType("(b)"),
                               Gio.DBusCallFlags.NONE, TIMEOUT_MS, None)
    except GLib.Error:
        return False
    return result.unpack()[0]


def enable_once(settings):
    """Turn the helper on in Cinnamon the first time Xclipy runs there; never again.

    If it is turned off later (System Settings → Extensions), it stays off.
    """
    if settings.get_boolean("cinnamon-helper-added"):
        return
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup("org.cinnamon", True) is None:
        return
    cinnamon = Gio.Settings.new("org.cinnamon")
    enabled = cinnamon.get_strv("enabled-extensions")
    if HELPER_UUID not in enabled:
        cinnamon.set_strv("enabled-extensions", enabled + [HELPER_UUID])
    settings.set_boolean("cinnamon-helper-added", True)
