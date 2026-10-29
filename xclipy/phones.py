"""Phones connected with Satellite: what was copied on them, and sending to them.

Satellite (org.x.Satellite) puts what is copied on a phone on this
computer's clipboard, and says so on its org.x.Satellite.Phone interface,
/org/x/Satellite/Phone:

    signal ClipboardReceived(s device, s name, s sha256)
        A phone's copy was put on the clipboard: the phone, and the SHA-256
        of the text to recognise it (never the text: any application on the
        bus sees signals).
    method GetDevices() -> (s json)
        The devices: id, name, connected, clipboard (whether they share it)...
    method SendClipboard(s device, s text) -> (b sent)
    signal DevicesChanged()

Xclipy never starts Satellite: without it, there are no phones.
"""

import hashlib
import json
import time

from gi.repository import Gio, GLib

NAME = "org.x.Satellite"
PATH = "/org/x/Satellite/Phone"
INTERFACE = "org.x.Satellite.Phone"
TIMEOUT_MS = 2000
# Satellite puts the copy on the clipboard and says so at the same time: Xclipy
# may see either first.
MATCH_SECONDS = 5


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class PhoneCopies:
    """The copies Satellite said came from a phone, just now: by their SHA-256."""

    def __init__(self):
        self._received = {}  # sha256: (name, when)

    def add(self, name, sha256, now=None):
        now = time.monotonic() if now is None else now
        self._received = {key: value for key, value in self._received.items()
                          if now - value[1] < MATCH_SECONDS}
        self._received[sha256] = (name, now)

    def claim(self, sha256, now=None):
        """The phone a copy came from, if Satellite said so just now; once."""
        now = time.monotonic() if now is None else now
        name, when = self._received.pop(sha256, (None, 0))
        return name if name is not None and now - when < MATCH_SECONDS else None


class Phones:
    def __init__(self):
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._devices = []
        self.copies = PhoneCopies()
        self.on_received = None  # (sha256) when a phone's copy was put on the clipboard
        self.on_devices_changed = None
        Gio.bus_watch_name_on_connection(self._bus, NAME, Gio.BusNameWatcherFlags.NONE,
                                         self._appeared, self._vanished)
        for signal, callback in (("ClipboardReceived", self._on_clipboard_received),
                                 ("DevicesChanged", lambda *_args: self._load_devices())):
            self._bus.signal_subscribe(NAME, INTERFACE, signal, PATH, None, Gio.DBusSignalFlags.NONE, callback)

    def _appeared(self, *_args):
        self._load_devices()

    def _vanished(self, *_args):
        self._set_devices([])

    def _load_devices(self):
        def done(bus, task):
            try:
                devices = json.loads(bus.call_finish(task).unpack()[0])
            except (GLib.Error, ValueError):
                devices = []
            self._set_devices([(d["id"], d["name"]) for d in devices if isinstance(d, dict)
                               and d.get("connected") and d.get("clipboard")])
        self._bus.call(NAME, PATH, INTERFACE, "GetDevices", None, GLib.VariantType("(s)"),
                       Gio.DBusCallFlags.NO_AUTO_START, TIMEOUT_MS, None, done)

    def _set_devices(self, devices):
        if devices != self._devices:
            self._devices = devices
            if self.on_devices_changed is not None:
                self.on_devices_changed()

    def devices(self):
        """The connected phones sharing their clipboard: [(id, name)]."""
        return list(self._devices)

    def send(self, device_id, text):
        self._bus.call(NAME, PATH, INTERFACE, "SendClipboard", GLib.Variant("(ss)", (device_id, text)),
                       GLib.VariantType("(b)"), Gio.DBusCallFlags.NO_AUTO_START, TIMEOUT_MS, None,
                       lambda bus, task: _finish(bus, task))

    def _on_clipboard_received(self, _bus, _sender, _path, _interface, _signal, parameters):
        _device, name, sha256 = parameters.unpack()
        self.copies.add(name, sha256)
        if self.on_received is not None:
            self.on_received(sha256)


def _finish(bus, task):
    try:
        bus.call_finish(task)
    except GLib.Error:
        pass  # Satellite went away meanwhile
