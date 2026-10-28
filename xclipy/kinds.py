"""What kind of text was copied: a link, an email address, a password...

The kind gives an item its icon in the list. Text that looks random enough
(like what password managers generate) is taken for a password.
"""

import os
import re

LINK = "link"
EMAIL = "email"
PHONE = "phone"
PATH = "path"
COLOR = "color"
# The kinds of history items, for the search filters.
TEXT = "text"
PASSWORD = "password"
IMAGE = "image"
FILTERS = (TEXT, LINK, EMAIL, PHONE, PATH, COLOR, PASSWORD, IMAGE)

ICONS = {
    LINK: "web-browser-symbolic",
    EMAIL: "mail-unread-symbolic",
    PHONE: "call-start-symbolic",
    PATH: "folder-symbolic",
}

_LINK = re.compile(r"^(?:(?:https?|ftp|sftp|smb)://|www\.)\S+$", re.IGNORECASE)
_EMAIL = re.compile(r"^(?:mailto:)?[^@\s/]+@[^@\s/]+\.[a-z]{2,}$", re.IGNORECASE)
# A phone number starts with tel:, + or ( or has its digits in groups.
_PHONE = re.compile(r"^(?:tel:\+?|\+|\()?[0-9]+(?:[ ()-]+[0-9]+)*$", re.IGNORECASE)
_DATE = re.compile(r"^(?:[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})$")
_PATH = re.compile(r"^(?:file://|~/|/)[^\n\0]*$")
_COLOR = re.compile(r"^(?:#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})|rgba?\([0-9 .,%]+\))$", re.IGNORECASE)

# Random-looking, yet not a password.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_HEX = re.compile(r"^(?:0x)?(?:[0-9a-f]+|[0-9A-F]+)$")  # hashes, commit ids, addresses
_DATE_OR_NUMBER = re.compile(r"^[0-9 ./:,+-]+$")


def kind_of(text):
    """LINK, EMAIL, PHONE, PATH, COLOR or None (just text)."""
    text = text.strip()
    if "\n" in text or len(text) > 2000:
        return None
    if _LINK.match(text):
        return LINK
    if _EMAIL.match(text):
        return EMAIL
    if _COLOR.match(text):
        return COLOR
    if _is_phone(text):
        return PHONE
    if _PATH.match(text) and (text.startswith("file://") or os.path.exists(os.path.expanduser(text))):
        return PATH
    return None


def item_kind(item):
    """The kind of a history item: one of FILTERS."""
    if item.image:
        return IMAGE
    if item.secret:
        return PASSWORD
    return kind_of(item.text) or TEXT


def filter_options(present, show_types):
    """The kinds to offer as filters, for items of the ``present`` kinds.

    Only images without the item types. None when no filter would narrow the
    list: every item is of the same kind, or no kind can be offered.
    """
    options = [kind for kind in FILTERS if kind in present and (show_types or kind == IMAGE)]
    return options if len(present) >= 2 else []


def _is_phone(text):
    if not _PHONE.match(text) or _DATE.match(text) or not 7 <= sum(c.isdigit() for c in text) <= 15:
        return False
    return text[0] in "+(" or text.lower().startswith("tel:") or not text.isdigit()


def _char_class(char):
    if char.islower():
        return 0
    if char.isupper():
        return 1
    if char.isdigit():
        return 2
    return 3


def looks_random(text):
    """Whether text looks like a generated password or key.

    One word of 8 to 128 characters, mixing at least three of lowercase,
    uppercase, digits and symbols, switching between them often and seldom
    keeping one for three characters or more (as words do): "xK9#mQ2$vL" is
    random, "html5Parser", "Password2024", "user_name_2" and "foo.bar(3)"
    aren't. Links, email addresses, paths, numbers, UUIDs and hashes are never
    passwords.
    """
    if not 8 <= len(text) <= 128 or any(c.isspace() for c in text):
        return False
    if kind_of(text) is not None or _UUID.match(text) or _HEX.match(text) or _DATE_OR_NUMBER.match(text):
        return False
    classes = [_char_class(c) for c in text]
    if len(set(classes)) < 3:
        return False
    switches = sum(1 for a, b in zip(classes, classes[1:]) if a != b)
    if switches / (len(text) - 1) < 0.4:
        return False
    in_long_runs = sum(len(run) for run in _runs(classes) if len(run) >= 3)
    return in_long_runs / len(text) < 0.5


def _runs(classes):
    runs, run = [], [classes[0]]
    for value in classes[1:]:
        if value == run[-1]:
            run.append(value)
        else:
            runs.append(run)
            run = [value]
    runs.append(run)
    return runs
