"""Xclipy's settings window, for the desktops without Cinnamon's System Settings."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from xapp.GSettingsWidgets import SettingsStack

from xclipy import shortcut
from xclipy.i18n import _
from xclipy.ui import settings_page


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title=_("Clipboard"), icon_name="xclipy")
        self.set_default_size(720, 640)
        stack = SettingsStack()
        # The tabs at the top, as System Settings has them in its header bar.
        switcher = Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.CENTER, margin=8)
        settings_page.fill(stack, shortcut.backend_for_desktop(), switcher.set_visible)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.add(stack)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(switcher, False, False, 0)
        box.pack_start(scrolled, True, True, 0)
        self.add(box)
        self.show_all()
