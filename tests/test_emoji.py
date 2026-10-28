"""Emoji groups, search and the recently used ones."""

import unittest

from xclipy import emoji
from xclipy.emoji_data import EMOJI, GROUPS


class EmojiTests(unittest.TestCase):
    def test_groups(self):
        self.assertEqual(len(GROUPS), len(emoji.GROUP_NAMES))
        self.assertEqual(emoji.group_name(0), "Smileys & Emotion")
        self.assertEqual(emoji.group_symbol(0), "😀")
        self.assertTrue(all(emoji.in_group(index) for index in range(len(GROUPS))))
        self.assertEqual(sum(len(emoji.in_group(i)) for i in range(len(GROUPS))), len(EMOJI))

    def test_skin_tones_apart(self):
        tones = {chr(c) for c in range(0x1F3FB, 0x1F400)}
        self.assertFalse([text for _g, text, _n in EMOJI if tones.intersection(text)])
        self.assertEqual(emoji.with_tone("👋", "medium"), "👋🏽")
        self.assertEqual(emoji.with_tone("👋", "none"), "👋")
        self.assertEqual(emoji.with_tone("😀", "dark"), "😀")  # no skin to tone
        self.assertEqual(emoji.with_tone("👨‍🏫", "light"), "👨🏻‍🏫")
        self.assertEqual(emoji.name_of("👍🏿"), "thumbs up")

    def test_search_needs_every_word(self):
        found = dict(emoji.search("Heart RED"))
        self.assertIn("❤️", found)
        self.assertTrue(all("red" in name and "heart" in name for name in found.values()))
        self.assertEqual(emoji.search("   "), [])
        # The start of words only: "cat" isn't in "identification card".
        self.assertNotIn("🪪", dict(emoji.search("cat")))
        self.assertIn("🐈", dict(emoji.search("ca")))
        self.assertEqual(emoji.search("no such emoji"), [])

    def test_names(self):
        self.assertEqual(emoji.name_of("😀"), "grinning face")
        self.assertEqual(emoji.name_of("x"), "")

    def test_recently_used(self):
        recent = []
        for text in ("😀", "🐶", "😀"):
            recent = emoji.remember(recent, text)
        self.assertEqual(recent, ["😀", "🐶"])
        for index in range(emoji.RECENT_SIZE + 5):
            recent = emoji.remember(recent, str(index))
        self.assertEqual(len(recent), emoji.RECENT_SIZE)


if __name__ == "__main__":
    unittest.main()
