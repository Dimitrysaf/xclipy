# Xclipy

Clipboard history for the Cinnamon, MATE and Xfce desktops.

<img width="800" height="600" alt="Xclipy's clipboard history under the text cursor, with a copy from a phone and an item's menu open" src="screenshots/clipboard.png" />

<img width="800" height="600" alt="Xclipy's emoji picker" src="screenshots/emoji.png" />

<img width="800" height="420" alt="Xclipy's page in System Settings" src="screenshots/settings.png" />

## Features

- Keeps what you copy: newest first, without duplicates, also after a restart.
  Copied images too, if you want, showing their top part.
- Links, email addresses, phone numbers, files and folders get an icon, and
  colors (#3a7bd5, rgb(...)) a swatch of the color (Show item types, in the
  settings).
- Super+V opens it, and Super+. opens it on the Emojis tab, without a window
  bar or a tray icon: under the text cursor, or in the bottom right corner of
  the screen when there's no text cursor. The Emojis tab can be turned off
  (Show emojis, in the settings).
- Choosing an item pastes it into the application you were typing in
  (terminals included, with Ctrl+Shift+V).
- A search bar (Show search bar, in the settings) searches the items, and its
  menu shows only one kind of item: text, links, email addresses, phone
  numbers, files and folders, colors, passwords, images or what was copied on a
  phone (only images without Show item types). The menu only offers the kinds
  there are.
- With [Satellite](https://github.com/Dimitrysaf/satellite), what is copied on
  a phone shows the phone's name, and each item's menu can send it to a
  connected phone (Send to ...).
- Each item has a menu to Edit, Delete, Pin or Paste it. Pinned items stay on
  top, in Pinned, and are kept by "Clear all" and by the size limit (Clear
  history in the settings deletes them too). Editing happens in the overlay,
  with Save and Cancel, without the tabs.
- An Emojis tab with search, the emoji groups and the recently used ones.
- Passwords show as ••••••••, are deleted once pasted and forgotten after a
  minute, and are never saved to disk; pinned ones can be saved in the keyring
  (Passwords and Keys) instead. They are recognised when the password
  manager marks them as secret (KeePassXC, KWallet, ...), and by how random
  they look: one word mixing lowercase, uppercase, digits and symbols, with no
  word-like parts ("xK9#mQ2$vL", API keys; not "user_name_2" or
  "Password2024").
- Its settings are in System Settings → Clipboard on Cinnamon, and in the
  Clipboard settings application (in the Control Center, the Settings Manager
  or `xclipy --settings`) elsewhere: turning the history on and off, the
  shortcuts, how many items to keep, clearing them when logging out, deleting
  old ones, images, passwords, applications whose copies are never kept, and
  the Emojis tab and its skin tone.

The overlay works with the keyboard: arrows to move, Enter to choose, the Menu
key (or Shift+F10) for an item's menu, Escape to close, Ctrl+Tab to switch
tabs. While editing, Ctrl+Enter saves and Escape cancels. With the search bar,
typing searches, Down goes back to the list and Escape clears the search. In
the Emojis tab, just type to search.

## Architecture

`xclipy` is the application. It runs from login, without a window
(`xclipy --background`), and watches the clipboard. The keyboard shortcuts run
`xclipy --show` and `xclipy --emoji`, which open or close the overlay of the
running Xclipy (or start it), on the Clipboard or the Emojis tab.

- The shortcuts are the desktop's own custom shortcuts, added the first time
  Xclipy runs on it. The desktop runs them whatever has the keyboard focus, and
  lists them with its other shortcuts: Keyboard → Shortcuts → Custom Shortcuts
  in Cinnamon, Keyboard Shortcuts in MATE, Keyboard → Application Shortcuts in
  Xfce. If one is removed there, Xclipy doesn't add it back. On other desktops,
  bind `xclipy --show` and `xclipy --emoji` to keys yourself.
- The text cursor's position is asked through AT-SPI, the accessibility
  interface. GTK applications (Text Editor, terminals, ...) give it; the
  overlay opens in the bottom right corner for applications that don't.
- Pasting presses Ctrl+V with `xdotool` (X11; the helper on Wayland).
- Excluded applications are recognised by the window that has the focus when
  something is copied (libwnck on X11; the helper on Wayland).
- When an application quits, Cinnamon and MATE keep what it had copied on the
  clipboard, as plain text. A password copied before stays a password, and a
  forgotten one isn't kept again.
- The page in System Settings is `cs_xclipy.py`, installed with Cinnamon's own
  modules in `/usr/share/cinnamon/cinnamon-settings/modules`. It is the same
  page as the settings window's (`xclipy/ui/settings_page.py`).
- Copies from phones: Satellite puts a phone's copy on the clipboard and says
  so on D-Bus (`org.x.Satellite.Phone`, `ClipboardReceived`, with the text's
  SHA-256, never the text). Xclipy never starts Satellite.
- In Cinnamon, a helper extension (`xclipy@dimitrysaf`, installed with Xclipy
  and turned on the first time Xclipy runs there) does on Wayland what an
  application can't do there itself. See below.

Xclipy:

- is started at login via XDG autostart (`xclipy --background`, in Cinnamon,
  MATE and Xfce), and by D-Bus activation (`org.x.Xclipy`) when a shortcut or
  the settings need it.
- writes to `.xsession-errors`.
- stores the history, pinned items included, in
  `~/.local/share/xclipy/history.json` and its images in
  `~/.local/share/xclipy/images/`, readable only by you. Passwords stay in
  memory, or, pinned, in the keyring through libsecret when the settings say
  so: the history file then only has an id where they go, not the password.
- clears the recent items at the next login when the session ended without
  logging out (a crash, a power cut), as it does when logging out.
- stores its settings in GSettings (`org.x.xclipy`).

### Wayland

Xclipy is made for X11 sessions, Linux Mint's default. Wayland only lets the
application with the keyboard focus read the clipboard, and no application can
place its windows or press keys in other applications. In Cinnamon's Wayland
session, the helper extension does it for Xclipy, on D-Bus
(`org.x.Xclipy.Cinnamon`, described in `xclipy/helper.py`): it says when
something is copied and reads it for Xclipy only, tells where the focused
window is, places the overlay, keeps it out of the window list, and presses
Ctrl+V. If the helper is turned off (System Settings → Extensions), Xclipy
only keeps what is on the clipboard when the overlay opens, the overlay opens
where the compositor puts it, choosing an item only copies it, and no
application can be excluded (the settings don't show Excluded applications
then). Other Wayland desktops have the same limits.

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
satellite (copies from phones, and sending items to them)
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
