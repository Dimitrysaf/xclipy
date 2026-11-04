#!/usr/bin/python3
"""Xclipy's page in Cinnamon's System Settings, "Clipboard".

System Settings loads every cs_*.py module in
/usr/share/cinnamon/cinnamon-settings/modules; this one is installed there.
Its tabs (General, Passwords, Emojis) are Xclipy's, the same as in its
settings window elsewhere; System Settings shows them in its header bar. While
the history is off, a page saying so takes their place, without tabs, as in
the Gestures settings.
"""

from gi.repository import Gio, GLib

from bin.SettingsWidgets import SidePage
from xapp.GSettingsWidgets import SettingsStack

from xclipy import shortcut
from xclipy.i18n import _
from xclipy.ui import settings_page


class Module:
    name = "xclipy"
    comment = _("Clipboard history and emoji")
    category = "prefs"

    def __init__(self, content_box):
        keywords = _("clipboard, history, copy, paste, emoji")
        self.sidePage = SidePage(_("Clipboard"), "xclipy", keywords, content_box, module=self)

    def on_module_selected(self):
        if self.loaded:
            # System Settings shows its tabs again when coming back here.
            GLib.idle_add(self._show_page)
            return
        self.sidePage.stack = SettingsStack()
        self.sidePage.add_widget(self.sidePage.stack)
        self._show_page = settings_page.fill(self.sidePage.stack, shortcut.backend_for_desktop("X-Cinnamon"),
                                             self._show_tabs)

    @staticmethod
    def _show_tabs(shown):
        Gio.Application.get_default().stack_switcher.set_opacity(1 if shown else 0)
