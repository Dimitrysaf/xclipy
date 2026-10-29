#!/usr/bin/python3
"""Open Xclipy's overlay on a sample history, optionally saving screenshots.

    python3 tools/preview.py                  # interactive
    xvfb-run -a python3 tools/preview.py --shots /tmp/shots   # headless PNGs

The settings are kept in memory and the history in a temporary folder, so
the real ones are left alone.
"""

import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SAMPLES = [
    "https://github.com/Dimitrysaf/xclipy",
    "sudo apt install xclipy",
    "Καλημέρα! Τα λέμε στις 10.",
    "def place(size, workarea, caret=None):\n    width, height = size\n    area_x, area_y = workarea[:2]\n"
    "    return area_x + width, area_y + height",
    "A longer paragraph that was copied from a web page, to show how the text of an item "
    "is cut after three lines so that every item stays about the same height in the list.",
    "42",
]


def use_temporary_settings(folder):
    """Compile the schema next to the checkout's and keep settings in memory."""
    subprocess.run(["glib-compile-schemas", "--targetdir", folder, os.path.join(ROOT, "data")], check=True)
    os.environ["GSETTINGS_SCHEMA_DIR"] = folder
    os.environ["GSETTINGS_BACKEND"] = "memory"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", metavar="FOLDER", help="save screenshots there and quit")
    parser.add_argument("--empty", action="store_true", help="start with an empty history")
    args = parser.parse_args()

    folder = tempfile.TemporaryDirectory()
    use_temporary_settings(folder.name)

    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk

    from xclipy import SCHEMA_ID
    from xclipy.history import ClipboardHistory
    from xclipy.ui.overlay import Overlay

    settings = Gio.Settings.new(SCHEMA_ID)
    settings.set_strv("recent-emoji", ["👍", "😂", "❤️", "🎉"])
    history = ClipboardHistory(os.path.join(folder.name, "history.json"), 50)
    for text in [] if args.empty else reversed(SAMPLES):
        history.add_text(text)

    app = Gtk.Application(application_id="org.x.Xclipy.Preview",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)

    def capture(window, name):
        gdk_window = window.get_window()
        pixbuf = Gdk.pixbuf_get_from_window(
            gdk_window, 0, 0, gdk_window.get_width(), gdk_window.get_height())
        path = os.path.join(args.shots, name)
        pixbuf.savev(path, "png", [], [])
        print("saved", path, flush=True)

    def on_activate(application):
        overlay = Overlay(application, history, settings, lambda text: print("chose", repr(text)),
                          lambda text: print("paste", repr(text)),
                          lambda text: print("chose emoji", repr(text)))
        history.on_changed = overlay.clipboard_page.refresh
        overlay.popup()
        if args.shots:
            os.makedirs(args.shots, exist_ok=True)
            steps = [
                (lambda: capture(overlay, "01-clipboard.png")),
                (lambda: overlay._stack.set_visible_child_name("emoji")),
                (lambda: capture(overlay, "02-emoji-recent.png")),
                (lambda: overlay.emoji_page._group_buttons[2].set_active(True)),
                (lambda: capture(overlay, "03-emoji-animals.png")),
                (lambda: overlay.emoji_page._search.set_text("cat")),
                (lambda: capture(overlay, "04-emoji-search.png")),
                (lambda: history.clear()),
                (lambda: overlay._stack.set_visible_child_name("clipboard")),
                (lambda: capture(overlay, "05-clipboard-empty.png")),
                application.quit,
            ]

            def step():
                steps.pop(0)()
                return bool(steps)
            GLib.timeout_add(500, step)
        else:
            overlay.connect("hide", lambda _w: application.quit())

    app.connect("activate", on_activate)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
