#!/usr/bin/python3
"""Xclipy's page in Cinnamon's System Settings, "Clipboard".

System Settings loads every cs_*.py module in
/usr/share/cinnamon/cinnamon-settings/modules; this one is installed there.
"""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from bin.KeybindingWidgets import ButtonKeybinding
from bin.SettingsWidgets import SidePage
from xapp.GSettingsWidgets import (
    Button, GSettingsComboBox, GSettingsSpinButton, GSettingsSwitch, SettingsLabel, SettingsPage,
    SettingsWidget,
)

from xclipy import APP_ID, DBUS_PATH, SCHEMA_ID, shortcut
from xclipy.i18n import _


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

        section = page.add_section()
        section.add_row(GSettingsSwitch(_("Enable clipboard history"), SCHEMA_ID, "enabled"))

        # Everything else only while the history is on.
        def reveal_section(title):
            return page.add_reveal_section(title, SCHEMA_ID, "enabled")

        section = reveal_section(_("Keyboard shortcuts"))
        section.add_row(shortcut_row(_("Open the clipboard history"), shortcut.CLIPBOARD))
        section.add_row(shortcut_row(_("Open the emojis"), shortcut.EMOJI))
        section.add_note(_("They are also listed in Keyboard, under Shortcuts → Custom Shortcuts."))

        section = reveal_section(_("History"))
        section.add_row(GSettingsSpinButton(_("Number of recent items"), SCHEMA_ID, "history-size"))
        section.add_row(GSettingsSwitch(_("Paste the chosen item"), SCHEMA_ID, "paste-on-select"))
        section.add_row(GSettingsSwitch(_("Show item types"), SCHEMA_ID, "show-item-types"))
        section.add_row(GSettingsSwitch(_("Show search bar"), SCHEMA_ID, "show-search"))
        section.add_row(GSettingsSwitch(_("Keep copied images"), SCHEMA_ID, "store-images"))
        section.add_row(GSettingsSwitch(_("Clear recent items when logging out"), SCHEMA_ID, "clear-on-logout"))
        section.add_row(GSettingsSwitch(_("Delete old recent items"), SCHEMA_ID, "delete-old-items"))
        section.add_reveal_row(GSettingsSpinButton(_("Older than"), SCHEMA_ID, "delete-old-days", _("days")),
                               SCHEMA_ID, "delete-old-items")
        section.add_row(Button(_("Clear history"), self.on_clear_history))

        section = reveal_section(_("Passwords"))
        section.add_row(GSettingsSwitch(_("Hide passwords"), SCHEMA_ID, "hide-passwords"))
        section.add_row(GSettingsSwitch(_("Treat random-looking text as a password"), SCHEMA_ID,
                                        "recognise-random-passwords"))
        section.add_row(GSettingsSwitch(_("Delete passwords once pasted"), SCHEMA_ID, "clear-pasted-passwords"))
        section.add_row(GSettingsSwitch(_("Forget passwords after a while"), SCHEMA_ID, "forget-passwords"))
        section.add_reveal_row(
            GSettingsSpinButton(_("After"), SCHEMA_ID, "forget-passwords-minutes", _("minutes")),
            SCHEMA_ID, "forget-passwords")
        section.add_row(GSettingsSwitch(_("Save pinned passwords in Passwords and Keys"), SCHEMA_ID,
                                        "save-pinned-passwords"))
        section.add_note(_("Passwords are recognised when the application copying them says so, "
                           "as password managers like KeePassXC do, or when they look random, like "
                           "generated passwords and keys. They are only saved in your keyring, when "
                           "pinned and the option above is on."))

        # Which application copies something is only known on X11.
        if not _is_wayland():
            section = reveal_section(_("Excluded applications"))
            section.add_row(ExcludedApplications())
            section.add_note(_("What these applications copy is never kept."))

        section = reveal_section(_("Emojis"))
        tones = [("none", _("Default")), ("light", _("Light")), ("medium-light", _("Medium-light")),
                 ("medium", _("Medium")), ("medium-dark", _("Medium-dark")), ("dark", _("Dark"))]
        section.add_row(GSettingsComboBox(_("Skin tone"), SCHEMA_ID, "emoji-skin-tone", tones))

    @staticmethod
    def on_clear_history(_button):
        # The history lives in the running xclipy (D-Bus starts it if needed).
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        Gio.DBusActionGroup.get(bus, APP_ID, DBUS_PATH).activate_action("clear-history", None)


def shortcut_row(label, kind):
    keys = shortcut.Shortcut(kind)
    row = SettingsWidget()
    row.pack_start(SettingsLabel(label), False, False, 0)
    button = ButtonKeybinding()
    button.set_size_request(200, -1)
    button.set_accel_string(next(iter(keys.binding()), ""))
    button.connect("accel-edited", lambda _b, accel, _label: keys.set_binding([accel]))
    button.connect("accel-cleared", lambda _b: keys.set_binding([]))
    row.pack_end(button, False, False, 0)
    return row


