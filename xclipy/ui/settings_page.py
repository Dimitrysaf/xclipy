"""Xclipy's settings, as a page of the XApp settings widgets.

The same page is in Cinnamon's System Settings (cs_xclipy.py) and, on other
desktops, in Xclipy's own settings window.
"""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from xapp.GSettingsWidgets import (
    Button, GSettingsComboBox, GSettingsSpinButton, GSettingsSwitch, SettingsLabel, SettingsWidget,
)

from xclipy import APP_ID, DBUS_PATH, SCHEMA_ID, helper, shortcut
from xclipy.i18n import _

# Where the desktop lists the shortcuts too.
SHORTCUT_NOTES = {
    "cinnamon": lambda: _("They are also listed in Keyboard, under Shortcuts → Custom Shortcuts."),
    "mate": lambda: _("They are also listed in Keyboard Shortcuts, under Custom Shortcuts."),
    "xfce": lambda: _("They are also listed in Keyboard, under Application Shortcuts."),
}


def fill(page, backend=None):
    """Add the settings to an xapp SettingsPage, with this desktop's shortcuts (or None)."""
    section = page.add_section()
    section.add_row(GSettingsSwitch(_("Enable clipboard history"), SCHEMA_ID, "enabled"))

    # Everything else only while the history is on.
    def reveal_section(title):
        return page.add_reveal_section(title, SCHEMA_ID, "enabled")

    section = reveal_section(_("Keyboard shortcuts"))
    if backend is not None:
        section.add_row(_shortcut_row(_("Open the clipboard history"), shortcut.Shortcut(shortcut.CLIPBOARD, backend)))
        section.add_reveal_row(_shortcut_row(_("Open the emojis"), shortcut.Shortcut(shortcut.EMOJI, backend)),
                               SCHEMA_ID, "show-emojis")
        section.add_note(SHORTCUT_NOTES[backend.desktop]())
    else:
        section.add_note(_("Set them in your desktop's keyboard settings: “xclipy --show” opens the "
                           "clipboard history and “xclipy --emoji” the emojis."))

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
    section.add_row(Button(_("Clear history"), _clear_history))

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

    # Which application copies something is only known on X11, or on Wayland
    # with the helper in Cinnamon.
    if not _is_wayland() or helper.running():
        section = reveal_section(_("Excluded applications"))
        section.add_row(ExcludedApplications())
        section.add_note(_("What these applications copy is never kept."))

    section = reveal_section(_("Emojis"))
    section.add_row(GSettingsSwitch(_("Show emojis"), SCHEMA_ID, "show-emojis"))
    tones = [("none", _("Default")), ("light", _("Light")), ("medium-light", _("Medium-light")),
             ("medium", _("Medium")), ("medium-dark", _("Medium-dark")), ("dark", _("Dark"))]
    section.add_reveal_row(GSettingsComboBox(_("Skin tone"), SCHEMA_ID, "emoji-skin-tone", tones),
                           SCHEMA_ID, "show-emojis")


def _clear_history(_button):
    # The history lives in the running xclipy (D-Bus starts it if needed).
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    Gio.DBusActionGroup.get(bus, APP_ID, DBUS_PATH).activate_action("clear-history", None)


def _shortcut_row(label, keys):
    row = SettingsWidget()
    row.pack_start(SettingsLabel(label), False, False, 0)
    button = ShortcutButton(keys.binding())
    button.connect("changed", lambda _b, accelerator: keys.set_binding(accelerator))
    row.pack_end(button, False, False, 0)
    return row


class ShortcutButton(Gtk.Button):
    """Shows a keyboard shortcut; click it and press keys to change it."""

    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_LAST, None, (str,))}

    def __init__(self, accelerator):
        super().__init__(tooltip_text=_("Click, then press the new keys. Escape cancels, "
                                        "Backspace removes the shortcut."))
        self.set_size_request(200, -1)
        self._accelerator = accelerator
        self._listening = False
        self._show()
        self.connect("clicked", lambda _b: self._listen())
        self.connect("key-press-event", self._on_key_press)
        self.connect("focus-out-event", lambda *_args: self._stop())

    def _show(self):
        if self._listening:
            self.set_label(_("New shortcut…"))
        elif self._accelerator:
            key, mods = Gtk.accelerator_parse(self._accelerator)
            self.set_label(Gtk.accelerator_get_label(key, mods) if key else self._accelerator)
        else:
            self.set_label(_("None"))

    def _listen(self):
        self._listening = True
        self._show()

    def _stop(self):
        if self._listening:
            self._listening = False
            self._show()

    def _on_key_press(self, _button, event):
        if not self._listening:
            return False
        keyval = Gdk.keyval_to_lower(event.keyval)
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        if keyval == Gdk.KEY_Escape and not mods:
            self._stop()
        elif keyval == Gdk.KEY_BackSpace and not mods:
            self._set("")
        elif _is_modifier(keyval):
            return True  # wait for the key itself
        elif mods or Gdk.KEY_F1 <= keyval <= Gdk.KEY_F35:
            self._set(Gtk.accelerator_name(keyval, mods))
        return True  # a key alone, without Ctrl, Alt or Super, isn't a shortcut

    def _set(self, accelerator):
        self._accelerator = accelerator
        self._stop()
        self.emit("changed", accelerator)


def _is_modifier(keyval):
    return keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
                      Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
                      Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_ISO_Level3_Shift, Gdk.KEY_Hyper_L,
                      Gdk.KEY_Hyper_R)


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
            row.pack_start(_app_icon(info), False, False, 0)
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
            line.pack_start(_app_icon(info), False, False, 0)
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


def _app_icon(info):
    icon = info.get_icon() if info is not None else None
    if icon is not None:
        return Gtk.Image.new_from_gicon(icon, Gtk.IconSize.LARGE_TOOLBAR)
    return Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR)


def _is_wayland():
    display = Gdk.Display.get_default()
    return display is not None and display.__gtype__.name == "GdkWaylandDisplay"


def _app_info(desktop_id):
    try:
        return Gio.DesktopAppInfo.new(desktop_id)
    except TypeError:
        return None
