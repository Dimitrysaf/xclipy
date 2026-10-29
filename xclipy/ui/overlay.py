"""The overlay: a borderless window with the Clipboard and Emojis tabs.

It opens at the bottom right of the mouse pointer (in the bottom right corner of
the screen only without one), can be dragged by its empty parts, and closes when
something is chosen, on Escape, or when it loses the focus.
"""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from xclipy.i18n import _
from xclipy.placement import place
from xclipy.ui.clipboard_page import ClipboardPage
from xclipy.ui.emoji_page import EmojiPage

WIDTH, HEIGHT = 360, 440
# Cinnamon takes the keyboard for a moment when a shortcut is pressed: the
# overlay only closes when the focus doesn't come back by then.
FOCUS_LOST_MS = 200

CSS = b"""
window.xclipy-overlay { background-color: transparent; }
window.xclipy-overlay .xclipy-card {
    background-color: @theme_bg_color;
    border: 1px solid @borders;
    border-radius: 8px;
}
window.xclipy-overlay.xclipy-solid .xclipy-card { border-radius: 0; }
.xclipy-emoji { font-size: 20px; }
"""


def is_wayland(display):
    # The GType's name: the class's depends on whether GdkWayland was imported.
    return display is not None and display.__gtype__.name == "GdkWaylandDisplay"


def _server_time(gdk_window):
    """The X server's current time, so the window manager gives us the focus."""
    try:
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11
        return GdkX11.x11_get_server_time(gdk_window)
    except (ImportError, ValueError, TypeError):
        return Gdk.CURRENT_TIME


