"""
Person detection plus optional weapon classification.

COCO YOLO models detect persons. They do not include a real weapon class.
Weapon detection is therefore a separate optional model. If no weapon model
file is configured, every confirmed person is classified PERSON NO_WPN.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# xyxy boxes are [x1, y1, x2, y2]
Box = Sequence[float]


def box_iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def expand_box(
    box: Box, ratio: float, frame_w: int, frame_h: int
) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    dx = w * ratio
    dy = h * ratio
    return (
        max(0.0, x1 - dx),
        max(0.0, y1 - dy),
        min(float(frame_w), x2 + dx),
        min(float(frame_h), y2 + dy),
    )


def box_center(box: Box) -> Tuple[float, float]:
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def point_in_box(px: float, py: float, box: Box) -> bool:
    return box[0] <= px <= box[2] and box[1] <= py <= box[3]


def weapon_associated_with_person(
    person_box: Box,
    weapon_box: Box,
    frame_w: int,
    frame_h: int,
    expand_ratio: float = 0.25,
    iou_threshold: float = 0.05,
) -> bool:
    """True when a weapon belongs to this person, not merely the same frame."""
    region = expand_box(person_box, expand_ratio, frame_w, frame_h)
    cx, cy = box_center(weapon_box)
    if point_in_box(cx, cy, region):
        return True
    return box_iou(region, weapon_box) >= iou_threshold


def classify_persons_and_weapons(
    persons: List[Dict],
    weapons: List[Dict],
    frame_w: int,
    frame_h: int,
    expand_ratio: float = 0.25,
) -> Tuple[Optional[str], List[Dict], List[Dict]]:
    """
    Attach weapons to persons and return the frame-level event state.

    A weapon outside every person region is drawn locally but does not create
    PERSON WPN. A frame with no person never becomes WPN.
    """
    labeled_persons: List[Dict] = []
    any_armed = False

    for person in persons:
        armed = False
        for weapon in weapons:
            if weapon_associated_with_person(
                person["bbox"],
                weapon["bbox"],
                frame_w,
                frame_h,
                expand_ratio=expand_ratio,
            ):
                armed = True
        label = "PERSON WPN" if armed else "PERSON NO_WPN"
        any_armed = any_armed or armed
        labeled_persons.append({**person, "label": label, "armed": armed})

    if not labeled_persons:
        return None, labeled_persons, weapons
    return ("WPN" if any_armed else "NO_WPN"), labeled_persons, weapons


def draw_detections(
    frame,
    labeled_persons: List[Dict],
    weapons: List[Dict],
    overlay_text: str = "",
):
    """Draw person/weapon boxes. Display-only; does not change LoRa text."""
    import cv2

    out = frame
    for person in labeled_persons:
        x1, y1, x2, y2 = [int(v) for v in person["bbox"]]
        armed = person.get("armed", False)
        color = (0, 0, 255) if armed else (0, 200, 0)
        label = person.get("label", "PERSON")
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            out,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

    for weapon in weapons:
        x1, y1, x2, y2 = [int(v) for v in weapon["bbox"]]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 140, 255), 2)
        cv2.putText(
            out,
            "WPN",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 140, 255),
            2,
        )

    if overlay_text:
        cv2.putText(
            out,
            overlay_text,
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
    return out


class PersonDetector:
    """Lightweight person detector. Model is loaded once."""

    def __init__(
        self,
        backend: str = "yolo",
        model_path: str = "models/yolov8n.pt",
        confidence: float = 0.45,
        infer_size: int = 320,
    ):
        self.backend = backend.lower()
        self.model_path = model_path
        self.confidence = confidence
        self.infer_size = infer_size
        self.model_name = self.backend
        self._yolo = None
        self._hog = None
        self._load()

    def _load(self) -> None:
        import cv2

        if self.backend == "hog":
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self._hog = hog
            self.model_name = "opencv-hog"
            logger.info("Person detector: OpenCV HOG (no neural-net weights)")
            return

        if self.backend != "yolo":
            raise ValueError(f"Unknown detection backend: {self.backend}")

        from ultralytics import YOLO

        path = Path(self.model_path)
        load_target = str(path) if path.is_file() else "yolov8n.pt"
        if load_target == "yolov8n.pt" and not path.is_file():
            logger.warning(
                "Person model %s not found; ultralytics will fetch yolov8n.pt (~6MB)",
                self.model_path,
            )
        Path("models").mkdir(exist_ok=True)
        self._yolo = YOLO(load_target)
        self.model_name = Path(load_target).name
        logger.info("Person detector: YOLO %s imgsz=%s", self.model_name, self.infer_size)

    def detect(self, frame) -> List[Dict]:
        try:
            if self._hog is not None:
                return self._detect_hog(frame)
            return self._detect_yolo(frame)
        except Exception as exc:
            logger.warning("Person inference failed: %s", exc)
            return []

    def _detect_hog(self, frame) -> List[Dict]:
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        rects, weights = self._hog.detectMultiScale(
            gray,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        persons = []
        for (x, y, w, h), weight in zip(rects, weights):
            conf = float(weight[0]) if hasattr(weight, "__len__") else float(weight)
            if conf < self.confidence:
                continue
            persons.append(
                {
                    "bbox": [float(x), float(y), float(x + w), float(y + h)],
                    "confidence": conf,
                }
            )
        return persons

    def _detect_yolo(self, frame) -> List[Dict]:
        results = self._yolo.predict(
            frame,
            imgsz=self.infer_size,
            conf=self.confidence,
            classes=[0],
            verbose=False,
            device="cpu",
            max_det=10,
        )
        persons = []
        if not results:
            return persons
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return persons
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        for bbox, conf in zip(xyxy, confs):
            persons.append(
                {
                    "bbox": [float(v) for v in bbox],
                    "confidence": float(conf),
                }
            )
        return persons


class WeaponDetector:
    """
    Optional weapon model.

    Disabled when no file exists. This class never invents a weapon class from
    a COCO person model.
    """

    def __init__(
        self,
        model_path: str = "",
        class_names: Optional[List[str]] = None,
        confidence: float = 0.40,
        infer_size: int = 320,
    ):
        self.model_path = (model_path or "").strip()
        self.class_names = [name.lower() for name in (class_names or [])]
        self.confidence = confidence
        self.infer_size = infer_size
        self.enabled = False
        self.model_name = "disabled"
        self._yolo = None
        self._class_ids: Optional[List[int]] = None
        self._load()

    def _load(self) -> None:
        if not self.model_path:
            logger.info("Weapon detector: disabled (WEAPON_MODEL not set)")
            return
        path = Path(self.model_path)
        if not path.is_file():
            logger.warning(
                "Weapon detector: disabled (file not found: %s). "
                "PERSON WPN will not be emitted.",
                self.model_path,
            )
            return
        from ultralytics import YOLO

        self._yolo = YOLO(str(path))
        names = self._yolo.names if hasattr(self._yolo, "names") else {}
        if isinstance(names, dict):
            name_map = {int(k): str(v).lower() for k, v in names.items()}
        else:
            name_map = {i: str(v).lower() for i, v in enumerate(names)}

        if self.class_names:
            self._class_ids = [
                idx for idx, name in name_map.items() if name in self.class_names
            ]
            if not self._class_ids:
                logger.warning(
                    "Weapon model %s has no classes in %s (model classes: %s). "
                    "Weapon detector disabled.",
                    path.name,
                    self.class_names,
                    list(name_map.values()),
                )
                self._yolo = None
                return
        else:
            self._class_ids = None

        self.enabled = True
        self.model_name = path.name
        logger.info(
            "Weapon detector: %s classes=%s",
            self.model_name,
            [name_map[i] for i in (self._class_ids or name_map.keys())],
        )

    def detect_in_region(self, frame, person_box: Box) -> List[Dict]:
        if not self.enabled or self._yolo is None:
            return []
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in expand_box(person_box, 0.15, w, h)]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return []
        crop = frame[y1:y2, x1:x2]
        try:
            results = self._yolo.predict(
                crop,
                imgsz=self.infer_size,
                conf=self.confidence,
                classes=self._class_ids,
                verbose=False,
                device="cpu",
                max_det=5,
            )
        except Exception as exc:
            logger.warning("Weapon inference failed: %s", exc)
            return []

        found: List[Dict] = []
        if not results:
            return found
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return found
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        for bbox, conf in zip(xyxy, confs):
            found.append(
                {
                    "bbox": [
                        float(bbox[0] + x1),
                        float(bbox[1] + y1),
                        float(bbox[2] + x1),
                        float(bbox[3] + y1),
                    ],
                    "confidence": float(conf),
                }
            )
        return found


class FrameClassifier:
    """Run person detection, then optional per-person weapon classification."""

    def __init__(
        self,
        person_detector: PersonDetector,
        weapon_detector: Optional[WeaponDetector] = None,
        expand_ratio: float = 0.25,
        person_only: bool = False,
    ):
        self.person_detector = person_detector
        self.weapon_detector = weapon_detector
        self.expand_ratio = expand_ratio
        self.person_only = person_only

    def infer(self, frame) -> Tuple[Optional[str], List[Dict], List[Dict]]:
        persons = self.person_detector.detect(frame)
        if not persons:
            return None, [], []

        weapons: List[Dict] = []
        use_weapon = (
            not self.person_only
            and self.weapon_detector is not None
            and self.weapon_detector.enabled
        )
        if use_weapon:
            for person in persons:
                weapons.extend(
                    self.weapon_detector.detect_in_region(frame, person["bbox"])
                )

        h, w = frame.shape[:2]
        return classify_persons_and_weapons(
            persons,
            weapons,
            w,
            h,
            expand_ratio=self.expand_ratio,
        )
