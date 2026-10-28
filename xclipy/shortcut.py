"""The keyboard shortcuts that open the overlay: Cinnamon custom shortcuts.

Cinnamon runs the command of a custom shortcut itself, so the shortcuts work
whatever has the keyboard focus. They are also listed in System Settings →
Keyboard → Shortcuts → Custom Shortcuts, where they can be changed too.
"""

from gi.repository import Gio

from xclipy.i18n import N_, _

PARENT_SCHEMA = "org.cinnamon.desktop.keybindings"
CUSTOM_SCHEMA = "org.cinnamon.desktop.keybindings.custom-keybinding"
CUSTOM_PATH = "/org/cinnamon/desktop/keybindings/custom-keybindings/{}/"
# Cinnamon reloads its custom shortcuts when this list changes; like Cinnamon's
# own settings, add or remove this entry to make sure it does.
DUMMY = "__dummy__"


class Kind:
    def __init__(self, command, name, default, added_key):
        self.command = command
        self.name = name  # as listed in Cinnamon's Keyboard settings
        self.default = default
        self.added_key = added_key  # the setting telling it was added once


CLIPBOARD = Kind("xclipy --show", N_("Clipboard history"), ["<Super>v"], "shortcut-added")
EMOJI = Kind("xclipy --emoji", N_("Emojis"), ["<Super>period"], "emoji-shortcut-added")


def available():
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(CUSTOM_SCHEMA, True) is not None


class Shortcut:
    def __init__(self, kind, parent=None, custom=None):
        self._kind = kind
        self._parent = parent or Gio.Settings.new(PARENT_SCHEMA)
        self._custom = custom or (lambda name: Gio.Settings.new_with_path(
            CUSTOM_SCHEMA, CUSTOM_PATH.format(name)))

    def find(self):
        """The name ("customN") of this custom shortcut, or None."""
        for name in self._parent.get_strv("custom-list"):
            if name != DUMMY and self._custom(name).get_string("command") == self._kind.command:
                return name
        return None

    def binding(self):
        name = self.find()
        return list(self._custom(name).get_strv("binding")) if name else []

    def set_binding(self, binding):
        names = self._parent.get_strv("custom-list")
        name = self.find()
        if name is None:
            # Cinnamon's Keyboard settings expect "custom" and a number.
            taken = {n for n in names if n != DUMMY}
            number = 0
            while "custom{}".format(number) in taken:
                number += 1
            name = "custom{}".format(number)
            names.append(name)
            custom = self._custom(name)
            custom.set_string("name", _(self._kind.name))
            custom.set_string("command", self._kind.command)
        self._custom(name).set_strv("binding", list(binding))
        if DUMMY in names:
            names.remove(DUMMY)
        else:
            names.append(DUMMY)
        self._parent.set_strv("custom-list", names)

    def add_default(self, settings):
        """Add the shortcut the first time Xclipy runs, but never again.

        If it is removed in the Keyboard settings later, it stays removed.
        """
        if settings.get_boolean(self._kind.added_key):
            return
        if self.find() is None:
            self.set_binding(self._kind.default)
        settings.set_boolean(self._kind.added_key, True)
