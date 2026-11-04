"""The clipboard history: pinned items, then the recent ones, newest first.

An item is either pinned or recent, never both. Pinned items stay until they
are unpinned or deleted: the size limits, "Clear all" and the automatic
clean-ups are for the recent ones (Clear history in the settings deletes
both).

What is kept after logging out is written to disk, readable only by its user,
with its images in a folder next to it: everything, the pinned items only (the
default), or nothing. The rest is kept in memory, with its images in the
session's runtime folder (in memory too, and emptied at logout). Passwords
("secret" items) are only kept in memory; pinned ones go to the keyring when
the settings say so, and the history file keeps their place (an id, not the
password).

However much is copied, the history stays small: a number of recent items (as
set), MAX_LENGTH characters of text each, and MAX_RECENT_BYTES for all of them.
"""

import json
import os
import shutil
import time

# What is kept after logging out (the "keep-after-logout" setting).
KEEP_EVERYTHING = "everything"
KEEP_PINNED = "pinned"
KEEP_NOTHING = "nothing"
MAX_LENGTH = 1000000  # characters; longer copies (whole files, logs) aren't kept
MAX_RECENT_BYTES = 64 * 1024 * 1024  # all the recent items together; the oldest go first


class Item:
    """Copied text (maybe a password) or a copied image, a PNG file in an images folder."""

    __slots__ = ("text", "image", "secret", "time", "secret_id", "size")

    def __init__(self, text=None, image=None, secret=False, copied=None, secret_id=None):
        self.text = text
        self.image = image
        self.secret = secret
        self.time = time.time() if copied is None else copied
        self.secret_id = secret_id  # where it is in the keyring, when it's saved there
        self.size = len(text.encode("utf-8", "replace")) if text else 0  # bytes; an image's are its file's

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
    def __init__(self, path, size, keyring=None, keep=KEEP_PINNED, memory_dir=None):
        """The history saved in the file ``path``, ``size`` recent items at most.

        ``keep`` is what is kept after logging out (KEEP_EVERYTHING,
        KEEP_PINNED or KEEP_NOTHING): only that is written to disk. The images
        of the rest go to ``memory_dir``. With a ``keyring``, pinned passwords
        are saved in it.
        """
        self._path = path
        self._keyring = keyring
        self._keep = keep
        self.saved_passwords = False  # whether the file had some, from the keyring
        self.images_dir = os.path.join(os.path.dirname(path), "images")
        self.memory_dir = memory_dir or os.path.join(os.path.dirname(path), "unsaved")
        self._size = size
        self._items = []
        self._pinned = []
        self._written = None  # what the file has, to only write it when that changes
        self.on_changed = lambda: None
        try:
            with open(self._path, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict) and keep != KEEP_NOTHING:
            self._pinned = self._load(loaded.get("pinned"), set())
            if keep == KEEP_EVERYTHING:
                self._items = self._load(loaded.get("items"), {item.key for item in self._pinned})
                self._trim()
        self._remove_unused_images()
        self._save()  # without what isn't kept any more

    def _load(self, value, seen):
        items = []
        for data in value if isinstance(value, list) else []:
            item = Item.from_json(data)
            if item is not None and item.secret_id:
                self.saved_passwords = True
                item.text = self._keyring.load(item.secret_id) if self._keyring else None
                if not _worth_keeping(item.text):
                    continue
                item.size = len(item.text.encode("utf-8", "replace"))
            if item is None or item.key in seen:
                continue
            if item.image:
                path = os.path.join(self.images_dir, item.image)
                if not os.path.isfile(path):
                    continue
                item.size = os.path.getsize(path)
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

    def _kept(self, item):
        """Whether an item is kept after logging out: written to disk."""
        return self._keep == KEEP_EVERYTHING or (self._keep == KEEP_PINNED and item in self._pinned)

    def image_path(self, item):
        return os.path.join(self.images_dir if self._kept(item) else self.memory_dir, item.image)

    def new_image_path(self, name):
        """Where an image copied now goes, before ``add_image(name)``."""
        return os.path.join(self.images_dir if self._keep == KEEP_EVERYTHING else self.memory_dir, name)

    def add_text(self, text, secret=False):
        """Put text first; returns the item, or None when it isn't worth keeping."""
        if not _worth_keeping(text):
            return None
        return self._add(Item(text=text, secret=secret))

    def add_image(self, name):
        """Put an image first, already saved at ``new_image_path(name)``."""
        item = Item(image=name)
        try:
            item.size = os.path.getsize(self.new_image_path(name))
        except OSError:
            return None
        return self._add(item)

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
        self._trim()
        self._changed()
        return item

    def _trim(self):
        """Drop the oldest recent items beyond the number set and the size limit.

        The newest always stays: it's at most MAX_LENGTH characters, or an image
        of a limited size.
        """
        total = 0
        for index, item in enumerate(self._items[:self._size]):
            total += item.size
            if total > MAX_RECENT_BYTES and index > 0:
                break
        else:
            index = min(len(self._items), self._size)
        self._drop(self._items[index:])
        del self._items[index:]

    def use(self, item):
        """Move a recent item to the top, as when it's copied again."""
        if item in self._items and item is not self._items[0]:
            self._items.remove(item)
            self._items.insert(0, item)
            self._changed()

    def remove(self, item):
        for items in (self._pinned, self._items):
            if item in items:
                self._drop([item])
                items.remove(item)
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
            self._drop(gone)
            self._items = [item for item in self._items if item not in gone]
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
            kept = self._kept(item)
            self._items.remove(item)
            self._pinned.insert(0, item)
            self._move_image(item, kept)
            self._save_password(item)
            self._changed()

    def unpin(self, item):
        """Move a pinned item back to the top of the recent ones."""
        if item in self._pinned:
            kept = self._kept(item)
            self._pinned.remove(item)
            self._forget_password(item)
            self._items.insert(0, item)
            self._move_image(item, kept)
            self._trim()
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
            item.size = len(new_text.encode("utf-8", "replace"))
            self._trim()
            self._changed()
        return True

    def set_size(self, size):
        self._size = size
        if len(self._items) > size:
            self._trim()
            self._changed()

    def set_keep(self, keep):
        """Keep more or less after logging out: the file and the images follow."""
        kept = {id(item): self._kept(item) for item in self._pinned + self._items}
        self._keep = keep
        for item in self._pinned + self._items:
            self._move_image(item, kept[id(item)])
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

    def _move_image(self, item, was_kept):
        """An item's image goes to disk, or into memory, when it starts or stops being kept."""
        if not item.image or was_kept == self._kept(item):
            return
        source = os.path.join(self.images_dir if was_kept else self.memory_dir, item.image)
        target = self.image_path(item)
        try:
            os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
            shutil.move(source, target)  # across file systems too: memory_dir is in memory
        except OSError:
            pass

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
        for folder, kept in ((self.images_dir, True), (self.memory_dir, False)):
            used = {item.image for item in self._pinned + self._items if item.image and self._kept(item) == kept}
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                if name not in used:
                    try:
                        os.remove(os.path.join(folder, name))
                    except OSError:
                        pass

    def _changed(self):
        self._save()
        self.on_changed()

    def _save(self):
        """Write what is kept after logging out, when it changed; with nothing kept, no file."""
        if self._keep == KEEP_NOTHING:
            if self._written != "":
                for path in [self._path] + [os.path.join(self.images_dir, n) for n in _listdir(self.images_dir)]:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                self._written = ""
            return
        data = {
            "pinned": [item.to_json() for item in self._pinned if not item.secret or item.secret_id],
            "items": [item.to_json() for item in self._items if not item.secret]
            if self._keep == KEEP_EVERYTHING else [],
        }
        text = json.dumps(data, ensure_ascii=False)
        if text == self._written:
            return  # e.g. a recent item copied, while only the pinned ones are kept
        # What was copied can be private: only this user may read it.
        os.makedirs(os.path.dirname(self._path), mode=0o700, exist_ok=True)
        temporary = self._path + ".tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, self._path)
        self._written = text


def _listdir(folder):
    try:
        return os.listdir(folder)
    except OSError:
        return []
