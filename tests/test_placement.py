"""Where the overlay opens."""

import unittest

from xclipy.placement import GAP, MARGIN, place

SIZE = (360, 440)
WORKAREA = (0, 0, 1920, 1040)  # a 1080p monitor with a 40px panel at the bottom


class PlacementTests(unittest.TestCase):
    def test_bottom_right_without_a_text_cursor(self):
        self.assertEqual(place(SIZE, WORKAREA), (1920 - 360 - MARGIN, 1040 - 440 - MARGIN))

    def test_bottom_right_of_the_second_monitor(self):
        self.assertEqual(place(SIZE, (1920, 0, 1280, 984)), (1920 + 1280 - 360 - MARGIN, 984 - 440 - MARGIN))

    def test_under_the_text_cursor(self):
        self.assertEqual(place(SIZE, WORKAREA, (500, 200, 1, 18)), (500, 200 + 18 + GAP))

    def test_above_the_text_cursor_near_the_bottom(self):
        self.assertEqual(place(SIZE, WORKAREA, (500, 900, 1, 18)), (500, 900 - GAP - 440))

    def test_stays_on_the_screen(self):
        # Right edge: moved left. Neither below nor above fits: kept inside.
        self.assertEqual(place(SIZE, WORKAREA, (1900, 200, 1, 18))[0], 1920 - 360)
        self.assertEqual(place(SIZE, (0, 0, 1024, 600), (10, 300, 1, 18)), (10, 600 - 440))


if __name__ == "__main__":
    unittest.main()
