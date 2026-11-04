"""Reading what is copied, without being flooded by a program copying in a loop."""

import time
import unittest

from gi.repository import GLib

from xclipy.watcher import READ_INTERVAL, ClipboardWatcher


def watcher():
    """Only its reading, without a clipboard to watch."""
    reader = ClipboardWatcher.__new__(ClipboardWatcher)
    reader._last_read = 0
    reader._pending = None
    reader._pending_source = 0
    return reader


class ReadingTests(unittest.TestCase):
    def test_a_copy_is_read_at_once(self):
        reads = []
        watcher()._read_soon(lambda: reads.append("now"))
        self.assertEqual(reads, ["now"])

    def test_a_flood_is_read_once_more_with_the_latest(self):
        reads = []
        reader = watcher()
        start = time.monotonic()
        for number in range(1000):
            reader._read_soon(lambda number=number: reads.append(number))
        self.assertEqual(reads, [0])  # the rest waits
        context = GLib.MainContext.default()
        while len(reads) < 2 and time.monotonic() - start < 2:
            context.iteration(True)
        self.assertEqual(reads, [0, 999])  # the latest, once
        self.assertGreaterEqual(time.monotonic() - start, READ_INTERVAL - 0.01)


if __name__ == "__main__":
    unittest.main()
