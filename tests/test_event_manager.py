import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_manager import EventManager


class EventManagerTests(unittest.TestCase):
    def test_requires_confirmation_frames(self):
        manager = EventManager(confirmation_frames=3, cooldown_seconds=30)
        self.assertIsNone(manager.update("NO_WPN", now=1.0))
        self.assertIsNone(manager.update("NO_WPN", now=1.1))
        self.assertEqual(manager.update("NO_WPN", now=1.2), "NO_WPN")

    def test_does_not_repeat_immediately(self):
        manager = EventManager(confirmation_frames=1, cooldown_seconds=30)
        self.assertEqual(manager.update("NO_WPN", now=0.0), "NO_WPN")
        self.assertIsNone(manager.update("NO_WPN", now=1.0))
        self.assertIsNone(manager.update("NO_WPN", now=10.0))

    def test_resend_after_cooldown(self):
        manager = EventManager(
            confirmation_frames=1,
            cooldown_seconds=30,
            state_change_only=False,
        )
        self.assertEqual(manager.update("NO_WPN", now=0.0), "NO_WPN")
        self.assertEqual(manager.update("NO_WPN", now=30.0), "NO_WPN")

    def test_state_change_sends_immediately(self):
        manager = EventManager(confirmation_frames=1, cooldown_seconds=30)
        self.assertEqual(manager.update("NO_WPN", now=0.0), "NO_WPN")
        self.assertEqual(manager.update("WPN", now=1.0), "WPN")

    def test_state_change_only_skips_cooldown_repeat(self):
        manager = EventManager(
            confirmation_frames=1,
            cooldown_seconds=5,
            state_change_only=True,
        )
        self.assertEqual(manager.update("NO_WPN", now=0.0), "NO_WPN")
        self.assertIsNone(manager.update("NO_WPN", now=20.0))

    def test_no_person_does_not_emit(self):
        manager = EventManager(confirmation_frames=2, cooldown_seconds=30)
        self.assertIsNone(manager.update(None, now=0.0))
        self.assertIsNone(manager.update(None, now=0.1))

    def test_flicker_resets_confirmation(self):
        manager = EventManager(confirmation_frames=3, cooldown_seconds=30)
        self.assertIsNone(manager.update("NO_WPN", now=0.0))
        self.assertIsNone(manager.update("WPN", now=0.1))
        self.assertIsNone(manager.update("NO_WPN", now=0.2))
        self.assertIsNone(manager.update("NO_WPN", now=0.3))
        self.assertEqual(manager.update("NO_WPN", now=0.4), "NO_WPN")


if __name__ == "__main__":
    unittest.main()
