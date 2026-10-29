"""The keyboard shortcuts that open the overlay, as the desktop's own custom shortcuts.

The desktop runs the command of a custom shortcut itself, so the shortcuts
work whatever has the keyboard focus, and they are listed (and can be changed)
in the desktop's keyboard settings too:

* Cinnamon: Keyboard → Shortcuts → Custom Shortcuts (org.cinnamon.desktop.keybindings).
* MATE: Keyboard Shortcuts → Custom Shortcuts (/org/mate/desktop/keybindings/customN/).
* Xfce: Keyboard → Application Shortcuts (xfconf, xfce4-keyboard-shortcuts).

On other desktops there are none: bind ``xclipy --show`` yourself.
"""

import os
import shutil
import subprocess

from gi.repository import Gio

from xclipy.i18n import N_, _


class Kind:
    def __init__(self, key, command, name, default):
        self.key = key  # remembered in "shortcuts-added", once added
        self.command = command
        self.name = name  # as the desktop's keyboard settings show it
        self.default = default


CLIPBOARD = Kind("clipboard", "xclipy --show", N_("Clipboard history"), "<Super>v")
EMOJI = Kind("emoji", "xclipy --emoji", N_("Emojis"), "<Super>period")
KINDS = (CLIPBOARD, EMOJI)


def _schema_installed(schema_id):
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(schema_id, True) is not None


class CinnamonShortcuts:
    """Cinnamon's custom shortcuts: a list of "customN" with a settings path each."""

    desktop = "cinnamon"
    PARENT_SCHEMA = "org.cinnamon.desktop.keybindings"
    CUSTOM_SCHEMA = "org.cinnamon.desktop.keybindings.custom-keybinding"
    CUSTOM_PATH = "/org/cinnamon/desktop/keybindings/custom-keybindings/{}/"
    # Cinnamon reloads its custom shortcuts when this list changes; like
    # Cinnamon's own settings, add or remove this entry to make sure it does.
    DUMMY = "__dummy__"

    @classmethod
    def available(cls):
        return _schema_installed(cls.CUSTOM_SCHEMA)

    def __init__(self, parent=None, custom=None):
        self._parent = parent or Gio.Settings.new(self.PARENT_SCHEMA)
        self._custom = custom or (lambda name: Gio.Settings.new_with_path(
            self.CUSTOM_SCHEMA, self.CUSTOM_PATH.format(name)))

    def find(self, command):
        for name in self._parent.get_strv("custom-list"):
            if name != self.DUMMY and self._custom(name).get_string("command") == command:
                return name
        return None

    def binding(self, command):
        name = self.find(command)
        return next(iter(self._custom(name).get_strv("binding")), "") if name else ""

    def set_binding(self, command, title, accelerator):
        names = self._parent.get_strv("custom-list")
        name = self.find(command)
        if name is None:
            # Cinnamon's Keyboard settings expect "custom" and a number.
            name = _free_name({n for n in names if n != self.DUMMY})
            names.append(name)
            custom = self._custom(name)
            custom.set_string("name", title)
            custom.set_string("command", command)
        self._custom(name).set_strv("binding", [accelerator] if accelerator else [])
        if self.DUMMY in names:
            names.remove(self.DUMMY)
        else:
            names.append(self.DUMMY)
        self._parent.set_strv("custom-list", names)


class MateShortcuts:
    """MATE's custom shortcuts: /org/mate/desktop/keybindings/customN/."""

    desktop = "mate"
    SCHEMA = "org.mate.control-center.keybinding"
    PATH = "/org/mate/desktop/keybindings/{}/"
    LIMIT = 100  # MATE numbers them; looking this far is plenty

    @classmethod
    def available(cls):
        return _schema_installed(cls.SCHEMA)

    def __init__(self, custom=None):
        self._custom = custom or (lambda name: Gio.Settings.new_with_path(self.SCHEMA, self.PATH.format(name)))

    def _names(self):
        return ["custom{}".format(number) for number in range(self.LIMIT)]

    def find(self, command):
        return next((n for n in self._names() if self._custom(n).get_string("action") == command), None)

    # MATE's shortcuts only know the Super key as <Mod4>.
    def binding(self, command):
        name = self.find(command)
        return self._custom(name).get_string("binding").replace("<Mod4>", "<Super>") if name else ""

    def set_binding(self, command, title, accelerator):
        name = self.find(command)
        if name is None:
            taken = {n for n in self._names() if self._custom(n).get_string("action")}
            name = _free_name(taken)
            custom = self._custom(name)
            custom.set_string("name", title)
            custom.set_string("action", command)
        self._custom(name).set_string("binding", (accelerator or "").replace("<Super>", "<Mod4>"))


class XfceShortcuts:
    """Xfce's application shortcuts: xfconf properties /commands/custom/<accelerator>."""

    desktop = "xfce"
    CHANNEL = "xfce4-keyboard-shortcuts"
    PREFIX = "/commands/custom/"

    @classmethod
    def available(cls):
        return shutil.which("xfconf-query") is not None

    def __init__(self, run=None):
        self._run = run or _xfconf_query

    def _properties(self):
        """{property: value} of the custom commands."""
        found = {}
        for line in self._run(["-c", self.CHANNEL, "-l", "-v"]).splitlines():
            prop, _space, value = line.partition(" ")
            if prop.startswith(self.PREFIX):
                found[prop] = value.strip()
        return found

    def find(self, command):
        return next((p for p, value in self._properties().items() if value == command), None)

    def binding(self, command):
        prop = self.find(command)
        accelerator = prop[len(self.PREFIX):] if prop else ""
        return "" if accelerator == "override" else accelerator

    def set_binding(self, command, title, accelerator):
        # The accelerator is the property's name: replace the property.
        prop = self.find(command)
        if prop is not None:
            self._run(["-c", self.CHANNEL, "-p", prop, "-r"])
        if accelerator:
            self._run(["-c", self.CHANNEL, "-p", self.PREFIX + accelerator, "-n", "-t", "string", "-s", command])


def _xfconf_query(arguments):
    try:
        return subprocess.run(["xfconf-query"] + arguments, capture_output=True, text=True,
                              timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _free_name(taken):
    number = 0
    while "custom{}".format(number) in taken:
        number += 1
    return "custom{}".format(number)


BACKENDS = {"X-Cinnamon": CinnamonShortcuts, "Cinnamon": CinnamonShortcuts,
            "MATE": MateShortcuts, "XFCE": XfceShortcuts}


def backend_for_desktop(current_desktop=None):
    """The shortcuts of this desktop (XDG_CURRENT_DESKTOP), or None."""
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "") if current_desktop is None else current_desktop
    for name in current_desktop.split(":"):
        backend = BACKENDS.get(name)
        if backend is not None and backend.available():
            return backend()
    return None


class Shortcut:
    """One of Xclipy's shortcuts on this desktop."""

    def __init__(self, kind, backend):
        self._kind = kind
        self._backend = backend

    def binding(self):
        """The accelerator ("<Super>v"), "" for none."""
        return self._backend.binding(self._kind.command)

    def set_binding(self, accelerator):
        self._backend.set_binding(self._kind.command, _(self._kind.name), accelerator)

    def add_default(self, settings):
        """Add the shortcut the first time Xclipy runs on this desktop, but never again.

        If it is removed in the keyboard settings later, it stays removed.
        """
        added = settings.get_strv("shortcuts-added")
        mark = "{}:{}".format(self._backend.desktop, self._kind.key)
        if mark in added:
            return
        if self._backend.find(self._kind.command) is None:
            self.set_binding(self._kind.default)
        settings.set_strv("shortcuts-added", added + [mark])