class Overlay(Gtk.Window):
    def __init__(self, application, history, settings, on_choose, on_paste, on_choose_emoji):
        # The helper in Cinnamon finds the overlay by this title; nothing shows
        # it, and screen readers say the accessible name.
        super().__init__(application=application, title="Xclipy")
        self.get_accessible().set_name(_("Clipboard history"))
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(WIDTH, HEIGHT)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.stick()  # on every workspace

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("xclipy-overlay")
        # Rounded corners need a see-through window, so compositing.
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)
        else:
            self.get_style_context().add_class("xclipy-solid")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("xclipy-card")
        self.add(card)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE, vexpand=True,
                                margin_bottom=6)
        self._settings = settings
        self._editing = False
        self.clipboard_page = ClipboardPage(history, settings, on_choose, on_paste)
        self.emoji_page = EmojiPage(settings, on_choose_emoji)
        self._stack.add_titled(self.clipboard_page, "clipboard", _("Clipboard"))
        self._stack.add_titled(self.emoji_page, "emoji", _("Emojis"))
        self._stack.connect("notify::visible-child-name", self._on_tab_changed)
        self._switcher = Gtk.StackSwitcher(stack=self._stack, halign=Gtk.Align.CENTER, margin_top=8,
                                           no_show_all=True)
        card.pack_start(self._switcher, False, False, 0)
        card.pack_start(self._stack, True, True, 0)
        card.show_all()
        settings.connect("changed::show-emojis", lambda *_args: self._show_tabs())
        self._show_tabs()
        self.clipboard_page.on_editing_changed = self._on_editing_changed
        self.clipboard_page.on_menu_closed = self._after_menu
        self.clipboard_page.on_drag = self.drag

        self.connect("key-press-event", self._on_key_press)
        # Presses the items, buttons and search don't take move the overlay.
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._on_button_press)
        self._hide_source = 0
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("focus-in-event", lambda *_args: self._cancel_hide())
        self.connect("hide", lambda *_args: self._cancel_hide())
        self.connect("delete-event", lambda *_args: self.hide() or True)

    def popup(self, tab="clipboard"):
        """Open on a tab ("clipboard" or "emoji") at the bottom right of the mouse pointer.

        On Wayland an application can't place its windows or know where the pointer
        is: the helper in Cinnamon places it the same way.
        """
        display = self.get_display()
        if not is_wayland(display):
            self.move(*self._position(display))
        self.clipboard_page.focus_first()
        if self.tab == tab:
            self._on_tab_changed(self._stack, None)  # start the tab afresh
        self.tab = tab
        self.show()
        self.present_with_time(_server_time(self.get_window()))

    def _position(self, display):
        pointer = monitor = None
        seat = display.get_default_seat()
        if seat is not None and seat.get_pointer() is not None:
            _screen, x, y = seat.get_pointer().get_position()
            pointer = (x, y)
            monitor = display.get_monitor_at_point(x, y)
        monitor = monitor or display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        minimum, _natural = self.get_preferred_size()  # the content can ask for more
        size = (max(WIDTH, minimum.width), max(HEIGHT, minimum.height))
        return place(size, (area.x, area.y, area.width, area.height), pointer)

    def _on_button_press(self, _window, event):
        # Only presses on the overlay's own background (around the tabs, its edges). A
        # press in the list or on a button bubbles up here too, but there it must stay a
        # click: once the window manager moves the window, the release never comes back.
        if Gtk.get_event_widget(event) is not self:
            return False
        return self.drag(event)

    def drag(self, event):
        """Let the window manager move the overlay with the pointer, on X11 and Wayland alike."""
        if event.button != Gdk.BUTTON_PRIMARY or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
        return True

    def _on_focus_out(self, *_args):
        if self.clipboard_page.menu_open:
            return  # its menu took the keyboard for a moment
        if not self._hide_source:
            self._hide_source = GLib.timeout_add(FOCUS_LOST_MS, self._hide_now)

    def _after_menu(self):
        """A menu closed: if a click elsewhere closed it, the overlay goes too."""
        self._cancel_hide()
        self._hide_source = GLib.timeout_add(FOCUS_LOST_MS, self._hide_unless_active)

    def _hide_unless_active(self):
        self._hide_source = 0
        if not self.is_active():
            self.hide()
        return GLib.SOURCE_REMOVE

    def _hide_now(self):
        self._hide_source = 0
        self.hide()
        return GLib.SOURCE_REMOVE

    def _cancel_hide(self):
        if self._hide_source:
            GLib.source_remove(self._hide_source)
            self._hide_source = 0

    def switch_to(self, tab):
        """Show another tab, and take the keyboard back from the shortcut."""
        self._cancel_hide()
        self.tab = tab
        self.present_with_time(_server_time(self.get_window()))

    @property
    def tab(self):
        return self._stack.get_visible_child_name()

    @tab.setter
    def tab(self, name):
        self._stack.set_visible_child_name(name)

    def _on_editing_changed(self, editing):
        # The edit page has the whole overlay: no tabs, until Save or Cancel.
        self._editing = editing
        self._show_tabs()

    def _show_tabs(self):
        """The tabs, unless editing or with the emojis turned off (just the clipboard then)."""
        emojis = self._settings.get_boolean("show-emojis")
        self.emoji_page.set_visible(emojis)
        if not emojis:
            self.tab = "clipboard"
        shown = emojis and not self._editing
        self._switcher.set_visible(shown)
        self._switcher.foreach(lambda button: button.show())
        self._stack.set_margin_top(0 if shown else 8)

    def _on_tab_changed(self, stack, _param):
        if stack.get_visible_child_name() == "emoji":
            self.emoji_page.prepare()
        else:
            self.clipboard_page.focus_first()

    def _on_key_press(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.clipboard_page.editing:
                self.clipboard_page.cancel_edit()
            elif not self.clipboard_page.clear_search():
                self.hide()
            return True
        if self._settings.get_boolean("show-emojis") and event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (
                Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Page_Down, Gdk.KEY_Page_Up):
            # Ctrl+Tab and Ctrl+Page Up/Down switch tabs, like in a browser.
            other = "emoji" if self._stack.get_visible_child_name() == "clipboard" else "clipboard"
            self._stack.set_visible_child_name(other)
            return True
        return False
