"""Xclipy's settings window, for the desktops without Cinnamon's System Settings."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from xapp.GSettingsWidgets import SettingsPage

from xclipy import shortcut
from xclipy.i18n import _
from xclipy.ui import settings_page


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title=_("Clipboard"), icon_name="xclipy")
        self.set_default_size(720, 640)
        page = SettingsPage()
        settings_page.fill(page, shortcut.backend_for_desktop())
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.add(page)
        self.add(scrolled)
        self.show_all()
