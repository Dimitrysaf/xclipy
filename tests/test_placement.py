"""Where the overlay opens."""

import unittest
from types import SimpleNamespace

from xclipy.placement import GAP, MARGIN, place
from xclipy.ui.overlay import is_wayland

SIZE = (360, 440)
WORKAREA = (0, 0, 1920, 1040)  # a 1080p monitor with a 40px panel at the bottom


class PlacementTests(unittest.TestCase):
    def test_bottom_right_of_the_pointer(self):
        self.assertEqual(place(SIZE, WORKAREA, (500, 200)), (500 + GAP, 200 + GAP))

    def test_bottom_right_corner_only_without_a_pointer(self):
        self.assertEqual(place(SIZE, WORKAREA), (1920 - 360 - MARGIN, 1040 - 440 - MARGIN))
        self.assertEqual(place(SIZE, (1920, 0, 1280, 984)), (1920 + 1280 - 360 - MARGIN, 984 - 440 - MARGIN))

    def test_left_of_the_pointer_near_the_right_edge(self):
        self.assertEqual(place(SIZE, WORKAREA, (1800, 200)), (1800 - GAP - 360, 200 + GAP))

    def test_above_the_pointer_near_the_bottom(self):
        self.assertEqual(place(SIZE, WORKAREA, (500, 900)), (500 + GAP, 900 - GAP - 440))

    def test_stays_on_the_screen(self):
        # Neither below nor above fits on a small screen: kept inside.
        self.assertEqual(place(SIZE, (0, 0, 1024, 600), (10, 300)), (10 + GAP, 600 - 440))
        self.assertEqual(place(SIZE, (1920, 0, 1280, 984), (1925, 5)), (1925 + GAP, 5 + GAP))


def _display(type_name):
    return SimpleNamespace(__gtype__=SimpleNamespace(name=type_name))


class DisplayTests(unittest.TestCase):
    def test_wayland_by_its_type(self):
        # Without GdkWayland imported, Python names the class GdkWaylandDisplay.
        self.assertTrue(is_wayland(_display("GdkWaylandDisplay")))
        self.assertFalse(is_wayland(_display("GdkX11Display")))
        self.assertFalse(is_wayland(None))


if __name__ == "__main__":
    unittest.main()
