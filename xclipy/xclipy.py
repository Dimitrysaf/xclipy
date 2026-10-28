#!/usr/bin/python3
"""Xclipy: the clipboard history of the Cinnamon desktop.

It runs from login without a window or a tray icon, keeps what is copied, and
opens its overlay when its keyboard shortcuts run ``xclipy --show`` or, on
the Emojis tab, ``xclipy --emoji``.
"""

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from xclipy import APP_ID, SCHEMA_ID, shortcut
from xclipy.caret import CaretTracker
from xclipy.history import ClipboardHistory
from xclipy.i18n import _
from xclipy.passwords import Keyring
from xclipy.paste import paste
from xclipy.ui.overlay import Overlay, is_wayland
from xclipy.watcher import ClipboardWatcher

PASTE_DELAY_MS = 150  # lets the focus go back to the application first
PASTED_MS = 1000  # by then the application has taken what was pasted
TIDY_SECONDS = 10  # how often old items and passwords are looked for


class XclipyApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
                         register_session=True)
        self.settings = None
        self.history = None
        self.watcher = None
        self.caret = None
        self.overlay = None
        self._terminal = False
        self.add_main_option(
            "background", ord("b"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            _("Keep the clipboard history without opening it"), None)
        self.add_main_option(
            "show", ord("s"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            _("Open the clipboard history, or close it when it is open"), None)
        self.add_main_option(
            "emoji", ord("e"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            _("Open the emojis, or close them when they are open"), None)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()  # keeps watching the clipboard without a window
        self.settings = Gio.Settings.new(SCHEMA_ID)
        path = os.path.join(GLib.get_user_data_dir(), "xclipy", "history.json")
        session = os.environ.get("XDG_SESSION_ID")
        keyring = Keyring() if self.settings.get_boolean("save-pinned-passwords") else None
        self.history = ClipboardHistory(path, self.settings.get_int("history-size"), session, keyring)
        if keyring is None and self.history.saved_passwords:
            Keyring().delete_all()  # turned off while Xclipy wasn't running
        # A new login: the last session's recent items go, even if it ended
        # without logging out (a crash, a power cut).
        if self.settings.get_boolean("clear-on-logout") and self.history.previous_session not in (None, session):
            self.history.clear()
        self.history.save()
        self.connect("query-end", self._on_logout)
        self.settings.connect("changed::history-size",
                              lambda s, key: self.history.set_size(s.get_int(key)))
        self.settings.connect("changed::enabled", self._on_enabled_changed)
        self.settings.connect("changed::save-pinned-passwords", lambda s, key: self.history.keep_pinned_passwords(
            Keyring() if s.get_boolean(key) else None))
        self.watcher = ClipboardWatcher(self.history, self.settings)
        self.caret = CaretTracker()
        if shortcut.available():
            for kind in (shortcut.CLIPBOARD, shortcut.EMOJI):
                shortcut.Shortcut(kind).add_default(self.settings)
        for name, callback in (
            ("show", lambda *_args: self.toggle_overlay()),
            ("clear-history", lambda *_args: self.history.clear_all()),
            ("quit", lambda *_args: self.quit()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        self._tidy()
        GLib.timeout_add_seconds(TIDY_SECONDS, self._tidy)

    def do_command_line(self, command_line):
        # Also runs in the first instance when xclipy is started again.
        options = command_line.get_options_dict()
        if options.contains("emoji"):
            self.toggle_overlay("emoji")
        elif not options.contains("background"):
            self.toggle_overlay()
        return 0

    def do_activate(self):
        self.toggle_overlay()

    def toggle_overlay(self, tab="clipboard"):
        """Open the overlay on a tab, switch to it, or close the overlay when it's on it."""
        if not self.settings.get_boolean("enabled"):
            return  # the shortcuts do nothing while the history is off
        if self.overlay is None:
            self.overlay = Overlay(self, self.history, self.settings, self.choose,
                                   lambda item: self.choose(item, then_paste=True),
                                   self.choose_emoji)
            self.history.on_changed = self.overlay.clipboard_page.refresh
        if not self.overlay.get_visible():
            # Asked now, while the application still has the keyboard focus.
            self._terminal = self.caret.in_terminal()
            self.overlay.popup(self.caret.caret(), tab)
        elif self.overlay.tab != tab:
            self.overlay.switch_to(tab)
        else:
            self.overlay.hide()

    def choose(self, item, then_paste=None):
        """Copy a history item, and paste it if asked to (by default, as set)."""
        self.history.use(item)
        self.watcher.copy(item)
        pasted = self._paste_after(then_paste)
        if pasted and item.secret and self.settings.get_boolean("clear-pasted-passwords") \
                and not self.history.is_pinned(item):
            GLib.timeout_add(PASTE_DELAY_MS + PASTED_MS, self._forget_password, item)

    def choose_emoji(self, text):
        self.watcher.copy(text)
        self._paste_after(None)

    def _paste_after(self, then_paste):
        self.overlay.hide()
        if then_paste is None:
            then_paste = self.settings.get_boolean("paste-on-select")
        # xdotool can't press keys in other applications on Wayland.
        if not then_paste or is_wayland(self.overlay.get_display()):
            return False
        GLib.timeout_add(PASTE_DELAY_MS, self._paste)
        return True

    def _paste(self):
        paste(self._terminal)
        return GLib.SOURCE_REMOVE

    def _forget_password(self, item):
        self.history.remove(item)
        self.watcher.forget(item)
        return GLib.SOURCE_REMOVE

    def _tidy(self):
        """Delete old items and passwords, as set."""
        gone = []
        if self.settings.get_boolean("forget-passwords"):
            gone += self.history.remove_older(self.settings.get_int("forget-passwords-minutes") * 60,
                                              secret_only=True)
        if self.settings.get_boolean("delete-old-items"):
            gone += self.history.remove_older(self.settings.get_int("delete-old-days") * 86400)
        for item in gone:
            if item.secret:
                self.watcher.forget(item)  # a forgotten password leaves the clipboard too
        return GLib.SOURCE_CONTINUE

    def _on_enabled_changed(self, settings, key):
        if not settings.get_boolean(key) and self.overlay is not None:
            self.overlay.hide()

    def _on_logout(self, _application):
        if self.settings.get_boolean("clear-on-logout"):
            self.history.clear()


def main():
    return XclipyApplication().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
