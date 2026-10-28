"""Pasting the chosen item, and leaving passwords out of the history."""

import unittest

from xclipy.paste import paste_keys
from xclipy.watcher import PASSWORD_HINT, is_password


class PasteTests(unittest.TestCase):
    def test_terminals_paste_with_shift(self):
        self.assertEqual(paste_keys(False), "ctrl+v")
        self.assertEqual(paste_keys(True), "ctrl+shift+v")

    def test_passwords_are_recognised(self):
        self.assertTrue(is_password(["UTF8_STRING", PASSWORD_HINT]))
        self.assertFalse(is_password(["UTF8_STRING", "TEXT"]))


if __name__ == "__main__":
    unittest.main()
