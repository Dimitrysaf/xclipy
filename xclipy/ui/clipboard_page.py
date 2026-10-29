"""The Clipboard tab: the pinned items, then what was copied recently.

Each item has a menu to edit, delete, pin or paste it, or send it to a phone
(through Satellite). Editing happens on a page of its own, in the overlay. A
search bar at the bottom (when the settings say so) searches the items, and
its menu filters them by kind.
"""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from xclipy import kinds
from xclipy.i18n import N_, _
from xclipy.ui.search_bar import SearchBar

PREVIEW_LINES = 3
HIDDEN = "••••••••"  # a password, whatever its length
IMAGE_WIDTH = 320  # about the width of a row
IMAGE_HEIGHT = 120  # images show their top part, this high at most
PREVIEW_LENGTH = 400  # characters
LINE_SEPARATOR = " "  # a new line, but not a new paragraph
FROM_PHONE = "from-phone"  # a filter: what was copied on a phone
FILTER_NAMES = {
    kinds.TEXT: N_("Text"), kinds.LINK: N_("Links"), kinds.EMAIL: N_("Email addresses"),
    kinds.PHONE: N_("Phone numbers"), kinds.PATH: N_("Files and folders"), kinds.COLOR: N_("Colors"),
    kinds.PASSWORD: N_("Passwords"), kinds.IMAGE: N_("Images"), FROM_PHONE: N_("From phone"),
}


def preview(text):
    """The start of the text: the label wraps it and shows three lines at most.

    Pango counts lines per paragraph, so the lines are kept in one.
    """
    lines = text.strip().splitlines()
    shown = LINE_SEPARATOR.join(lines[:PREVIEW_LINES])
    if len(lines) > PREVIEW_LINES or len(shown) > PREVIEW_LENGTH:
        return shown[:PREVIEW_LENGTH] + "…"
    return shown


