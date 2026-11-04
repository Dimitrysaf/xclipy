# Xclipy

Clipboard history for the Cinnamon, MATE and Xfce desktops.

<img width="360" height="440" alt="Xclipy's clipboard history: a pinned item, then the recent ones with their types" src="screenshots/clipboard.png" /> <img width="390" height="440" alt="Xclipy's emojis, on the Smileys group" src="screenshots/emoji.png" />

<img width="1000" height="730" alt="Xclipy's settings in System Settings, on the General tab" src="screenshots/settings.png" />

## Features

### Clipboard history

Super + V opens an overlay with your clipboard history. It opens right at your
mouse pointer, like a right-click menu, so your eyes (and your mouse) don't
have to travel far. Choose an item and it's pasted where you were typing.

Items are sorted into types, like links, email addresses, phone numbers,
files, color codes (with a little swatch of the color) and passwords. Passwords
are hidden as •••••••• once recognised, and they only live in memory: they're
gone after a reboot, even if you pin them. If you want pinned passwords to
stick around, turn on saving them to the keyring.

Images can be copied too. Don't want them? Turn them off in the settings. Heck,
you can turn off whatever you like in the settings. Even the clipboard history
itself :)

Anything can be pinned to the top, edited, deleted or pasted from its menu, and
a search bar can join the bottom of the overlay if you like searching more than
scrolling.

### Emojis

Sometimes words aren't enough 🙂. Turn on Show emojis in the settings, and
Super + . opens an overlay of its own with every emoji, in groups, with
search, your recently used ones first and the skin tone you prefer. They're
off by default: it's a clipboard manager first, and emojis left off don't
take a byte of memory.

### Keyboard

Your hands never have to leave the keyboard: arrows to move, Enter to choose,
the Menu key (or Shift+F10) for an item's menu, Escape to close. While editing,
Ctrl+Enter saves and Escape cancels. With the search bar, just type to search,
Down goes back to the list and Escape clears the search. With the emojis, just
type.

### What is saved

You choose what is kept after logging out: everything, only your pinned items
(the default), or nothing at all. Only that is written to disk, in your home
folder and readable only by you; the rest stays in memory and is gone when you
log out. Passwords never go to disk. Clear history, in the settings, deletes
everything, pinned items included.

## Architecture

`xclipy` is the application, in Python with GTK 3. It starts at login without a
window (`xclipy --background`, XDG autostart) and watches the clipboard. The
keyboard shortcuts run `xclipy --show` and `xclipy --emoji`, which reach the
running Xclipy over D-Bus (`org.x.Xclipy`, which also starts it if needed) and
open or close the clipboard overlay or the emoji overlay. The emoji overlay is
only made the first time it opens, and dropped when the emojis are turned off;
Super+. is only added to the desktop's shortcuts the first time they're turned
on. `xclipy --settings` opens the settings.

### Watching the clipboard

Xclipy follows the clipboard's owner changes (GTK on X11, the helper on
Wayland) and reads the new content as text or, when images are kept, as an
image. It skips its own copies, and copies made in an excluded application:
the application is the window with the keyboard focus (libwnck on X11, the
helper on Wayland), matched by its window class, application id and program
name. When an application quits, Cinnamon and MATE put back what it had
copied, as plain text; Xclipy remembers the passwords it has seen (as SHA-256
digests, in memory), so a password stays one, and a forgotten one isn't kept
again.

### Recognising passwords and other kinds

- **Passwords** are recognised in two ways (`xclipy/kinds.py`,
  `xclipy/watcher.py`):
  - The copying application marks them: password managers (KeePassXC,
    KWallet, ...) add the `x-kde-passwordManagerHint` target to the
    clipboard.
  - They look random: one word of 8 to 128 characters, mixing at least three
    of lowercase, uppercase, digits and symbols, switching between them
    often, with few runs of three or more of the same class, as words have.
    Links, email addresses, paths, numbers, UUIDs and hashes never count.
    "xK9#mQ2$vL" is a password; "user_name_2" and "Password2024" aren't.
