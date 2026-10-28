"""The clipboard history: pinned items, then the recent ones, newest first.

An item is either pinned or recent, never both. Pinned items stay until they
are unpinned or deleted: the size limit, "Clear all" and the automatic
clean-ups are for the recent ones (Clear history in the settings deletes
both).

The history is kept on disk, readable only by its user, with the images in a
folder next to it. Passwords ("secret" items) are only kept in memory; pinned
ones go to the keyring when the settings say so, and the history file keeps
their place (an id, not the password).
"""

import json
import os
import time

MAX_LENGTH = 1000000  # characters; longer copies (whole files, logs) aren't kept


class Item:
    """Copied text (maybe a password) or a copied image, a PNG file in the images folder."""

    __slots__ = ("text", "image", "secret", "time", "secret_id")

    def __init__(self, text=None, image=None, secret=False, copied=None, secret_id=None):
        self.text = text
        self.image = image
        self.secret = secret
        self.time = time.time() if copied is None else copied
        self.secret_id = secret_id  # where it is in the keyring, when it's saved there

    @property
    def key(self):
        """What makes two items the same."""
        return ("image", self.image) if self.image else ("text", self.text)

    def to_json(self):
        if self.image:
            data = {"image": self.image}
        elif self.secret_id:
            data = {"secret": self.secret_id}  # the password is in the keyring
        else:
            data = {"text": self.text}
        data["time"] = self.time
        return data

    @classmethod
    def from_json(cls, data):
        if isinstance(data, str):  # the first versions kept only text
            data = {"text": data}
        if not isinstance(data, dict):
            return None
        copied = data.get("time")
        copied = copied if isinstance(copied, (int, float)) else None
        if isinstance(data.get("image"), str) and os.sep not in data["image"]:
            return cls(image=data["image"], copied=copied)
        if isinstance(data.get("secret"), str):
            return cls(secret=True, copied=copied, secret_id=data["secret"])  # its text is in the keyring
        if isinstance(data.get("text"), str) and _worth_keeping(data["text"]):
            return cls(text=data["text"], copied=copied)
        return None


def _worth_keeping(text):
    return bool(text) and bool(text.strip()) and len(text) <= MAX_LENGTH