class ClipboardPage(Gtk.Box):
    def __init__(self, history, settings, on_choose, on_paste, phones=None):
        """on_choose(item) when an item is activated, on_paste(item) for its Paste.

        phones: the phones to send items to (xclipy.phones.Phones), if any.
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._history = history
        self._settings = settings
        self._phones = phones
        self._on_choose = on_choose
        self._on_paste = on_paste
        self._editing = None  # the item being edited
        self.on_editing_changed = lambda editing: None
        # Item menus fade out: destroying one meanwhile crashes GTK. So their
        # actions, and rebuilding the list, wait until the menu is gone.
        self._after_menu = []
        self._refresh_after_menu = False
        self._filter = None  # the kind shown, None for all

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        self._list.set_header_func(self._header)
        self._list.set_filter_func(self._is_shown)
        nothing = Gtk.Label(label=_("No items found"), margin=24)
        nothing.get_style_context().add_class("dim-label")
        nothing.show()
        self._list.set_placeholder(nothing)
        self._list.connect("row-activated", lambda _l, row: self._on_choose(row.item))
        self._list.connect("key-press-event", self._on_list_key_press)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.add(self._list)
        list_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_page.pack_start(scrolled, True, True, 0)
        list_page.pack_start(self._search_bar(), False, False, 0)

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("edit-paste-symbolic", Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class("dim-label")
        empty.pack_start(icon, False, False, 0)
        empty.pack_start(Gtk.Label(label=_("Nothing copied yet")), False, False, 0)
        hint = Gtk.Label(label=_("What you copy shows up here."), wrap=True, justify=Gtk.Justification.CENTER)
        hint.get_style_context().add_class("dim-label")
        empty.pack_start(hint, False, False, 0)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._stack.add_named(list_page, "list")
        self._stack.add_named(empty, "empty")
        self._stack.add_named(self._edit_page(), "edit")
        self.pack_start(self._stack, True, True, 0)
        for key in ("hide-passwords", "show-item-types", "show-search"):
            settings.connect("changed::" + key, lambda *_args: self.refresh())
        self.refresh()

    # The search bar

    def _search_bar(self):
        self._bar = SearchBar()
        self._bar.set_no_show_all(True)
        self._search = self._bar.entry
        self._search.connect("search-changed", lambda _e: self._apply_filter())
        self._search.connect("activate", lambda _e: self._choose_first_shown())
        self._search.connect("key-press-event", self._on_search_key_press)
        self._search.show()
        self._filters = Gtk.Popover(position=Gtk.PositionType.TOP)
        self._filter_button = Gtk.MenuButton(popover=self._filters, tooltip_text=_("Filter"))
        self._filter_button.add(Gtk.Image.new_from_icon_name("xclipy-filter-symbolic", Gtk.IconSize.BUTTON))
        self._filter_button.get_child().show()
        self._bar.pack_start(self._filter_button, False, False, 0)
        return self._bar

    def _update_search_bar(self, items):
        """Show the bar as set, with the filters for the kinds of items there are."""
        shown = self._settings.get_boolean("show-search")
        self._bar.set_visible(shown)
        present = {kinds.item_kind(item) for item in items}
        show_types = self._settings.get_boolean("show-item-types")
        options = kinds.filter_options(present, show_types) if shown else []
        # Copies from phones too, when some items are and some aren't.
        if shown and show_types and len({bool(item.device) for item in items}) == 2:
            options.append(FROM_PHONE)
        if self._filter not in options:
            self._filter = None
        if not shown:
            self._search.set_text("")
        self._filter_button.set_visible(bool(options))
        child = self._filters.get_child()
        if child is not None:
            self._filters.remove(child)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=6)
        for kind in [None] + options:
            button = Gtk.ModelButton(text=self._filter_name(kind), role=Gtk.ButtonRole.RADIO,
                                     active=kind == self._filter)
            button.kind = kind
            button.connect("clicked", lambda _b, k=kind: (self._filters.popdown(), self._set_filter(k)))
            box.pack_start(button, False, False, 0)
        box.show_all()
        self._filters.add(box)
        self._filter_button.set_tooltip_text(_("Filter") if self._filter is None else self._filter_name(self._filter))

    @staticmethod
    def _filter_name(kind):
        return _(FILTER_NAMES[kind]) if kind else _("All items")

    def _set_filter(self, kind):
        self._filter = kind
        for button in self._filters.get_child().get_children():
            button.set_property("active", button.kind == kind)
        self._filter_button.set_tooltip_text(_("Filter") if kind is None else self._filter_name(kind))
        self._apply_filter()

    def _apply_filter(self):
        self._list.invalidate_filter()
        self._list.invalidate_headers()
        shown = self._shown_rows()
        if shown and self._list.get_selected_row() not in shown:
            self._list.select_row(shown[0])

    def _is_shown(self, row):
        item = row.item
        if self._filter == FROM_PHONE:
            if not item.device:
                return False
        elif self._filter is not None and kinds.item_kind(item) != self._filter:
            return False
        query = self._search.get_text().strip().lower()
        if not query:
            return True
        if item.image or (item.secret and self._settings.get_boolean("hide-passwords")):
            return False  # nothing to search in what isn't shown
        return query in item.text.lower()

    def _shown_rows(self):
        return [row for row in self._list.get_children() if self._is_shown(row)]

    def _choose_first_shown(self):
        shown = self._shown_rows()
        if shown:
            self._on_choose(shown[0].item)

    def _on_search_key_press(self, _entry, event):
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            shown = self._shown_rows()
            if shown:
                self._list.select_row(shown[0])
                shown[0].grab_focus()
            return True
        return False

    def clear_search(self):
        """Escape: clear the search first. Returns whether there was one."""
        if self._bar.get_visible() and (self._search.get_text() or self._filter is not None):
            self._search.set_text("")
            self._set_filter(None)
            return True
        return False

    # The list

    def refresh(self):
        if any(row.menu_button.get_popover().get_mapped() for row in self._list.get_children()):
            self._refresh_after_menu = True
            return
        self._refresh_after_menu = False
        # Stay on the same item (pinned, moved...), or in the same place when it's gone.
        selected = self._list.get_selected_row()
        if selected is not None:  # read now: the rows are destroyed below
            had_focus = self._list.get_focus_child() is not None
            selected = (selected.item, selected.get_index(), had_focus)
        for row in self._list.get_children():
            self._list.remove(row)
        pinned, recent = self._history.pinned(), self._history.items()
        ImageTop.keep_only({self._history.image_path(i) for i in pinned + recent if i.image})
        self._update_search_bar(pinned + recent)
        for item in pinned:
            self._list.add(self._row(item, pinned=True))
        for item in recent:
            self._list.add(self._row(item, pinned=False))
        self._list.show_all()
        if self._editing is None:
            self._stack.set_visible_child_name("list" if pinned or recent else "empty")
        if selected is not None:
            self._select(*selected)

    def _select(self, item, index=0, focus=True):
        rows = self._shown_rows()
        if not rows:
            return
        row = next((r for r in rows if r.item is item), rows[min(index, len(rows) - 1)])
        self._list.select_row(row)
        if focus:
            row.grab_focus()

    def _row(self, item, pinned):
        row = Gtk.ListBoxRow()
        row.item = item
        row.pinned = pinned
        box = Gtk.Box(spacing=6, margin_start=12, margin_end=6, margin_top=8, margin_bottom=8)
        content = self._content(item)
        if item.device and self._settings.get_boolean("show-item-types"):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            column.pack_start(content, True, True, 0)
            column.pack_start(_device(item.device), False, False, 0)
            content = column
        box.pack_start(content, True, True, 0)
        row.menu_button = Gtk.MenuButton(relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.CENTER,
                                         tooltip_text=_("More"), popover=self._menu(item, pinned))
        row.menu_button.add(Gtk.Image.new_from_icon_name("view-more-symbolic", Gtk.IconSize.BUTTON))
        box.pack_end(row.menu_button, False, False, 0)
        row.add(box)
        return row

    def _content(self, item):
        if item.image:
            return ImageTop(self._history.image_path(item))
        box = Gtk.Box(spacing=8)
        show_types = self._settings.get_boolean("show-item-types")
        if item.secret and self._settings.get_boolean("hide-passwords"):
            if show_types:
                box.pack_start(_icon("dialog-password-symbolic", _("Password")), False, False, 0)
            box.pack_start(Gtk.Label(label=HIDDEN, xalign=0), False, False, 0)
            return box
        kind = kinds.kind_of(item.text) if show_types else None
        if kind == kinds.COLOR:
            box.pack_start(ColorSwatch(item.text), False, False, 0)
        elif kind is not None:
            box.pack_start(_icon(kinds.ICONS[kind], None), False, False, 0)
        elif item.secret and show_types:
            box.pack_start(_icon("dialog-password-symbolic", _("Password")), False, False, 0)
        box.pack_start(Gtk.Label(label=preview(item.text), xalign=0, wrap=True, lines=PREVIEW_LINES,
                                 wrap_mode=Pango.WrapMode.WORD_CHAR, ellipsize=Pango.EllipsizeMode.END,
                                 max_width_chars=1), True, True, 0)
        return box

    def _menu(self, item, pinned):
        popover = Gtk.Popover(position=Gtk.PositionType.BOTTOM)
        popover.connect("unmap", lambda _p: GLib.idle_add(self._on_menu_gone))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=6)
        entries = []
        if item.text is not None and not item.secret:  # images and passwords can't be edited
            entries.append((_("Edit"), lambda: self._edit(item)))
        entries += [
            (_("Delete"), lambda: self._history.remove(item)),
            (_("Unpin") if pinned else _("Pin"),
             lambda: (self._history.unpin if pinned else self._history.pin)(item)),
            (_("Paste"), lambda: self._on_paste(item)),
        ]
        if item.text is not None and self._phones is not None:
            for device_id, name in self._phones.devices():
                entries.append((_("Send to {}").format(name),
                                lambda device_id=device_id: self._phones.send(device_id, item.text)))
        for label, action in entries:
            button = Gtk.ModelButton(text=label)  # closes the menu
            button.connect("clicked", lambda _b, action=action: self._after_menu.append(action))
            box.pack_start(button, False, False, 0)
        box.show_all()
        popover.add(box)
        return popover

    def _on_menu_gone(self):
        actions, self._after_menu = self._after_menu, []
        for action in actions:
            action()
        if self._refresh_after_menu:
            self.refresh()
        return GLib.SOURCE_REMOVE

    def _header(self, row, before):
        if before is not None and before.pinned == row.pinned:
            row.set_header(None)
            return
        # Clear all deletes every recent item: not while only some are shown.
        searching = bool(self._search.get_text().strip()) or self._filter is not None
        current = row.get_header()
        if current is not None and (current.pinned, current.searching) == (row.pinned, searching):
            return
        header = Gtk.Box(spacing=6, margin_start=12, margin_end=6, margin_top=4, margin_bottom=4)
        header.pinned = row.pinned
        header.searching = searching
        title = Gtk.Label(label=_("Pinned") if row.pinned else _("Recent"), xalign=0)
        title.get_style_context().add_class("dim-label")
        header.pack_start(title, True, True, 0)
        if not row.pinned and not searching:
            clear = Gtk.Button(label=_("Clear all"), relief=Gtk.ReliefStyle.NONE)
            clear.connect("clicked", lambda _b: GLib.idle_add(_once, self._history.clear))
            header.pack_end(clear, False, False, 0)
        header.show_all()
        row.set_header(header)

    def _on_list_key_press(self, _list, event):
        # The Menu key or Shift+F10 opens the item's menu.
        menu_key = event.keyval == Gdk.KEY_Menu or (
            event.keyval == Gdk.KEY_F10 and event.state & Gdk.ModifierType.SHIFT_MASK)
        row = self._list.get_selected_row()
        if menu_key and row is not None:
            row.menu_button.set_active(True)
            return True
        # Typing searches.
        if self._bar.get_visible() and self._search.handle_event(event):
            self._search.grab_focus_without_selecting()
            return True
        return False

    def focus_first(self):
        self.cancel_edit()
        self._search.set_text("")
        self._set_filter(None)
        self._select(None)

    # Editing

    def _edit_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_start=8, margin_end=8, margin_bottom=2)
        title = Gtk.Label(xalign=0, margin_start=4)
        title.set_markup("<b>{}</b>".format(GLib.markup_escape_text(_("Edit"))))
        page.pack_start(title, False, False, 0)
        self._text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=6, right_margin=6,
                                  top_margin=6, bottom_margin=6)
        self._text.connect("key-press-event", self._on_text_key_press)
        self._text.get_buffer().connect(
            "changed", lambda buffer: self._save.set_sensitive(bool(_buffer_text(buffer).strip())))
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, shadow_type=Gtk.ShadowType.IN)
        scrolled.add(self._text)
        page.pack_start(scrolled, True, True, 0)
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda _b: self.cancel_edit())
        self._save = Gtk.Button(label=_("Save"))
        self._save.get_style_context().add_class("suggested-action")
        self._save.connect("clicked", lambda _b: self._save_edit())
        buttons.pack_start(cancel, False, False, 0)
        buttons.pack_start(self._save, False, False, 0)
        page.pack_start(buttons, False, False, 0)
        return page

    @property
    def editing(self):
        return self._editing is not None

    def _edit(self, item):
        self._editing = item
        self._text.get_buffer().set_text(item.text)
        self._stack.set_visible_child_name("edit")
        self._text.grab_focus()
        self.on_editing_changed(True)

    def _save_edit(self):
        self._history.edit(self._editing, _buffer_text(self._text.get_buffer()))
        self.cancel_edit()

    def cancel_edit(self):
        if self._editing is not None:
            self._close_edit(self._editing)

    def _close_edit(self, item):
        """Back to the list, on the edited item."""
        self._editing = None
        self.refresh()
        self._select(item)
        self.on_editing_changed(False)

    def _on_text_key_press(self, _view, event):
        # Ctrl+Enter saves; Enter alone is a new line.
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and event.state & Gdk.ModifierType.CONTROL_MASK:
            if self._save.get_sensitive():
                self._save_edit()
            return True
        return False


class ImageTop(Gtk.DrawingArea):
    """The top of an image, as wide as the row: images are never enlarged."""

    _cache = {}  # path: (the top of the image, its original width)

    def __init__(self, path):
        super().__init__(hexpand=True)
        self._pixbuf, self._width = self._load(path)
        if self._pixbuf is None:
            self.set_size_request(-1, 32)
        else:
            scale = min(1.0, IMAGE_WIDTH / self._width)
            ratio = self._pixbuf.get_width() / self._width  # of the loaded top to the original
            self.set_size_request(-1, int(min(IMAGE_HEIGHT, self._pixbuf.get_height() / ratio * scale)))
        self.connect("draw", self._on_draw)

    @classmethod
    def keep_only(cls, paths):
        for path in set(cls._cache) - paths:
            del cls._cache[path]

    @classmethod
    def _load(cls, path):
        if path not in cls._cache:
            try:
                image = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error:
                return None, 0
            width, height = image.get_width(), image.get_height()
            # Twice the width shown, for sharp HiDPI screens; just the top.
            scale = min(1.0, 2 * IMAGE_WIDTH / width)
            top = min(height, int(2 * IMAGE_HEIGHT / scale) + 1)
            image = image.new_subpixbuf(0, 0, width, top)
            cls._cache[path] = (image.scale_simple(max(1, int(width * scale)), max(1, int(top * scale)),
                                                   GdkPixbuf.InterpType.BILINEAR), width)
        return cls._cache[path]

    def _on_draw(self, _widget, cr):
        if self._pixbuf is None:
            return False
        allocation = self.get_allocation()
        scale = min(1.0, allocation.width / self._width) * self._width / self._pixbuf.get_width()
        _rounded(cr, min(allocation.width, self._pixbuf.get_width() * scale), allocation.height, 4)
        cr.clip()
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
        cr.paint()
        return False


class ColorSwatch(Gtk.DrawingArea):
    """A copied color (#ff8800, rgb(...)), shown."""

    def __init__(self, text):
        super().__init__(valign=Gtk.Align.CENTER, tooltip_text=text)
        self.set_size_request(16, 16)
        self._color = _parse_color(text)
        self.connect("draw", self._on_draw)

    def _on_draw(self, _widget, cr):
        _rounded(cr, 16, 16, 4)
        if self._color is not None:
            cr.set_source_rgba(*self._color)
            cr.fill_preserve()
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.8)
        cr.set_line_width(1)
        cr.stroke()
        return False


