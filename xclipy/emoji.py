"""The emoji, their groups, searching them and the recently used ones."""

import re

from xclipy.emoji_data import EMOJI, GROUPS, TONES
from xclipy.i18n import N_, _

# The groups of emoji_data.GROUPS, as they are shown.
GROUP_NAMES = (
    N_("Smileys & Emotion"), N_("People & Body"), N_("Animals & Nature"), N_("Food & Drink"),
    N_("Travel & Places"), N_("Activities"), N_("Objects"), N_("Symbols"), N_("Flags"),
)
# The values of the emoji-skin-tone setting; "none" is the yellow default.
SKIN_TONES = ("none", "light", "medium-light", "medium", "medium-dark", "dark")
RECENT_SIZE = 30
SEARCH_LIMIT = 300

assert len(GROUP_NAMES) == len(GROUPS)


def group_name(index):
    return _(GROUP_NAMES[index])


def in_group(index):
    """[(emoji, name), ...] of one group, in the usual order."""
    return [(text, name) for group, text, name in EMOJI if group == index]


def group_symbol(index):
    """The group's first emoji, to stand for the group on its button."""
    return next(text for group, text, _name in EMOJI if group == index)


def _words(text):
    return re.findall(r"\w+", text.lower())


def search(query):
    """The emoji with a word in their English name starting with each word of the query."""
    words = _words(query)
    if not words:
        return []
    found = [(text, name) for _group, text, name in EMOJI
             if all(any(part.startswith(word) for part in _words(name)) for word in words)]
    return found[:SEARCH_LIMIT]


def with_tone(text, tone):
    """The emoji in a skin tone (a SKIN_TONES value), when it has them."""
    index = SKIN_TONES.index(tone) - 1 if tone in SKIN_TONES else -1
    return TONES[text][index] if index >= 0 and text in TONES else text


_names = None


def name_of(text):
    """The English name of an emoji, also in a skin tone."""
    global _names
    if _names is None:
        _names = {emoji: name for _group, emoji, name in EMOJI}
        for emoji, variants in TONES.items():
            for variant in variants:
                _names[variant] = _names[emoji]
    return _names.get(text, "")


def remember(recent, text):
    """The recently used emoji, with text first."""
    return ([text] + [emoji for emoji in recent if emoji != text])[:RECENT_SIZE]
