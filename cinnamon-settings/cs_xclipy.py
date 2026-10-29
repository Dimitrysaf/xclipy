#!/usr/bin/python3
"""Xclipy's page in Cinnamon's System Settings, "Clipboard".

System Settings loads every cs_*.py module in
/usr/share/cinnamon/cinnamon-settings/modules; this one is installed there.
The page itself is Xclipy's, the same as in its settings window elsewhere.
"""

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
        self.sidePage.add_widget(page)
        settings_page.fill(page, shortcut.backend_for_desktop("X-Cinnamon"))
