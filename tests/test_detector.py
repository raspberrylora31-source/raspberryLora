import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detector import classify_persons_and_weapons


class AssociationTests(unittest.TestCase):
    def test_no_person_is_not_wpn(self):
        weapons = [{"bbox": [10, 10, 40, 40], "confidence": 0.9}]
        state, persons, _ = classify_persons_and_weapons([], weapons, 640, 360)
        self.assertIsNone(state)
        self.assertEqual(persons, [])

    def test_person_without_weapon(self):
        persons = [{"bbox": [100, 50, 200, 300], "confidence": 0.8}]
        state, labeled, _ = classify_persons_and_weapons(persons, [], 640, 360)
        self.assertEqual(state, "NO_WPN")
        self.assertEqual(labeled[0]["label"], "PERSON NO_WPN")

    def test_weapon_inside_person_region(self):
        persons = [{"bbox": [100, 50, 200, 300], "confidence": 0.8}]
        weapons = [{"bbox": [120, 80, 150, 140], "confidence": 0.9}]
        state, labeled, _ = classify_persons_and_weapons(persons, weapons, 640, 360)
        self.assertEqual(state, "WPN")
        self.assertEqual(labeled[0]["label"], "PERSON WPN")

    def test_distant_weapon_does_not_arm_person(self):
        persons = [{"bbox": [100, 50, 200, 300], "confidence": 0.8}]
        weapons = [{"bbox": [500, 20, 540, 60], "confidence": 0.9}]
        state, labeled, _ = classify_persons_and_weapons(persons, weapons, 640, 360)
        self.assertEqual(state, "NO_WPN")
        self.assertEqual(labeled[0]["label"], "PERSON NO_WPN")


if __name__ == "__main__":
    unittest.main()
