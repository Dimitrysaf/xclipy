"""The Emojis tab: emoji by group, the recently used ones, and a search."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from xclipy import emoji
from xclipy.emoji_data import GROUPS
from xclipy.i18n import _
from xclipy.ui.search_bar import SearchBar

RECENT = "recent"


class EmojiPage(Gtk.Box):
    def __init__(self, settings, on_choose):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._settings = settings
        self._on_choose = on_choose
        self._shown = None  # the group (or RECENT) in the grid, None while searching

        self._grid = Gtk.FlowBox(homogeneous=True, valign=Gtk.Align.START,
                                 min_children_per_line=8, max_children_per_line=8,
                                 selection_mode=Gtk.SelectionMode.NONE, margin_start=4, margin_end=4)
        self._grid.connect("child-activated", lambda _g, child: self._choose(child.emoji))
        self._scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._scrolled.add(self._grid)
        self._empty = Gtk.Label(label="", valign=Gtk.Align.CENTER)
        self._empty.get_style_context().add_class("dim-label")
        self._stack = Gtk.Stack()
        self._stack.add_named(self._scrolled, "grid")
        self._stack.add_named(self._empty, "empty")
        self.pack_start(self._stack, True, True, 0)

        groups = Gtk.Box(homogeneous=True, margin_start=4, margin_end=4)
        self._group_buttons = {}
        first = None
        for group, symbol, name in self._groups():
            button = Gtk.RadioButton.new_from_widget(first)
            button.set_mode(False)  # a toggle button, not a radio circle
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_tooltip_text(name)
            if group == RECENT:
                button.add(Gtk.Image.new_from_icon_name("document-open-recent-symbolic", Gtk.IconSize.BUTTON))
            else:
                button.add(Gtk.Label(label=symbol))
            button.connect("toggled", self._on_group_toggled, group)
            groups.pack_start(button, True, True, 0)
            self._group_buttons[group] = button
            first = first or button
        self.pack_start(groups, False, False, 0)

        # At the bottom, the same as the Clipboard tab's.
        bar = SearchBar()
        bar.set_margin_top(0)  # this page spaces its parts already
        self._search = bar.entry
        self._search.connect("search-changed", lambda _e: self._show_search())
        self._search.connect("activate", lambda _e: self.choose_first())
        self._search.connect("key-press-event", self._on_search_key_press)
        self.pack_start(bar, False, False, 0)

    @staticmethod
    def _groups():
        yield RECENT, None, _("Recently used")
        for index in range(len(GROUPS)):
            yield index, emoji.group_symbol(index), emoji.group_name(index)

    def prepare(self):
        """Called when the tab is shown: start from the recently used ones, if any."""
        self._search.set_text("")
        group = RECENT if self._settings.get_strv("recent-emoji") else 0
        if self._group_buttons[group].get_active():
            self._show_group(group)
        else:
            self._group_buttons[group].set_active(True)
        self._search.grab_focus()

    def _on_group_toggled(self, button, group):
        if button.get_active():
            self._search.set_text("")
            self._show_group(group)

    def _show_group(self, group):
        self._shown = group
        if group == RECENT:
            entries = [(text, emoji.name_of(text)) for text in self._settings.get_strv("recent-emoji")]
            self._fill(entries, _("Emoji you use show up here."))
        else:
            self._fill(self._toned(emoji.in_group(group)), "")

    def _show_search(self):
        query = self._search.get_text().strip()
        if not query:
            if self._shown is None:
                self._show_group(next(g for g, b in self._group_buttons.items() if b.get_active()))
            return
        self._shown = None
        self._fill(self._toned(emoji.search(query)), _("No emoji found"))

    def _toned(self, entries):
        tone = self._settings.get_string("emoji-skin-tone")
        return [(emoji.with_tone(text, tone), name) for text, name in entries]

    def _fill(self, entries, empty_text):
        for child in self._grid.get_children():
            self._grid.remove(child)
        for text, name in entries:
            child = Gtk.FlowBoxChild()
            child.emoji = text
            label = Gtk.Label(label=text)
            label.get_style_context().add_class("xclipy-emoji")
            child.add(label)
            child.set_tooltip_text(name)
            self._grid.add(child)
        self._grid.show_all()
        self._scrolled.get_vadjustment().set_value(0)
        self._empty.set_label(empty_text)
        self._stack.set_visible_child_name("grid" if entries else "empty")

    def _on_search_key_press(self, _entry, event):
        # Up goes to the emoji above.
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            child = self._grid.get_child_at_index(0)
            if child is not None:
                child.grab_focus()
            return True
        return False

    def choose_first(self):
        """Enter in the search: the first emoji found."""
        child = self._grid.get_child_at_index(0)
        if child is not None:
            self._choose(child.emoji)

    def _choose(self, text):
        self._settings.set_strv("recent-emoji", emoji.remember(self._settings.get_strv("recent-emoji"), text))
        self._on_choose(text)
