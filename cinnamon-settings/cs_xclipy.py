#!/usr/bin/python3
"""Xclipy's page in Cinnamon's System Settings, "Clipboard".

System Settings loads every cs_*.py module in
/usr/share/cinnamon/cinnamon-settings/modules; this one is installed there.
The page itself is Xclipy's, the same as in its settings window elsewhere.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from bin.SettingsWidgets import SidePage
from xapp.GSettingsWidgets import SettingsPage

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
            return
        page = SettingsPage()
        settings_page.fill(page, shortcut.backend_for_desktop("X-Cinnamon"))
        # System Settings grows its window to the page's height; scrolling here keeps the window as it is.
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.add(page)
        scrolled.expand = True  # SidePage packs widgets with this attribute to fill the window
        self.sidePage.add_widget(scrolled)
