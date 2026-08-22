import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detector import (
    PROJECT_ROOT,
    _sys_path_without_project_shadows,
    classify_persons_and_weapons,
    cuda_torch_arm_warning,
    display_overlay_label,
    parse_yolov5_predictions,
    resolve_weapon_class_ids,
    WeaponModelError,
)


class AssociationTests(unittest.TestCase):
    def test_no_person_is_not_wpn_or_no_wpn(self):
        weapons = [{"bbox": [10, 10, 40, 40], "confidence": 0.9}]
        state, persons, _ = classify_persons_and_weapons([], weapons, 640, 360)
        self.assertIsNone(state)
        self.assertEqual(persons, [])

    def test_person_without_weapon_after_model_ran(self):
        persons = [{"bbox": [100, 50, 200, 300], "confidence": 0.8}]
        state, labeled, _ = classify_persons_and_weapons(persons, [], 640, 360)
        self.assertEqual(state, "NO_WPN")
        self.assertEqual(labeled[0]["label"], "PERSON")

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
        self.assertEqual(labeled[0]["label"], "PERSON")

    def test_mixed_people_any_wpn_is_event(self):
        persons = [
            {"bbox": [100, 50, 200, 300], "confidence": 0.8},
            {"bbox": [400, 50, 500, 300], "confidence": 0.8},
        ]
        weapons = [{"bbox": [120, 80, 150, 140], "confidence": 0.9}]
        state, labeled, _ = classify_persons_and_weapons(persons, weapons, 640, 360)
        self.assertEqual(state, "WPN")
        self.assertEqual(labeled[0]["label"], "PERSON WPN")
        self.assertEqual(labeled[1]["label"], "PERSON")


class PersonResultParsingTests(unittest.TestCase):
    def test_parses_person_rows(self):
        rows = [
            [10, 20, 30, 40, 0.9, 0],
            [1, 2, 3, 4, 0.1, 0],
            [5, 6, 7, 8, 0.8, 2],
        ]
        found = parse_yolov5_predictions(rows, 0.45, allowed_class_ids=[0])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["class_id"], 0)
        self.assertEqual(found[0]["bbox"], [10.0, 20.0, 30.0, 40.0])

    def test_skips_malformed_rows(self):
        rows = [[1, 2, 3], "bad", [10, 20, 30, 40, 0.8, 0]]
        found = parse_yolov5_predictions(rows, 0.4)
        self.assertEqual(len(found), 1)

    def test_keeps_other_classes_when_unfiltered(self):
        rows = [
            [10, 20, 30, 40, 0.9, 0],
            [50, 60, 80, 90, 0.8, 2],
        ]
        found = parse_yolov5_predictions(rows, 0.45)
        self.assertEqual([row["class_id"] for row in found], [0, 2])


class OverlayLabelTests(unittest.TestCase):
    def test_unarmed_person_is_person_not_no_wpn(self):
        self.assertEqual(display_overlay_label("NO_WPN", [{"label": "PERSON"}]), "PERSON")

    def test_armed_person_is_person_wpn(self):
        self.assertEqual(display_overlay_label("WPN", [{"label": "PERSON WPN"}]), "PERSON WPN")

    def test_empty_frame(self):
        self.assertEqual(display_overlay_label(None, []), "NO PERSON EVENT")


class WeaponClassResolutionTests(unittest.TestCase):
    def test_single_weapon_class_used_automatically(self):
        ids, names = resolve_weapon_class_ids({0: "weapon"}, [])
        self.assertEqual(names, ["weapon"])
        self.assertEqual(ids, [0])

    def test_does_not_treat_person_as_weapon(self):
        ids, names = resolve_weapon_class_ids({0: "person", 1: "pistol", 2: "rifle"}, [])
        self.assertEqual(names, ["pistol", "rifle"])
        self.assertEqual(ids, [1, 2])

    def test_configured_classes_must_exist(self):
        with self.assertRaises(WeaponModelError) as ctx:
            resolve_weapon_class_ids({0: "weapon"}, ["pistol", "rifle"])
        self.assertIn("not found", str(ctx.exception).lower())

    def test_person_cannot_be_configured_as_weapon(self):
        with self.assertRaises(WeaponModelError):
            resolve_weapon_class_ids({0: "person", 1: "pistol"}, ["person"])

    def test_empty_names_fail(self):
        with self.assertRaises(WeaponModelError):
            resolve_weapon_class_ids({}, ["weapon"])

    def test_person_only_model_is_invalid_weapon_model(self):
        with self.assertRaises(WeaponModelError):
            resolve_weapon_class_ids({0: "person"}, [])


class UnsafeTorchTests(unittest.TestCase):
    def test_cuda_wheel_on_pi4_is_hard_error(self):
        text = cuda_torch_arm_warning("2.13.0+cu130", "aarch64", cpuinfo="Features: fp asimd crc32")
        self.assertIsNotNone(text)
        self.assertTrue(text.startswith("ERROR:"))
        self.assertIn("Illegal instruction", text)
        self.assertIn("torch==2.3.1", text)
        self.assertIn("fix_pi_torch.sh", text)
        self.assertIn("--backend hog", text)

    def test_new_cpu_wheel_on_pi4_is_hard_error(self):
        text = cuda_torch_arm_warning("2.13.0+cpu", "aarch64", cpuinfo="Features: fp asimd crc32")
        self.assertIsNotNone(text)
        self.assertIn("2.3.1", text)

    def test_silent_on_pi4_safe_cpu_torch(self):
        self.assertIsNone(
            cuda_torch_arm_warning("2.3.1", "aarch64", cpuinfo="Features: fp asimd crc32")
        )

    def test_silent_on_pi5_with_lse(self):
        self.assertIsNone(
            cuda_torch_arm_warning(
                "2.13.0+cpu",
                "aarch64",
                cpuinfo="Features: fp asimd crc32 atomics",
            )
        )

    def test_silent_on_x86_cuda(self):
        self.assertIsNone(cuda_torch_arm_warning("2.13.0+cu130", "x86_64"))

    def test_hub_loader_avoids_project_models_shadow(self):
        source = Path(__file__).resolve().parent.parent.joinpath("detector.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def _sys_path_without_project_shadows", source)
        cleaned = _sys_path_without_project_shadows()
        self.assertNotIn(str(PROJECT_ROOT.resolve()), cleaned)
        self.assertNotIn("", cleaned)
        self.assertNotIn(".", cleaned)


if __name__ == "__main__":
    unittest.main()
