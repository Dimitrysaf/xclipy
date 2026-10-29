"""Adds what is copied to the clipboard to the history.

Text is kept; images too when the settings say so. Text that a password
manager marks as secret (KeePassXC, KWallet, ...) is kept as a password, and
so is text that looks random (when the settings say so).
Nothing is kept while the history is turned off, or from excluded
applications.

On Wayland an application only sees the clipboard while it has the keyboard
focus: there, the copies come from Xclipy's helper in Cinnamon, when it runs.
"""

import hashlib
import os
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from xclipy import apps
from xclipy.kinds import looks_random

# Password managers (KeePassXC, KWallet, ...) offer this target with "secret".
PASSWORD_HINT = "x-kde-passwordManagerHint"
MAX_IMAGE_PIXELS = 4096 * 4096
TEXT_TYPES = ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain")
OWN_COPY_SECONDS = 2  # the helper tells about Xclipy's own copies too


def is_password(target_names):
    return PASSWORD_HINT in target_names


def image_name(pixbuf):
    """A name for the image's file, the same for the same picture."""
    digest = hashlib.sha256()
    digest.update("{}x{}x{}".format(pixbuf.get_width(), pixbuf.get_height(), pixbuf.get_n_channels()).encode())
    digest.update(pixbuf.read_pixel_bytes().get_data())
    return digest.hexdigest()[:32] + ".png"


class ClipboardWatcher:
    def __init__(self, history, settings, helper=None):
        """helper: Xclipy's helper in Cinnamon, for the copies on Wayland."""
        self._history = history
        self._settings = settings
        self._helper = helper
        self._focused = apps.FocusedApplication(helper)
        self._own_change = False  # the next owner change is ours
        self._own_copy = (None, 0)  # what Xclipy itself put there, and when
        # The passwords seen (as digests, in memory): Cinnamon can offer one
        # again without its mark, and a forgotten one mustn't come back.
        self._secrets = set()
        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._clipboard.connect("owner-change", self._on_owner_change)

    def copy(self, item):
        """Put a history item, or text that isn't kept (an emoji), on the clipboard."""
        self._own_change = True
        self._own_copy = (item if isinstance(item, str) else item.text, time.monotonic())
        if isinstance(item, str):
            self._clipboard.set_text(item, -1)
        elif item.image:
            try:
                self._clipboard.set_image(GdkPixbuf.Pixbuf.new_from_file(self._history.image_path(item)))
            except GLib.Error:
                self._own_change = False
        else:
            self._clipboard.set_text(item.text, -1)

    def forget(self, item):
        """Take a password off the clipboard, if it's still on it."""
        if item.text is not None:
            self._clipboard.request_text(self._empty_if, item.text)

    def _empty_if(self, clipboard, text, password):
        if text == password:
            # Emptied rather than cleared: Cinnamon would put it back.
            self._own_change = True
            clipboard.set_text("", -1)

    def _on_owner_change(self, clipboard, _event):
        if self._own_change:
            self._own_change = False
            return
        if self._wanted():
            clipboard.request_targets(self._on_targets)

    def _wanted(self):
        """Whether to keep what was just copied: history on, not an excluded application."""
        if not self._settings.get_boolean("enabled"):
            return False
        excluded = self._settings.get_strv("excluded-apps")
        return not (excluded and apps.is_excluded(self._focused.names(), excluded))

    def on_helper_copy(self, mimetypes):
        """The helper says something was copied (Wayland)."""
        own_text, own_time = self._own_copy
        if time.monotonic() - own_time < OWN_COPY_SECONDS and own_text is None:
            return  # an image Xclipy put there
        if not self._wanted():
            return
        secret = PASSWORD_HINT in mimetypes
        text_type = next((t for t in TEXT_TYPES if t in mimetypes), None)
        if text_type is not None:
            def got_text(data):
                text = data.decode("utf-8", "replace") if data else None
                if text is not None and not (text == own_text and time.monotonic() - own_time < OWN_COPY_SECONDS):
                    self._on_text(None, text, secret)
            self._helper.read_clipboard(text_type, got_text)
        elif self._settings.get_boolean("store-images") and "image/png" in mimetypes:
            self._helper.read_clipboard("image/png", self._got_png)

    def _got_png(self, data):
        if not data:
            return
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        try:
            loader.write(data)
            loader.close()
        except GLib.Error:
            return
        self._on_image(None, loader.get_pixbuf())

    def _on_targets(self, clipboard, targets, *_args):
        targets = targets or []
        secret = is_password([target.name() for target in targets])
        if Gtk.targets_include_text(targets):
            clipboard.request_text(self._on_text, secret)
        elif self._settings.get_boolean("store-images") and Gtk.targets_include_image(targets, False):
            clipboard.request_image(self._on_image)

    def _on_text(self, _clipboard, text, secret):
        if text is None:
            return
        if not secret and self._settings.get_boolean("recognise-random-passwords"):
            secret = looks_random(text.strip())
        digest = hashlib.sha256(text.encode()).digest()
        if secret:
            self._secrets.add(digest)
        elif digest in self._secrets:
            if not self._history.has_text(text):
                return  # a forgotten password
            secret = True
        self._history.add_text(text, secret)

    def _on_image(self, _clipboard, pixbuf, *_args):
        if pixbuf is None or pixbuf.get_width() * pixbuf.get_height() > MAX_IMAGE_PIXELS:
            return
        name = image_name(pixbuf)
        folder = self._history.images_dir
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            os.makedirs(folder, mode=0o700, exist_ok=True)
            try:
                pixbuf.savev(path, "png", [], [])
                os.chmod(path, 0o600)
            except GLib.Error:
                return
        self._history.add_image(name)
