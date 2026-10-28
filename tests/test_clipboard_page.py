"""How an item of the history is shown in the Clipboard tab."""

import unittest

from xclipy.ui.clipboard_page import LINE_SEPARATOR, PREVIEW_LENGTH, _parse_color, preview


class PreviewTests(unittest.TestCase):
    def test_short_text_as_it_is(self):
        self.assertEqual(preview("  sudo apt install xclipy\n"), "sudo apt install xclipy")

    def test_three_lines_at_most(self):
        self.assertEqual(preview("one\ntwo\nthree\nfour"), LINE_SEPARATOR.join(["one", "two", "three…"]))
        self.assertEqual(preview("one\r\ntwo\nthree"), LINE_SEPARATOR.join(["one", "two", "three"]))

    def test_long_text_is_cut(self):
        self.assertEqual(preview("x" * 5000), "x" * PREVIEW_LENGTH + "…")


class ColorTests(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(_parse_color("#ff8800"), (1.0, 0x88 / 255, 0.0, 1.0))
        self.assertEqual(_parse_color("#ff880080"), (1.0, 0x88 / 255, 0.0, 0x80 / 255))
        self.assertEqual(_parse_color("#f80c"), (1.0, 0x88 / 255, 0.0, 0xcc / 255))
        self.assertEqual(_parse_color("rgb(255, 0, 0)"), (1.0, 0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
