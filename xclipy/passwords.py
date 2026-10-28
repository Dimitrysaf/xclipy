"""Pinned passwords kept in the keyring (Passwords and Keys), when the settings say so.

The history file only says where a saved password goes, by an id; the
password itself is in the user's keyring, which the login unlocks.
"""

import uuid

import gi

from gi.repository import GLib

from xclipy.i18n import _


def _secret():
    try:
        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except (ImportError, ValueError):
        return None
    return Secret


class Keyring:
    def __init__(self):
        self._secret = _secret()
        if self._secret is not None:
            self._schema = self._secret.Schema.new(
                "org.x.Xclipy.Password", self._secret.SchemaFlags.NONE,
                {"id": self._secret.SchemaAttributeType.STRING})

    @staticmethod
    def new_id():
        return uuid.uuid4().hex

    def save(self, password_id, password):
        """Returns whether it was saved."""
        if self._secret is None:
            return False
        try:
            return self._secret.password_store_sync(
                self._schema, {"id": password_id}, self._secret.COLLECTION_DEFAULT,
                _("Pinned password from the clipboard history"), password, None)
        except GLib.Error:
            return False

    def load(self, password_id):
        """The password, or None (not saved, or no keyring)."""
        if self._secret is None:
            return None
        try:
            return self._secret.password_lookup_sync(self._schema, {"id": password_id}, None)
        except GLib.Error:
            return None

    def delete(self, password_id):
        if self._secret is None:
            return
        try:
            self._secret.password_clear_sync(self._schema, {"id": password_id}, None)
        except GLib.Error:
            pass

    def delete_all(self):
        """Every password Xclipy saved, also those the history forgot."""
        if self._secret is None:
            return
        try:
            self._secret.password_clear_sync(self._schema, {}, None)
        except GLib.Error:
            pass
