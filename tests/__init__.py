import os

# The tests compare interface text in English, whatever the desktop's language
# (before xclipy.i18n loads a catalogue).
os.environ["LANGUAGE"] = "C"
