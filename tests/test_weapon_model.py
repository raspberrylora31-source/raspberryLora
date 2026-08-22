import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detector import (
    WEAPON_UNAVAILABLE,
    WEAPON_WEIGHT_SOURCES,
    WeaponDetector,
    WeaponModelError,
    ensure_weapon_weights,
    resolve_weapon_class_ids,
    weapon_model_missing_message,
)


class MissingWeaponModelTests(unittest.TestCase):
    def test_required_missing_file_raises(self):
        missing = "/tmp/does-not-exist-weapon-best.pt"
        with self.assertRaises(WeaponModelError) as ctx:
            WeaponDetector(model_path=missing, required=True)
        text = str(ctx.exception)
        self.assertIn(WEAPON_UNAVAILABLE, text)
        self.assertIn("does-not-exist-weapon-best.pt", text)

    def test_missing_message_is_explicit(self):
        message = weapon_model_missing_message("models/best.pt")
        self.assertIn(WEAPON_UNAVAILABLE, message)
        self.assertIn("models/best.pt", message)
        self.assertIn("download_weapon_model.py", message)

    def test_empty_directory_is_not_a_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "best.pt"
            with self.assertRaises(WeaponModelError) as ctx:
                WeaponDetector(model_path=str(fake), required=True)
            self.assertIn(WEAPON_UNAVAILABLE, str(ctx.exception))

    def test_person_only_does_not_load_weapon_model(self):
        detector = WeaponDetector(
            model_path="/tmp/does-not-exist-weapon-best.pt",
            required=False,
        )
        self.assertFalse(detector.enabled)
        found, ok = detector.detect_in_region(None, [0, 0, 10, 10])
        self.assertEqual(found, [])
        self.assertFalse(ok)

    def test_custom_path_is_not_replaced_by_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "custom.pt"
            with self.assertRaises(WeaponModelError):
                ensure_weapon_weights(str(missing), download=True)

    def test_existing_local_weights_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "best.pt"
            path.write_bytes(b"PK" + b"\x00" * 1_200_000)
            resolved = ensure_weapon_weights(str(path), download=False)
            self.assertEqual(resolved.resolve(), path.resolve())


class WeaponClassFromRealModelTests(unittest.TestCase):
    def test_gun_knife_names_are_auto_selected(self):
        ids, names = resolve_weapon_class_ids({0: "gun", 1: "knife"}, [])
        self.assertEqual(names, ["gun", "knife"])
        self.assertEqual(ids, [0, 1])

    def test_stock_coco_is_rejected(self):
        coco = {
            0: "person",
            1: "bicycle",
            2: "car",
            16: "dog",
            56: "chair",
            62: "tv",
            79: "toothbrush",
        }
        coco.update({i: f"coco{i}" for i in range(3, 80) if i not in coco})
        with self.assertRaises(WeaponModelError) as ctx:
            resolve_weapon_class_ids(coco, [])
        self.assertIn(WEAPON_UNAVAILABLE, str(ctx.exception))
        self.assertIn("COCO", str(ctx.exception))

    def test_public_source_is_yolov5_gun_knife(self):
        primary = WEAPON_WEIGHT_SOURCES[0]
        self.assertIn("knife_Gun_Detection", primary["url"])
        self.assertEqual(primary["classes"], ("gun", "knife"))
        self.assertTrue(primary["url"].endswith(".pt"))

    def test_checked_in_or_downloaded_weights_are_yolov5_zip(self):
        local = Path(__file__).resolve().parent.parent / "models" / "best.pt"
        if not local.is_file():
            self.skipTest("models/best.pt not present in this workspace")
        header = local.read_bytes()[:2]
        self.assertEqual(header, b"PK")
        data = local.read_bytes()
        self.assertIn(b"gun", data)
        self.assertIn(b"knife", data)
        self.assertGreater(local.stat().st_size, 1_000_000)


if __name__ == "__main__":
    unittest.main()
