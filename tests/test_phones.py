"""Copies from phones, as Satellite announces them."""

import unittest

from xclipy.phones import MATCH_SECONDS, PhoneCopies, digest


class PhoneCopiesTests(unittest.TestCase):
    def test_a_copy_is_claimed_once(self):
        copies = PhoneCopies()
        copies.add("Pixel", digest("hello"), now=100)
        self.assertEqual(copies.claim(digest("hello"), now=101), "Pixel")
        self.assertIsNone(copies.claim(digest("hello"), now=101))

    def test_only_the_same_text(self):
        copies = PhoneCopies()
        copies.add("Pixel", digest("hello"), now=100)
        self.assertIsNone(copies.claim(digest("hello there"), now=100))

    def test_only_just_now(self):
        copies = PhoneCopies()
        copies.add("Pixel", digest("hello"), now=100)
        self.assertIsNone(copies.claim(digest("hello"), now=100 + MATCH_SECONDS))

    def test_the_digest_is_satellites(self):
        # Satellite sends the hexadecimal SHA-256 of the UTF-8 text.
        self.assertEqual(digest("é"), "4a99557e4033c3539de2eb65472017cad5f9557f7a0625a09f1c3f6e2ba69c4c")


if __name__ == "__main__":
    unittest.main()
