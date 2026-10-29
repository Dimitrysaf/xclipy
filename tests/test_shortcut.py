"""The desktops' custom shortcuts that open the overlay."""

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


class FakeCinnamon:
    """org.cinnamon.desktop.keybindings and its custom shortcuts."""

    def __init__(self, custom_list=()):
        self.parent = FakeSettings(**{"custom-list": list(custom_list)})
        self.customs = {}

    def custom(self, name):
        return self.customs.setdefault(name, FakeSettings())

    def backend(self):
        return shortcut.CinnamonShortcuts(self.parent, self.custom)

    def shortcut(self, kind=shortcut.CLIPBOARD):
        return shortcut.Shortcut(kind, self.backend())

    def names(self):
        return [n for n in self.parent.get_strv("custom-list") if n != shortcut.CinnamonShortcuts.DUMMY]


class CinnamonTests(unittest.TestCase):
    def test_added_after_the_users_own_shortcuts(self):
        cinnamon = FakeCinnamon(["custom0", "custom2"])
        cinnamon.custom("custom0").set_string("command", "firefox")
        cinnamon.shortcut().set_binding("<Super>v")
        self.assertEqual(cinnamon.names(), ["custom0", "custom2", "custom1"])
        added = cinnamon.custom("custom1")
        self.assertEqual(added.get_string("command"), "xclipy --show")
        self.assertEqual(added.get_string("name"), "Clipboard history")
        self.assertEqual(added.get_strv("binding"), ["<Super>v"])

    def test_changed_in_place(self):
        cinnamon = FakeCinnamon()
        cinnamon.shortcut().set_binding("<Super>v")
        cinnamon.shortcut().set_binding("<Primary><Alt>v")
        self.assertEqual(cinnamon.names(), ["custom0"])
        self.assertEqual(cinnamon.shortcut().binding(), "<Primary><Alt>v")
        cinnamon.shortcut().set_binding("")
        self.assertEqual(cinnamon.shortcut().binding(), "")

    def test_every_change_changes_the_list(self):
        # Cinnamon only reloads custom shortcuts when custom-list changes.
        cinnamon = FakeCinnamon()
        lists = []
        for binding in ("<Super>v", "<Super>c", ""):
            cinnamon.shortcut().set_binding(binding)
            lists.append(cinnamon.parent.get_strv("custom-list"))
        self.assertNotEqual(lists[0], lists[1])
        self.assertNotEqual(lists[1], lists[2])

    def test_defaults_only_once_per_desktop(self):
        cinnamon = FakeCinnamon()
        settings = FakeSettings()
        for kind in shortcut.KINDS:
            cinnamon.shortcut(kind).add_default(settings)
        self.assertEqual(cinnamon.names(), ["custom0", "custom1"])
        self.assertEqual(cinnamon.shortcut().binding(), "<Super>v")
        self.assertEqual(cinnamon.shortcut(shortcut.EMOJI).binding(), "<Super>period")
        self.assertEqual(cinnamon.custom("custom1").get_string("name"), "Emojis")
        self.assertEqual(settings.get_strv("shortcuts-added"), ["cinnamon:clipboard", "cinnamon:emoji"])
        # Removed by the user in the Keyboard settings: it isn't added back.
        cinnamon.parent.set_strv("custom-list", [])
        cinnamon.shortcut().add_default(settings)
        self.assertEqual(cinnamon.shortcut().binding(), "")


class MateTests(unittest.TestCase):
    def setUp(self):
        self.customs = {}
        self.backend = shortcut.MateShortcuts(lambda name: self.customs.setdefault(name, FakeSettings()))

    def test_added_in_a_free_place_and_changed_there(self):
        self.customs["custom0"] = FakeSettings(name="Terminal", action="mate-terminal", binding="<Mod4>t")
        keys = shortcut.Shortcut(shortcut.CLIPBOARD, self.backend)
        keys.set_binding("<Super>v")
        added = self.customs["custom1"]
        # MATE writes Super as <Mod4>.
        self.assertEqual((added.get_string("name"), added.get_string("action"), added.get_string("binding")),
                         ("Clipboard history", "xclipy --show", "<Mod4>v"))
        self.assertEqual(keys.binding(), "<Super>v")
        keys.set_binding("<Primary><Alt>v")
        self.assertEqual(keys.binding(), "<Primary><Alt>v")
        self.assertEqual(self.customs["custom0"].get_string("action"), "mate-terminal")

    def test_defaults(self):
        settings = FakeSettings()
        for kind in shortcut.KINDS:
            shortcut.Shortcut(kind, self.backend).add_default(settings)
        self.assertEqual(shortcut.Shortcut(shortcut.EMOJI, self.backend).binding(), "<Super>period")
        self.assertEqual(settings.get_strv("shortcuts-added"), ["mate:clipboard", "mate:emoji"])


class FakeXfconf:
    """xfconf-query on the xfce4-keyboard-shortcuts channel."""

    def __init__(self, properties):
        self.properties = dict(properties)

    def __call__(self, arguments):
        if "-l" in arguments:
            return "".join("{} {}\n".format(p, v) for p, v in self.properties.items())
        prop = arguments[arguments.index("-p") + 1]
        if "-r" in arguments:
            self.properties.pop(prop, None)
        elif "-s" in arguments:
            self.properties[prop] = arguments[arguments.index("-s") + 1]
        return ""


class XfceTests(unittest.TestCase):
    def test_the_accelerator_is_the_property(self):
        xfconf = FakeXfconf({"/commands/custom/<Super>e": "thunar", "/commands/default/<Alt>F2": "xfrun4"})
        keys = shortcut.Shortcut(shortcut.CLIPBOARD, shortcut.XfceShortcuts(xfconf))
        keys.set_binding("<Super>v")
        self.assertEqual(xfconf.properties["/commands/custom/<Super>v"], "xclipy --show")
        keys.set_binding("<Primary><Alt>v")
        self.assertNotIn("/commands/custom/<Super>v", xfconf.properties)
        self.assertEqual(keys.binding(), "<Primary><Alt>v")
        keys.set_binding("")
        self.assertEqual(keys.binding(), "")
        self.assertEqual(xfconf.properties["/commands/custom/<Super>e"], "thunar")


class DesktopTests(unittest.TestCase):
    def test_no_shortcuts_elsewhere(self):
        self.assertIsNone(shortcut.backend_for_desktop("KDE"))
        self.assertIsNone(shortcut.backend_for_desktop(""))


if __name__ == "__main__":
    unittest.main()
