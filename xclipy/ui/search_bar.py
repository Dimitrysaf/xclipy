"""The search bar at the bottom of both tabs: a search field, maybe a button."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from xclipy.i18n import _


class SearchBar(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=6, margin_start=8, margin_end=8, margin_top=6)
        self.entry = Gtk.SearchEntry(placeholder_text=_("Search"), hexpand=True)
        self.pack_start(self.entry, True, True, 0)
        # As high as a button, whether one is beside it or not.
        self.entry.connect("style-updated", lambda _e: self._fit_height())
        self._fit_height()

    def _fit_height(self):
        button = Gtk.Button()
        button.add(Gtk.Image.new_from_icon_name("edit-find-symbolic", Gtk.IconSize.BUTTON))
        button.show_all()
        _minimum, natural = button.get_preferred_height()
        self.entry.set_size_request(-1, natural)