def _parse_color(text):
    text = text.strip()
    digits = text[1:]
    if text.startswith("#") and len(digits) in (4, 8):  # with alpha, which GDK doesn't read
        size = len(digits) // 4
        values = [int(digits[i * size:(i + 1) * size] * (3 - size), 16) / 255 for i in range(4)]
        return tuple(values)
    color = Gdk.RGBA()
    return (color.red, color.green, color.blue, color.alpha) if color.parse(text) else None


def _rounded(cr, width, height, radius):
    cr.new_sub_path()
    for x, y, start in ((width - radius, radius, -0.5), (width - radius, height - radius, 0),
                        (radius, height - radius, 0.5), (radius, radius, 1)):
        cr.arc(x, y, radius, start * 3.14159265, (start + 0.5) * 3.14159265)
    cr.close_path()


def _icon(name, tooltip):
    icon = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.BUTTON)
    icon.set_valign(Gtk.Align.CENTER)  # the kinds with an icon are one line
    icon.get_style_context().add_class("dim-label")
    if tooltip:
        icon.set_tooltip_text(tooltip)
    return icon


def _device(name):
    """Where an item was copied: a phone, by its name."""
    box = Gtk.Box(spacing=4)
    box.get_style_context().add_class("dim-label")
    box.pack_start(Gtk.Image.new_from_icon_name("phone-symbolic", Gtk.IconSize.MENU), False, False, 0)
    label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1)
    label.set_markup("<small>{}</small>".format(GLib.markup_escape_text(name)))
    box.pack_start(label, True, True, 0)
    return box


def _buffer_text(buffer):
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)


def _once(action):
    action()
    return GLib.SOURCE_REMOVE
