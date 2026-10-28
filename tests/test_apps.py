"""Recognising the excluded applications."""

import unittest

from xclipy.apps import desktop_names, is_excluded


class AppsTests(unittest.TestCase):
    def test_names_of_a_desktop_file(self):
        self.assertEqual(desktop_names("org.keepassxc.KeePassXC.desktop", None, "keepassxc"),
                         {"org.keepassxc.keepassxc", "keepassxc"})
        self.assertEqual(desktop_names("bitwarden.desktop", "Bitwarden", "/opt/Bitwarden/bitwarden"),
                         {"bitwarden"})
        # A launcher says nothing about the application.
        self.assertEqual(desktop_names("my-tool.desktop", None, "python3"), {"my-tool"})

    def test_matching_windows(self):
        names = {"keepassxc.desktop": {"keepassxc"}, "firefox.desktop": {"firefox"}}
        self.assertTrue(is_excluded({"keepassxc"}, ["keepassxc.desktop"], names.get))
        self.assertFalse(is_excluded({"firefox", "navigator"}, ["keepassxc.desktop"], names.get))
        self.assertFalse(is_excluded(set(), ["keepassxc.desktop"], names.get))


if __name__ == "__main__":
    unittest.main()
