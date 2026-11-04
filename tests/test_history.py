"""The clipboard history: order, pins, clean-ups, passwords, images and its file."""

import json
import os
import stat
import tempfile
import unittest

from unittest import mock

from xclipy.history import KEEP_EVERYTHING, KEEP_NOTHING, KEEP_PINNED, MAX_LENGTH, ClipboardHistory


class FakeKeyring:
    def __init__(self):
        self.saved = {}
        self.count = 0

    def new_id(self):
        self.count += 1
        return "id{}".format(self.count)

    def save(self, password_id, password):
        self.saved[password_id] = password
        return True

    def load(self, password_id):
        return self.saved.get(password_id)

    def delete(self, password_id):
        self.saved.pop(password_id, None)

    def delete_all(self):
        self.saved.clear()


def texts(items):
    return [item.text if item.text is not None else item.image for item in items]


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "xclipy", "history.json")

    def tearDown(self):
        self.folder.cleanup()

    def history(self, size=10):
        # Everything kept after logging out: the recent items are on disk too.
        return ClipboardHistory(self.path, size, keep=KEEP_EVERYTHING)

    def test_newest_first_without_duplicates(self):
        history = self.history()
        for text in ("one", "two", "one", "three"):
            history.add_text(text)
        self.assertEqual(texts(history.items()), ["three", "one", "two"])

    def test_keeps_only_the_newest(self):
        history = self.history(2)
        for text in ("one", "two", "three"):
            history.add_text(text)
        self.assertEqual(texts(history.items()), ["three", "two"])
        history.set_size(1)
        self.assertEqual(texts(history.items()), ["three"])

    def test_skips_blank_and_huge_text(self):
        history = self.history()
        self.assertIsNone(history.add_text(""))
        self.assertIsNone(history.add_text(" \n\t"))
        self.assertIsNone(history.add_text("x" * (MAX_LENGTH + 1)))
        self.assertEqual(history.items(), [])

    def test_use_moves_an_item_to_the_top(self):
        history = self.history()
        one = history.add_text("one")
        history.add_text("two")
        history.use(one)
        self.assertEqual(texts(history.items()), ["one", "two"])

    def test_remove_and_clear(self):
        history = self.history()
        one = history.add_text("one")
        history.add_text("two")
        history.remove(one)
        self.assertEqual(texts(history.items()), ["two"])
        history.clear()
        self.assertEqual(history.items(), [])

    def test_kept_privately_across_restarts(self):
        history = self.history()
        history.add_text("Γειά σου")
        history.add_text("two")
        self.assertEqual(texts(self.history().items()), ["two", "Γειά σου"])
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(self.path)).st_mode), 0o700)

    def test_a_broken_file_starts_empty(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as stream:
            stream.write("{not json")
        self.assertEqual(self.history().items(), [])
        with open(self.path, "w") as stream:
            json.dump({"items": ["ok", 3, None, {"text": "new", "time": 5}]}, stream)
        self.assertEqual(texts(self.history().items()), ["ok", "new"])

    def test_tells_when_it_changes(self):
        history = self.history()
        changes = []
        history.on_changed = lambda: changes.append(texts(history.items()))
        one = history.add_text("one")
        history.add_text("one")  # already first: nothing changes
        history.clear()
        history.remove(one)  # already gone
        self.assertEqual(changes, [["one"], []])


class PinTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "history.json")

    def tearDown(self):
        self.folder.cleanup()

    def test_pinned_items_stay_on_top_and_are_kept(self):
        history = ClipboardHistory(self.path, 2, keep=KEEP_EVERYTHING)
        items = {text: history.add_text(text) for text in ("one", "two", "three")}
        history.pin(items["two"])
        history.pin(items["three"])
        self.assertEqual(texts(history.pinned()), ["three", "two"])
        self.assertEqual(history.items(), [])
        for text in ("four", "five", "six", "three"):
            history.add_text(text)  # copying a pinned item again leaves it pinned
        self.assertEqual(texts(history.pinned()), ["three", "two"])
        self.assertEqual(texts(history.items()), ["six", "five"])
        history.clear()
        self.assertEqual(texts(history.pinned()), ["three", "two"])
        self.assertEqual(texts(ClipboardHistory(self.path, 2, keep=KEEP_EVERYTHING).pinned()), ["three", "two"])

    def test_clear_all_deletes_the_pinned_items_too(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        history.pin(history.add_text("one"))
        history.add_text("two")
        history.clear_all()
        self.assertEqual((history.pinned(), history.items()), ([], []))

    def test_unpin_goes_back_to_the_top(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        one = history.add_text("one")
        history.add_text("two")
        history.pin(one)
        self.assertTrue(history.is_pinned(one))
        history.unpin(one)
        self.assertFalse(history.is_pinned(one))
        self.assertEqual(texts(history.items()), ["one", "two"])

    def test_edit_in_place(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        items = {text: history.add_text(text) for text in ("one", "two", "three")}
        history.pin(items["one"])
        self.assertTrue(history.edit(items["two"], "TWO"))
        self.assertTrue(history.edit(items["one"], "ONE"))
        self.assertEqual(texts(history.items()), ["three", "TWO"])
        self.assertEqual(texts(history.pinned()), ["ONE"])
        self.assertFalse(history.edit(items["two"], "  "))
        # Edited into another item: they become one.
        self.assertTrue(history.edit(items["two"], "three"))
        self.assertEqual(texts(history.items()), ["three"])

    def test_pinned_and_recent_never_overlap_on_disk(self):
        with open(self.path, "w") as stream:
            json.dump({"pinned": ["a", "a"], "items": ["a", "b"]}, stream)
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        self.assertEqual((texts(history.pinned()), texts(history.items())), (["a"], ["b"]))


class CleanUpTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "history.json")

    def tearDown(self):
        self.folder.cleanup()

    def test_old_recent_items_go_pinned_ones_stay(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        old = history.add_text("old")
        old.time = 1000
        pinned = history.add_text("pinned")
        pinned.time = 1000
        history.pin(pinned)
        new = history.add_text("new")
        new.time = 5000
        history.remove_older(3000, now=5000)
        self.assertEqual(texts(history.items()), ["new"])
        self.assertEqual(texts(history.pinned()), ["pinned"])

    def test_forgetting_passwords_leaves_other_text(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        for text, secret in (("text", False), ("hunter2", True)):
            history.add_text(text, secret).time = 0
        history.remove_older(60, secret_only=True, now=120)
        self.assertEqual(texts(history.items()), ["text"])

    def test_a_password_stays_one(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        password = history.add_text("hunter2", secret=True)
        # The same text again without the mark (Cinnamon keeps a closed application's clipboard).
        self.assertIs(history.add_text("hunter2"), password)
        self.assertTrue(password.secret)
        history.add_text("other")
        self.assertTrue(history.add_text("hunter2").secret)
        self.assertTrue(history.has_text("hunter2"))

    def test_removals_tell_what_went(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        history.add_text("hunter2", secret=True).time = 0
        self.assertEqual(texts(history.remove_older(60, secret_only=True, now=120)), ["hunter2"])
        self.assertFalse(history.has_text("hunter2"))

    def test_passwords_are_never_written_to_disk(self):
        history = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        history.pin(history.add_text("pinned secret", secret=True))
        history.add_text("hunter2", secret=True)
        history.add_text("plain")
        with open(self.path) as stream:
            saved = stream.read()
        self.assertNotIn("hunter2", saved)
        self.assertNotIn("pinned secret", saved)
        self.assertEqual(texts(ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING).items()), ["plain"])

    def test_pinned_passwords_in_the_keyring(self):
        keyring = FakeKeyring()
        history = ClipboardHistory(self.path, 10, keyring=keyring, keep=KEEP_EVERYTHING)
        history.add_text("plain")
        password = history.add_text("hunter2", secret=True)
        history.pin(password)
        self.assertEqual(list(keyring.saved.values()), ["hunter2"])
        with open(self.path) as stream:
            self.assertNotIn("hunter2", stream.read())
        # Back after a restart, in its place.
        again = ClipboardHistory(self.path, 10, keyring=keyring, keep=KEEP_EVERYTHING)
        self.assertEqual(texts(again.pinned()), ["hunter2"])
        self.assertTrue(again.pinned()[0].secret)
        # Unpinned or deleted, it leaves the keyring.
        again.unpin(again.pinned()[0])
        self.assertEqual(keyring.saved, {})

    def test_turning_the_keyring_off_and_on(self):
        keyring = FakeKeyring()
        history = ClipboardHistory(self.path, 10, keyring=keyring, keep=KEEP_EVERYTHING)
        history.pin(history.add_text("hunter2", secret=True))
        history.keep_pinned_passwords(None)
        self.assertEqual(keyring.saved, {})
        self.assertEqual(texts(history.pinned()), ["hunter2"])  # still there until a restart
        reloaded = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        self.assertEqual(reloaded.pinned(), [])
        history.keep_pinned_passwords(keyring)
        self.assertEqual(list(keyring.saved.values()), ["hunter2"])
        history.clear_all()
        self.assertEqual(keyring.saved, {})

    def test_without_the_keyring_the_saved_ones_are_left_out(self):
        keyring = FakeKeyring()
        history = ClipboardHistory(self.path, 10, keyring=keyring, keep=KEEP_EVERYTHING)
        history.pin(history.add_text("hunter2", secret=True))
        without = ClipboardHistory(self.path, 10, keep=KEEP_EVERYTHING)
        self.assertEqual(without.pinned(), [])
        self.assertTrue(without.saved_passwords)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "history.json")
        self.history = ClipboardHistory(self.path, 2, keep=KEEP_EVERYTHING)
        os.makedirs(self.history.images_dir)

    def tearDown(self):
        self.folder.cleanup()

    def image(self, name):
        with open(os.path.join(self.history.images_dir, name), "wb") as stream:
            stream.write(b"png")
        return self.history.add_image(name)

    def files(self):
        return sorted(os.listdir(self.history.images_dir))

    def test_images_files_go_with_their_items(self):
        a = self.image("a.png")
        self.image("b.png")
        self.image("c.png")  # a falls off the end of the history
        self.assertEqual(self.files(), ["b.png", "c.png"])
        self.assertEqual(texts(ClipboardHistory(self.path, 2, keep=KEEP_EVERYTHING).items()), ["c.png", "b.png"])
        self.history.remove(self.history.items()[0])
        self.assertEqual(self.files(), ["b.png"])
        self.history.clear_all()
        self.assertEqual(self.files(), [])
        self.assertIsNotNone(a)

    def test_the_same_image_once(self):
        self.image("a.png")
        self.image("a.png")
        self.assertEqual(len(self.history.items()), 1)

    def test_unused_and_missing_files_are_tidied(self):
        self.image("a.png")
        with open(os.path.join(self.history.images_dir, "stray.png"), "wb") as stream:
            stream.write(b"png")
        with open(self.path) as stream:
            data = json.load(stream)
        data["items"].append({"image": "missing.png"})
        with open(self.path, "w") as stream:
            json.dump(data, stream)
        reloaded = ClipboardHistory(self.path, 2, keep=KEEP_EVERYTHING)
        self.assertEqual(texts(reloaded.items()), ["a.png"])
        self.assertEqual(self.files(), ["a.png"])


class KeepAfterLogoutTests(unittest.TestCase):
    """Only what is kept after logging out goes to disk; the rest stays in memory."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "data", "history.json")
        self.memory = os.path.join(self.folder.name, "run", "images")

    def tearDown(self):
        self.folder.cleanup()

    def history(self, keep=KEEP_PINNED, size=10):
        return ClipboardHistory(self.path, size, keep=keep, memory_dir=self.memory)

    def saved(self):
        with open(self.path, encoding="utf-8") as stream:
            return json.load(stream)

    def image(self, history, name):
        path = history.new_image_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"png")
        return history.add_image(name)

    def test_only_the_pinned_items_by_default(self):
        history = self.history()
        history.pin(history.add_text("pinned"))
        history.add_text("recent")
        self.assertEqual(self.saved(), {"pinned": [history.pinned()[0].to_json()], "items": []})
        again = self.history()
        self.assertEqual((texts(again.pinned()), again.items()), (["pinned"], []))

    def test_recent_copies_never_touch_the_disk(self):
        history = self.history()
        os.remove(self.path)
        for text in ("one", "two", "three"):
            history.add_text(text)
        self.assertFalse(os.path.exists(self.path))

    def test_images_in_memory_until_pinned(self):
        history = self.history()
        item = self.image(history, "a.png")
        self.assertEqual(os.listdir(self.memory), ["a.png"])
        history.pin(item)
        self.assertEqual((os.listdir(self.memory), os.listdir(history.images_dir)), ([], ["a.png"]))
        history.unpin(item)
        self.assertEqual((os.listdir(self.memory), os.listdir(history.images_dir)), (["a.png"], []))

    def test_nothing_on_disk(self):
        history = self.history()
        history.pin(self.image(history, "a.png"))
        history.pin(history.add_text("pinned"))
        history.set_keep(KEEP_NOTHING)
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(os.listdir(history.images_dir), [])
        self.assertEqual(os.listdir(self.memory), ["a.png"])
        self.assertEqual(texts(history.pinned()), ["pinned", "a.png"])  # until logging out
        history.add_text("recent")
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(self.history(KEEP_NOTHING).pinned(), [])

    def test_everything_from_memory_to_disk(self):
        history = self.history(KEEP_NOTHING)
        self.image(history, "a.png")
        history.add_text("recent")
        history.set_keep(KEEP_EVERYTHING)
        self.assertEqual(texts(self.history(KEEP_EVERYTHING).items()), ["recent", "a.png"])
        self.assertEqual(os.listdir(history.images_dir), ["a.png"])

    def test_the_recent_items_have_a_size_limit(self):
        history = self.history()
        with mock.patch("xclipy.history.MAX_RECENT_BYTES", 10):
            history.pin(history.add_text("pinned items don't count"))
            history.add_text("aaaa")
            history.add_text("bbbb")
            self.assertEqual(texts(history.items()), ["bbbb", "aaaa"])
            history.add_text("cccc")  # 12 bytes with the two before: the oldest goes
            self.assertEqual(texts(history.items()), ["cccc", "bbbb"])
            history.add_text("a copy bigger than the limit on its own")
            self.assertEqual(texts(history.items()), ["a copy bigger than the limit on its own"])


if __name__ == "__main__":
    unittest.main()