class ClipboardHistory:
    def __init__(self, path, size, session=None, keyring=None):
        """``session`` tells login sessions apart (see ``previous_session``).

        With a ``keyring``, pinned passwords are saved in it.
        """
        self._path = path
        self._keyring = keyring
        self.saved_passwords = False  # whether the file had some, from the keyring
        self.images_dir = os.path.join(os.path.dirname(path), "images")
        self._size = size
        self._session = session
        self._items = []
        self._pinned = []
        self.previous_session = None
        self.on_changed = lambda: None
        try:
            with open(self._path, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict):
            self.previous_session = loaded.get("session")
            self._pinned = self._load(loaded.get("pinned"), set())
            self._items = self._load(loaded.get("items"), {item.key for item in self._pinned})
            self._drop(self._items[size:])
            del self._items[size:]
        self._remove_unused_images()

    def _load(self, value, seen):
        items = []
        for data in value if isinstance(value, list) else []:
            item = Item.from_json(data)
            if item is not None and item.secret_id:
                self.saved_passwords = True
                item.text = self._keyring.load(item.secret_id) if self._keyring else None
                if not _worth_keeping(item.text):
                    continue
            if item is None or item.key in seen:
                continue
            if item.image and not os.path.isfile(self.image_path(item)):
                continue
            seen.add(item.key)
            items.append(item)
        return items

    def items(self):
        """The recent items, newest first."""
        return list(self._items)

    def pinned(self):
        return list(self._pinned)

    def is_pinned(self, item):
        return item in self._pinned

    def image_path(self, item):
        return os.path.join(self.images_dir, item.image)

    def add_text(self, text, secret=False):
        """Put text first; returns the item, or None when it isn't worth keeping."""
        if not _worth_keeping(text):
            return None
        return self._add(Item(text=text, secret=secret))

    def add_image(self, name):
        """Put an image first, already saved as ``name`` in the images folder."""
        return self._add(Item(image=name))

    def _add(self, item):
        for pinned in self._pinned:
            if pinned.key == item.key:
                return pinned
        old = next((i for i in self._items if i.key == item.key), None)
        if old is not None:
            # A password stays one, also when the same text comes back
            # without its mark (Cinnamon keeps the clipboard of a closed
            # application, and offers it again as plain text).
            item.secret = item.secret or old.secret
            if old is self._items[0]:
                return old
            self._items.remove(old)
        self._items.insert(0, item)
        self._drop(self._items[self._size:])
        del self._items[self._size:]
        self._changed()
        return item

    def use(self, item):
        """Move a recent item to the top, as when it's copied again."""
        if item in self._items and item is not self._items[0]:
            self._items.remove(item)
            self._items.insert(0, item)
            self._changed()

    def remove(self, item):
        for items in (self._pinned, self._items):
            if item in items:
                items.remove(item)
                self._drop([item])
                self._changed()
                return

    def clear(self):
        """Delete the recent items; the pinned ones stay."""
        self.remove_recent(lambda item: True)

    def clear_all(self):
        """Delete everything, the pinned items too."""
        if self._items or self._pinned:
            self._drop(self._items + self._pinned)
            self._items = []
            self._pinned = []
            self._changed()

    def remove_recent(self, unwanted):
        """Delete the recent items for which unwanted(item) is true; returns them."""
        gone = [item for item in self._items if unwanted(item)]
        if gone:
            self._items = [item for item in self._items if item not in gone]
            self._drop(gone)
            self._changed()
        return gone

    def remove_older(self, seconds, secret_only=False, now=None):
        """Delete the recent items (or passwords) copied more than ``seconds`` ago; returns them."""
        limit = (time.time() if now is None else now) - seconds
        return self.remove_recent(lambda item: item.time < limit and (item.secret or not secret_only))

    def has_text(self, text):
        return any(item.text == text for item in self._pinned + self._items)

    def pin(self, item):
        """Move an item to the top of the pinned ones."""
        if item in self._items:
            self._items.remove(item)
            self._pinned.insert(0, item)
            self._save_password(item)
            self._changed()

    def unpin(self, item):
        """Move a pinned item back to the top of the recent ones."""
        if item in self._pinned:
            self._pinned.remove(item)
            self._forget_password(item)
            self._items.insert(0, item)
            self._drop(self._items[self._size:])
            del self._items[self._size:]
            self._changed()

    def edit(self, item, new_text):
        """Change a text item in its place; returns False when new_text isn't worth keeping."""
        if item.image or not _worth_keeping(new_text):
            return False
        for items in (self._pinned, self._items):
            if item in items:
                break
        else:
            return False
        if new_text != item.text:
            for others in (self._pinned, self._items):
                for other in [o for o in others if o is not item and o.key == ("text", new_text)]:
                    others.remove(other)  # it's this item now
            item.text = new_text
            self._changed()
        return True

    def set_size(self, size):
        self._size = size
        if len(self._items) > size:
            self._drop(self._items[size:])
            del self._items[size:]
            self._changed()

    def keep_pinned_passwords(self, keyring):
        """Start (with a keyring) or stop (None) saving the pinned passwords."""
        if keyring is None:
            for item in self._pinned:
                self._forget_password(item)
            if self._keyring is not None:
                self._keyring.delete_all()
        self._keyring = keyring
        for item in self._pinned:
            self._save_password(item)
        self._changed()

    def _save_password(self, item):
        if item.secret and not item.secret_id and self._keyring is not None:
            secret_id = self._keyring.new_id()
            if self._keyring.save(secret_id, item.text):
                item.secret_id = secret_id

    def _forget_password(self, item):
        if item.secret_id and self._keyring is not None:
            self._keyring.delete(item.secret_id)
        item.secret_id = None

    def _drop(self, items):
        """Forget items for good: their images and saved passwords too."""
        for item in items:
            self._forget_password(item)
            if item.image:
                try:
                    os.remove(self.image_path(item))
                except OSError:
                    pass

    def _remove_unused_images(self):
        used = {item.image for item in self._pinned + self._items if item.image}
        try:
            names = os.listdir(self.images_dir)
        except OSError:
            return
        for name in names:
            if name not in used:
                try:
                    os.remove(os.path.join(self.images_dir, name))
                except OSError:
                    pass

    def _changed(self):
        self._save()
        self.on_changed()

    def _save(self):
        # What was copied can be private: only this user may read it.
        os.makedirs(os.path.dirname(self._path), mode=0o700, exist_ok=True)
        data = {
            "session": self._session,
            "pinned": [item.to_json() for item in self._pinned if not item.secret or item.secret_id],
            "items": [item.to_json() for item in self._items if not item.secret],
        }
        temporary = self._path + ".tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
        os.replace(temporary, self._path)

    def save(self):
        """Write the history now (e.g. to record this session)."""
        self._save()
