"""The overlays: borderless windows with the clipboard history, or the emojis.

Each opens at the bottom right of the mouse pointer (in the bottom right corner
of the screen only without one), where it was decided before it opened, and
closes when something is chosen, on Escape, or when it loses the focus. It
can't be moved. The emoji overlay is only made the first time it opens.
"""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from xclipy.i18n import _
from xclipy.ui.clipboard_page import ClipboardPage
from xclipy.ui.emoji_page import EmojiPage

WIDTH, HEIGHT = 360, 440
# Cinnamon takes the keyboard for a moment when a shortcut is pressed: the
# overlay only closes when the focus doesn't come back by then.
FOCUS_LOST_MS = 200
FADE_MS = 120  # the fade in when it opens, about as quick as a menu
# The helper in Cinnamon finds the overlays by this title; nothing shows it.
TITLE = "Xclipy"

# The card is drawn as the theme draws a menu (Mint-Y: square, with a 1px border),
# so its corners, border and background are the theme's; only a menu's outer margin
# is dropped, as the window is exactly the card's size. Nothing in it drags the window.
CSS = b"""
window.xclipy-overlay { background-color: transparent; }
window.xclipy-overlay, window.xclipy-overlay * { -GtkWidget-window-dragging: false; }
window.xclipy-overlay .xclipy-card { margin: 0; }
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
    """What both overlays share: no window bar, above the others, closing on its own."""

    def __init__(self, application, name, page):
        # Screen readers say the accessible name, not the title.
        super().__init__(application=application, title=TITLE)
        self.get_accessible().set_name(name)
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
        self._composited = visual is not None and screen.is_composited()
        if self._composited:
            self.set_visual(visual)
            self.set_app_paintable(True)
        else:
            self.get_style_context().add_class("xclipy-solid")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.get_style_context().add_class("menu")
        card.get_style_context().add_class("xclipy-card")
        page.set_margin_top(8)
        page.set_margin_bottom(6)
        card.pack_start(page, True, True, 0)
        card.show_all()
        self.add(card)
        self._card = card
        self._fade_id = 0

        self.connect("key-press-event", self._on_key_press)
        self._hide_source = 0
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("focus-in-event", lambda *_args: self._cancel_hide())
        self.connect("hide", lambda *_args: self._cancel_hide())
        self.connect("delete-event", lambda *_args: self.hide() or True)

    def size(self):
        """The (width, height) it opens with: the content can ask for more."""
        minimum, _natural = self.get_preferred_size()
        return max(WIDTH, minimum.width), max(HEIGHT, minimum.height)

    def popup(self, position=None):
        """Open at ``position``, (x, y) on the screen, decided before it opens.

        Without one (on Wayland, where applications can't place their windows),
        the window manager places it: the helper in Cinnamon, where Xclipy asked.
        """
        if position is not None:
            self.move(*position)
        self.prepare()
        self._fade_in()
        self.show()
        self.present_with_time(_server_time(self.get_window()))

    def prepare(self):
        """Start afresh, before opening."""

    def escape(self):
        """Escape was pressed: close, unless the overlay has something to undo first."""
        self.hide()

    def menu_open(self):
        """Whether one of its menus has the keyboard for now."""
        return False

    def _fade_in(self):
        """Fade the content in. The window itself can't fade on Wayland, its content can."""
        if self._fade_id:
            self.remove_tick_callback(self._fade_id)
            self._fade_id = 0
        if not self._composited or not Gtk.Settings.get_default().props.gtk_enable_animations:
            self._card.set_opacity(1.0)  # nothing to fade through, or animations are off
            return
        self._card.set_opacity(0.0)
        start = []

        def tick(_widget, clock):
            now = clock.get_frame_time()
            if not start:
                start.append(now)
            progress = min(1.0, (now - start[0]) / (FADE_MS * 1000))
            self._card.set_opacity(1 - (1 - progress) ** 3)  # quick at first, like a menu
            if progress < 1.0:
                return GLib.SOURCE_CONTINUE
            self._fade_id = 0
            return GLib.SOURCE_REMOVE
        self._fade_id = self.add_tick_callback(tick)

    def _on_focus_out(self, *_args):
        if self.menu_open():
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

    def _on_key_press(self, _window, event):
        if event.keyval != Gdk.KEY_Escape:
            return False
        self.escape()
        return True


class ClipboardOverlay(Overlay):
    def __init__(self, application, history, settings, on_choose, on_paste):
        self.page = ClipboardPage(history, settings, on_choose, on_paste)
        super().__init__(application, _("Clipboard history"), self.page)
        self.page.on_menu_closed = self._after_menu

    def prepare(self):
        self.page.focus_first()

    def escape(self):
        if self.page.editing:
            self.page.cancel_edit()
        elif not self.page.clear_search():
            self.hide()

    def menu_open(self):
        return self.page.menu_open


class EmojiOverlay(Overlay):
    def __init__(self, application, settings, on_choose):
        self.page = EmojiPage(settings, on_choose)
        super().__init__(application, _("Emojis"), self.page)

    def prepare(self):
        self.page.prepare()
