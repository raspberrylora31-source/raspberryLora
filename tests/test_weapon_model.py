import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detector import WeaponDetector, WeaponModelError, weapon_model_missing_message


class MissingWeaponModelTests(unittest.TestCase):
    def test_required_missing_file_raises(self):
        missing = "/tmp/does-not-exist-weapon-best.pt"
        with self.assertRaises(WeaponModelError) as ctx:
            WeaponDetector(model_path=missing, required=True)
        text = str(ctx.exception)
        self.assertIn("Weapon detection is required", text)
        self.assertIn("models/best.pt", text)

    def test_missing_message_is_explicit(self):
        message = weapon_model_missing_message("models/best.pt")
        self.assertIn("ERROR: Weapon detection is required but models/best.pt was not found.", message)
        self.assertIn("models/best.pt", message)

    def test_empty_directory_is_not_a_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "best.pt"
            with self.assertRaises(WeaponModelError):
                WeaponDetector(model_path=str(fake), required=True)

    def test_person_only_does_not_load_weapon_model(self):
        detector = WeaponDetector(
            model_path="/tmp/does-not-exist-weapon-best.pt",
            required=False,
        )
        self.assertFalse(detector.enabled)
        found, ok = detector.detect_in_region(None, [0, 0, 10, 10])
        self.assertEqual(found, [])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
