"""The Cinnamon custom shortcut that opens the overlay."""

import unittest

from xclipy import shortcut


class FakeSettings:
    def __init__(self, **values):
        self.values = dict(values)

    def get_strv(self, key):
        return list(self.values.get(key, []))

    def set_strv(self, key, value):
        self.values[key] = list(value)

    def get_string(self, key):
        return self.values.get(key, "")

    def set_string(self, key, value):
        self.values[key] = value

    def get_boolean(self, key):
        return self.values.get(key, False)

    def set_boolean(self, key, value):
        self.values[key] = value


class FakeCinnamon:
    """org.cinnamon.desktop.keybindings and its custom shortcuts."""

    def __init__(self, custom_list=()):
        self.parent = FakeSettings(**{"custom-list": list(custom_list)})
        self.customs = {}

    def custom(self, name):
        return self.customs.setdefault(name, FakeSettings())

    def shortcut(self, kind=shortcut.CLIPBOARD):
        return shortcut.Shortcut(kind, self.parent, self.custom)

    def names(self):
        return [n for n in self.parent.get_strv("custom-list") if n != shortcut.DUMMY]


class ShortcutTests(unittest.TestCase):
    def test_added_after_the_users_own_shortcuts(self):
        cinnamon = FakeCinnamon(["custom0", "custom2"])
        cinnamon.custom("custom0").set_string("command", "firefox")
        cinnamon.shortcut().set_binding(["<Super>v"])
        self.assertEqual(cinnamon.names(), ["custom0", "custom2", "custom1"])
        added = cinnamon.custom("custom1")
        self.assertEqual(added.get_string("command"), "xclipy --show")
        self.assertEqual(added.get_string("name"), "Clipboard history")
        self.assertEqual(added.get_strv("binding"), ["<Super>v"])

    def test_changed_in_place(self):
        cinnamon = FakeCinnamon()
        cinnamon.shortcut().set_binding(["<Super>v"])
        cinnamon.shortcut().set_binding(["<Primary><Alt>v"])
        self.assertEqual(cinnamon.names(), ["custom0"])
        self.assertEqual(cinnamon.shortcut().binding(), ["<Primary><Alt>v"])

    def test_every_change_changes_the_list(self):
        # Cinnamon only reloads custom shortcuts when custom-list changes.
        cinnamon = FakeCinnamon()
        lists = []
        for binding in (["<Super>v"], ["<Super>c"], []):
            cinnamon.shortcut().set_binding(binding)
            lists.append(cinnamon.parent.get_strv("custom-list"))
        self.assertNotEqual(lists[0], lists[1])
        self.assertNotEqual(lists[1], lists[2])

    def test_default_only_once(self):
        cinnamon = FakeCinnamon()
        settings = FakeSettings()
        cinnamon.shortcut().add_default(settings)
        self.assertEqual(cinnamon.shortcut().binding(), ["<Super>v"])
        self.assertTrue(settings.get_boolean("shortcut-added"))
        # Removed by the user in the Keyboard settings: it isn't added back.
        cinnamon.parent.set_strv("custom-list", [])
        cinnamon.shortcut().add_default(settings)
        self.assertIsNone(cinnamon.shortcut().find())
        self.assertEqual(cinnamon.shortcut().binding(), [])

    def test_the_emoji_shortcut_beside_it(self):
        cinnamon = FakeCinnamon()
        settings = FakeSettings()
        cinnamon.shortcut().add_default(settings)
        cinnamon.shortcut(shortcut.EMOJI).add_default(settings)
        self.assertEqual(cinnamon.names(), ["custom0", "custom1"])
        self.assertEqual(cinnamon.custom("custom1").get_string("command"), "xclipy --emoji")
        self.assertEqual(cinnamon.custom("custom1").get_string("name"), "Emojis")
        self.assertEqual(cinnamon.shortcut(shortcut.EMOJI).binding(), ["<Super>period"])
        self.assertEqual(cinnamon.shortcut().binding(), ["<Super>v"])
        self.assertTrue(settings.get_boolean("emoji-shortcut-added"))


if __name__ == "__main__":
    unittest.main()
