"""Kinds of copied text, and passwords recognised by how random they look."""

import unittest

from xclipy import kinds


class KindTests(unittest.TestCase):
    def test_kinds(self):
        for text, kind in (
            ("https://github.com/Dimitrysaf/xclipy", kinds.LINK), ("www.linuxmint.com", kinds.LINK),
            ("dimitris@example.com", kinds.EMAIL), ("mailto:me@example.gr", kinds.EMAIL),
            ("+30 210 123 4567", kinds.PHONE), ("(210) 123-4567", kinds.PHONE), ("tel:2101234567", kinds.PHONE),
            ("/", kinds.PATH), ("file:///tmp/a b.txt", kinds.PATH),
            ("#ff8800", kinds.COLOR), ("#f80c", kinds.COLOR), ("rgb(10, 20, 30)", kinds.COLOR),
            ("hello world", None), ("2026-10-28", None), ("12345678", None), ("1.234.567", None),
            ("/no/such/path/here", None), ("see https://x.org", None), ("line\nhttps://x.org", None),
        ):
            with self.subTest(text=text):
                self.assertEqual(kinds.kind_of(text), kind)


class RandomTests(unittest.TestCase):
    def test_generated_passwords_and_keys(self):
        for text in ("xK9#mQ2$vL", "X7f!pL2q", "Qw8Zr4Tn", "a1B2c3D4e5",
                     "ghp_aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z", "sk-proj-Ab12Cd34Ef56"):
            with self.subTest(text=text):
                self.assertTrue(kinds.looks_random(text))

    def test_words_code_and_ids_are_not(self):
        for text in ("html5Parser", "Password2024", "user_name_2", "foo.bar(3)", "Hello,World!",
                     "getElementById", "550e8400-e29b-41d4-a716-446655440000",
                     "3f786850e387550fdab836ed7e6dc881de23001b", "2026-10-28", "short1!",
                     "two words1!X", "https://x.org/?a=B1&c=D2"):
            with self.subTest(text=text):
                self.assertFalse(kinds.looks_random(text))


class FilterTests(unittest.TestCase):
    def test_item_kinds(self):
        from xclipy.history import Item
        self.assertEqual(kinds.item_kind(Item(image="a.png")), kinds.IMAGE)
        self.assertEqual(kinds.item_kind(Item(text="https://x.org", secret=True)), kinds.PASSWORD)
        self.assertEqual(kinds.item_kind(Item(text="https://x.org")), kinds.LINK)
        self.assertEqual(kinds.item_kind(Item(text="hello")), kinds.TEXT)

    def test_options(self):
        present = {kinds.TEXT, kinds.LINK, kinds.IMAGE}
        self.assertEqual(kinds.filter_options(present, True), [kinds.TEXT, kinds.LINK, kinds.IMAGE])
        # Without the item types, only images.
        self.assertEqual(kinds.filter_options(present, False), [kinds.IMAGE])
        self.assertEqual(kinds.filter_options({kinds.TEXT, kinds.LINK}, False), [])
        # Nothing to narrow: one kind only.
        self.assertEqual(kinds.filter_options({kinds.IMAGE}, False), [])
        self.assertEqual(kinds.filter_options({kinds.TEXT}, True), [])
        self.assertEqual(kinds.filter_options(set(), True), [])


if __name__ == "__main__":
    unittest.main()
