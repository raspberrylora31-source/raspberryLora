import unittest
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from message_formatter import format_detection_message, format_timestamp


class FormatTimestampTests(unittest.TestCase):
    def test_local_clock_format(self):
        stamp = format_timestamp(datetime(2026, 8, 20, 11, 25, 31))
        self.assertEqual(stamp, "2026-08-20 11:25:31")

    def test_no_milliseconds(self):
        stamp = format_timestamp(datetime(2026, 8, 20, 11, 25, 31, 123456))
        self.assertEqual(stamp, "2026-08-20 11:25:31")


class FormatDetectionMessageTests(unittest.TestCase):
    def test_no_weapon(self):
        message = format_detection_message("NO_WPN", "2026-08-20 11:25:31")
        self.assertEqual(message, "PERSON NO_WPN 2026-08-20 11:25:31")

    def test_weapon(self):
        message = format_detection_message("WPN", "2026-08-20 11:25:38")
        self.assertEqual(message, "PERSON WPN 2026-08-20 11:25:38")

    def test_lowercase_state(self):
        message = format_detection_message("no_wpn", "2026-08-20 11:25:31")
        self.assertEqual(message, "PERSON NO_WPN 2026-08-20 11:25:31")

    def test_rejects_unknown_state(self):
        with self.assertRaises(ValueError):
            format_detection_message("UNKNOWN", "2026-08-20 11:25:31")

    def test_requires_timestamp_content(self):
        with self.assertRaises(ValueError):
            format_detection_message("WPN", "   ")


if __name__ == "__main__":
    unittest.main()