- **Other kinds** are recognised by their text alone, in this order: links
  (`http(s)://`, `ftp://`, `smb://`, `www.`), email addresses, colors (`#rgb`,
  `#rrggbb`, `#rrggbbaa`, `rgb()`, `rgba()`), phone numbers (7 to 15 digits,
  with `+`, `tel:`, brackets or groups; dates aren't), and files and folders
  (a `file://` URI, or a path that exists). Anything else, or anything on
  several lines, is text.

### Passwords

Unless it is pinned, a password is deleted from the history about a second
after it is pasted (once the application has taken it), and taken off the
clipboard too if it's still there. Every 10 seconds, Xclipy forgets passwords older than the set time, and
deletes items older than the set number of days when that is on. A pinned
password is only kept beyond the session if "Save pinned passwords" is on (and
something is kept after logging out):
it is then stored in the keyring through libsecret (schema
`org.x.Xclipy.Password`, with a random id), and the history file only has that
id. Turning the option off deletes them from the keyring.

### Storage

- What is kept after logging out ("Keep after logging out": everything, the
  pinned items only, or nothing) is the only part written to disk:
  `~/.local/share/xclipy/history.json` (newest first, pinned items apart, each
  item with the time it was copied), written atomically and only when it
  changes, with the folder `0700` and the file `0600`. With the default, a copy
  never touches the disk; with nothing kept, there's no file at all.
- Images: PNG files named by a hash of the picture, so the same image is stored
  once; files no item uses are deleted. Kept ones are in
  `~/.local/share/xclipy/images/`, the others in the session's runtime folder
  (`$XDG_RUNTIME_DIR/xclipy/images/`, in memory and emptied at logout). An
  image moves between the two when it's pinned or unpinned.
- The settings, the recently used emoji and the skin tone: GSettings,
  `org.x.xclipy`.
- However much is copied, the history stays small: the number of recent items
  set (200 at most), a million characters of text and 16 megapixels of image
  each, and 64 MB for all the recent items together (the oldest go first;
  pinned items don't count). A program copying in a loop is read four times a
  second at most, the latest copy always; on Wayland the helper doesn't read
  copies over 16 MB.

### Opening and pasting

- Where an overlay opens is decided before it opens (`xclipy/placement.py`):
  at the mouse pointer, below it and to its right; above it when there is no
  room below, to its left when there is no room on the right (in the bottom
  right corner of the screen only without a pointer). In Cinnamon the helper
  decides, as the window manager: on Wayland only it knows the pointer. The
  overlay never moves after that: it can't be dragged or resized.
- Which application has the keyboard focus, and whether it's a terminal, comes
  from AT-SPI, the accessibility interface (`xclipy/focus.py`).
- Pasting puts the item on the clipboard and presses Ctrl+V with `xdotool`
  (X11; the helper on Wayland), or Ctrl+Shift+V when AT-SPI says the focused
  application is a terminal.
- The emoji come from Unicode's `emoji-test.txt` (`xclipy/emoji_data.py`) and
  are searched by their English names.

### Desktop integration

- The shortcuts are the desktop's own custom shortcuts, added the first time
  Xclipy runs there, and listed with its other shortcuts (Cinnamon's
  `org.cinnamon.desktop.keybindings`, MATE's `/org/mate/desktop/keybindings/`,
  Xfce's `xfce4-keyboard-shortcuts`). Removed there, they aren't added back. On
  other desktops, bind `xclipy --show` and `xclipy --emoji` yourself.
- The settings are one page (`xclipy/ui/settings_page.py`), shown in
  Cinnamon's System Settings by `cs_xclipy.py` (installed in
  `/usr/share/cinnamon/cinnamon-settings/modules`) and in a window of its own
  elsewhere.
- Xclipy writes to `.xsession-errors`.

### Wayland

Wayland only lets the application with the keyboard focus read the clipboard,
and no application can place its windows or press keys in other applications.
In Cinnamon, a helper extension installed with Xclipy (`xclipy@dimitrysaf`,
turned on the first time Xclipy runs there) does it for Xclipy over D-Bus
(`org.x.Xclipy.Cinnamon`, described in `xclipy/helper.py`). It says when
something is copied and reads it (for Xclipy only), tells which window has the
focus, and presses Ctrl+V. Right before an overlay opens, the helper says
where it goes, at the mouse pointer, and on which side of it; then it puts the
overlay there as Cinnamon shows it. Cinnamon places every new window itself,
so the overlay is kept invisible until it is in its place (a few frames), and
never seen anywhere else. The helper also keeps the overlays out of the window
list, and stops any attempt to move or resize them. Without it (turned off, or
on other Wayland desktops), Xclipy only keeps what is on the clipboard when the
overlay opens, which opens where the compositor puts it, choosing an item only
copies it, and applications can't be excluded. On X11 the helper only says
where the overlays go, and Xclipy opens them there itself.

## Building from source

### For Mint with mint-dev-tools

```bash
# Install mint-dev-tools
sudo apt install mint-dev-tools
# Remove any previous versions
sudo apt remove xclipy
# Build and install from github
mint-build -i -g https://github.com/Dimitrysaf/xclipy.git
```

### For Debian distributions (Mint, Ubuntu, etc.) with dpkg-buildpackage

```bash
# Get the source code..
git clone https://github.com/Dimitrysaf/xclipy.git
# Go in..
cd xclipy
# Install the build dependencies..
sudo apt build-dep --mark-auto .
# Remove any previously built packages
rm -f ../xclipy*.deb
# Build
dpkg-buildpackage -us -uc
# Install
sudo apt install ../xclipy*.deb
```

Log out and back in (or run `xclipy --background`), then press Super+V.

### For other distributions with meson

```bash
# Get the source code..
git clone https://github.com/Dimitrysaf/xclipy.git
# Go in..
cd xclipy
```

Install the build and runtime dependencies for your distribution. For example:

```bash
# Fedora: sudo dnf install meson ninja-build python3 gettext
# Arch: sudo pacman -S meson ninja python gettext
# openSUSE: sudo zypper install meson ninja python3 gettext-tools
```

The dependencies are listed below (using debian pkg names, names may be different in your distribution). Install all of them.

#### Dependencies for building

```text
gettext
gtk-update-icon-cache
libglib2.0-bin (for glib-compile-schemas)
meson
python3
```

#### Dependencies for runtime, also needed to run the tests (`meson test`)

```text
gir1.2-gtk-3.0
python3
python3-gi
```

#### Other dependencies for runtime

```text
gir1.2-atspi-2.0
gir1.2-secret-1
gir1.2-wnck-3.0
python3-xapp
xapps-common
xdotool
```

A D-Bus session bus is also required.

Optional:

```text
cinnamon (System Settings → Clipboard, and the helper extension)
fonts-noto-color-emoji (to show the emoji in color)
```

#### Build and install

```bash
meson setup build --prefix=/usr
meson compile -C build
meson test -C build  # optional
sudo meson install -C build
```

System Settings only reads its pages (and Cinnamon its extensions) from
`/usr`, so install with `--prefix=/usr`. With `/usr/local`, the login autostart entry is also
installed in a folder the system doesn't read.

#### Uninstall

To remove a Meson installation while retaining the build directory:

```bash
sudo ninja -C build uninstall
```

## Development

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -t .   # tests
python3 tools/preview.py                                  # the overlay on a sample history
xvfb-run -a python3 tools/preview.py --shots /tmp/shots   # headless screenshots
```

The emoji come from Unicode's `emoji-test.txt`. To update them:

```bash
curl -O https://unicode.org/Public/emoji/latest/emoji-test.txt
python3 tools/update_emoji.py emoji-test.txt
```

## Translations

Xclipy is in English, with a Greek translation. It follows the desktop's
language. Emoji are searched by their English names.

The translation template is `xclipy.pot` and the translations are in `po/`.
After changing interface text, regenerate the template and update the
translations:

```bash
./makepot
msgmerge --update po/el.po xclipy.pot
```

To add a language, create its file from the template, translate it, and add
its code to `po/LINGUAS`:

```bash
msginit --input=xclipy.pot --output=po/fr.po --locale=fr
```

The tests check that every language translates every message, and that the
template is up to date.

## License

Code: GPLv3 or later. See [LICENSES/GPL-3.0.txt](LICENSES/GPL-3.0.txt).
The emoji list is generated from Unicode data, under the
[Unicode License](https://www.unicode.org/license.txt).

## AI is used.
This project was made with Claude. UI is handmade. 