class ExcludedApplications(SettingsWidget):
    """The excluded applications, by desktop file, with Add and Remove."""

    def __init__(self):
        super().__init__()
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(6)
        self.settings = Gio.Settings.new(SCHEMA_ID)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.pack_start(self.list, False, False, 0)
        add = Gtk.Button(label=_("Add an application…"), halign=Gtk.Align.START)
        add.connect("clicked", self.on_add)
        self.pack_start(add, False, False, 0)
        self.settings.connect("changed::excluded-apps", lambda *_args: self.refresh())
        self.refresh()

    def refresh(self):
        for child in self.list.get_children():
            self.list.remove(child)
        excluded = self.settings.get_strv("excluded-apps")
        if not excluded:
            none = SettingsLabel(_("No applications"))
            none.get_style_context().add_class("dim-label")
            self.list.pack_start(none, False, False, 0)
        for desktop_id in excluded:
            info = _app_info(desktop_id)
            row = Gtk.Box(spacing=10)
            icon = info.get_icon() if info is not None else None
            row.pack_start(Gtk.Image.new_from_gicon(icon, Gtk.IconSize.LARGE_TOOLBAR) if icon
                           else Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR),
                           False, False, 0)
            name = info.get_display_name() if info is not None else desktop_id.rsplit(".desktop", 1)[0]
            row.pack_start(SettingsLabel(name), False, False, 0)
            remove = Gtk.Button.new_from_icon_name("list-remove-symbolic", Gtk.IconSize.BUTTON)
            remove.set_relief(Gtk.ReliefStyle.NONE)
            remove.set_tooltip_text(_("Remove"))
            remove.connect("clicked", lambda _b, d=desktop_id: self.settings.set_strv(
                "excluded-apps", [x for x in self.settings.get_strv("excluded-apps") if x != d]))
            row.pack_end(remove, False, False, 0)
            self.list.pack_start(row, False, False, 0)
        self.list.show_all()

    def on_add(self, button):
        dialog = ApplicationChooser(button.get_toplevel(), self.settings.get_strv("excluded-apps"))
        if dialog.run() == Gtk.ResponseType.OK and dialog.chosen:
            self.settings.set_strv("excluded-apps", self.settings.get_strv("excluded-apps") + [dialog.chosen])
        dialog.destroy()


class ApplicationChooser(Gtk.Dialog):
    """The installed applications, with a search."""

    def __init__(self, parent, excluded):
        super().__init__(title=_("Add an application"), transient_for=parent, modal=True)
        self.set_default_size(420, 480)
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.add_button(_("Add"), Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self.chosen = None

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(8)
        search = Gtk.SearchEntry(placeholder_text=_("Search applications"))
        box.pack_start(search, False, False, 0)
        self.list = Gtk.ListBox(activate_on_single_click=False)
        self.list.connect("row-selected", self.on_selected)
        self.list.connect("row-activated", lambda *_args: self.response(Gtk.ResponseType.OK))
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, shadow_type=Gtk.ShadowType.IN)
        scrolled.add(self.list)
        box.pack_start(scrolled, True, True, 0)

        apps = [info for info in Gio.AppInfo.get_all()
                if info.should_show() and info.get_id() and info.get_id() not in excluded]
        for info in sorted(apps, key=lambda i: GLib.utf8_collate_key(i.get_display_name().lower(), -1)):
            row = Gtk.ListBoxRow()
            row.desktop_id = info.get_id()
            row.search_text = " ".join(filter(None, (info.get_display_name(), info.get_id()))).lower()
            line = Gtk.Box(spacing=10, margin=6)
            icon = info.get_icon()
            line.pack_start(Gtk.Image.new_from_gicon(icon, Gtk.IconSize.LARGE_TOOLBAR) if icon
                            else Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR),
                            False, False, 0)
            line.pack_start(Gtk.Label(label=info.get_display_name(), xalign=0), True, True, 0)
            row.add(line)
            self.list.add(row)
        self.list.set_filter_func(lambda row: search.get_text().lower() in row.search_text)
        search.connect("search-changed", lambda _s: self.list.invalidate_filter())
        self.set_response_sensitive(Gtk.ResponseType.OK, False)
        self.show_all()

    def on_selected(self, _list, row):
        self.chosen = row.desktop_id if row is not None else None
        self.set_response_sensitive(Gtk.ResponseType.OK, row is not None)


def _is_wayland():
    return type(Gdk.Display.get_default()).__name__.startswith("Wayland")


def _app_info(desktop_id):
    try:
        return Gio.DesktopAppInfo.new(desktop_id)
    except TypeError:
        return None
