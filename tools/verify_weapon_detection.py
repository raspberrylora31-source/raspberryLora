#!/usr/bin/env python3
"""
Run the real person + weapon path on still images (no webcam required).

1. Ensures models/best.pt is the public YOLOv5 gun+knife checkpoint
2. Builds two demo frames (person only, person + weapon crop)
3. Prints PERSON NO_WPN / PERSON WPN / NO PERSON EVENT
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from detector import (  # noqa: E402
    FrameClassifier,
    PersonDetector,
    WeaponDetector,
    WeaponModelError,
    draw_detections,
    ensure_weapon_weights,
)

PERSON_IMAGE_URL = (
    "https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/zidane.jpg"
)
WEAPON_CROP_URL = (
    "https://raw.githubusercontent.com/zaizou1003/knife_Gun_Detection/"
    "main/exp6/train_batch0.jpg"
)


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 10_000:
        return dest
    import urllib.request

    tmp = dest.with_suffix(dest.suffix + ".download")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)
    return dest


def _person_only_frame(person_path: Path) -> np.ndarray:
    frame = cv2.imread(str(person_path))
    if frame is None:
        raise SystemExit(f"Could not read {person_path}")
    return cv2.resize(frame, (640, 360))


def _person_with_weapon_frame(person_path: Path, mosaic_path: Path) -> np.ndarray:
    """Paste a training-mosaic weapon crop onto the person torso."""
    frame = _person_only_frame(person_path)
    mosaic = cv2.imread(str(mosaic_path))
    if mosaic is None:
        raise SystemExit(f"Could not read {mosaic_path}")
    h, w = mosaic.shape[:2]
    # Upper-left cell of the YOLOv5 train mosaic is typically a labeled weapon.
    crop = mosaic[0 : max(1, h // 2), 0 : max(1, w // 2)]
    crop = cv2.resize(crop, (160, 120))
    y1, x1 = 140, 240
    y2, x2 = y1 + crop.shape[0], x1 + crop.shape[1]
    y2 = min(y2, frame.shape[0])
    x2 = min(x2, frame.shape[1])
    frame[y1:y2, x1:x2] = crop[: y2 - y1, : x2 - x1]
    return frame


def _run(frame, classifier: FrameClassifier, title: str, out_path: Path) -> str:
    state, persons, weapons = classifier.infer(frame)
    if state is None:
        label = "NO PERSON EVENT"
    elif state == "WPN":
        label = "PERSON WPN"
    else:
        label = "PERSON NO_WPN"
    annotated = draw_detections(frame.copy(), persons, weapons, label)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), annotated)
    print(f"{title}: {label}")
    print(f"  persons={len(persons)} weapons={len(weapons)} preview={out_path}")
    return label


def main() -> int:
    parser = argparse.ArgumentParser(description="Still-image weapon-path check")
    parser.add_argument("--out-dir", default="tests/output")
    args = parser.parse_args()

    try:
        weights = ensure_weapon_weights()
    except WeaponModelError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    fixtures = ROOT / "tests" / "fixtures"
    person_img = _download(PERSON_IMAGE_URL, fixtures / "person.jpg")
    mosaic_img = _download(WEAPON_CROP_URL, fixtures / "weapon_mosaic.jpg")

    person = PersonDetector(backend="yolov5", infer_size=320)
    weapon = WeaponDetector(model_path=str(weights), infer_size=256, required=True)
    classifier = FrameClassifier(person, weapon, person_only=False)

    out_dir = Path(args.out_dir)
    no_wpn = _run(
        _person_only_frame(person_img),
        classifier,
        "person without weapon",
        out_dir / "person_no_wpn.jpg",
    )
    wpn = _run(
        _person_with_weapon_frame(person_img, mosaic_img),
        classifier,
        "person with weapon crop",
        out_dir / "person_wpn.jpg",
    )
    print("Expected: PERSON NO_WPN then PERSON WPN (crop must be detectable).")
    if no_wpn == "NO PERSON EVENT":
        print("Person detector saw no person in the demo photo.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
