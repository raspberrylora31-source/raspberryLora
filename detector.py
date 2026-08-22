"""
Person detection (YOLOv5n) plus required YOLOv5 weapon detection.

Full detection mode loads models/best.pt once at startup. A missing or invalid
weapon model is a hard error. PERSON NO_WPN is emitted only after the weapon
model has actually run on a person crop and found no configured weapon class.

Person-only camera tests skip the weapon model entirely and never emit
PERSON NO_WPN.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEAPON_MODEL = "models/best.pt"
DEFAULT_PERSON_MODEL = "models/yolov5n.pt"
YOLOV5N_URL = (
    "https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5n.pt"
)
PERSON_CLASS_NAMES = frozenset({"person", "people", "human"})
Box = Sequence[float]


class WeaponModelError(Exception):
    """Full detection cannot start or continue without a valid weapon model."""


class PersonModelError(Exception):
    """Person detector failed to load."""


def weapon_model_missing_message(path: str = DEFAULT_WEAPON_MODEL) -> str:
    return (
        "ERROR: Weapon detection is required but models/best.pt was not found.\n"
        "\n"
        "Please place the trained YOLOv5 weapon model at:\n"
        "\n"
        f"{path}\n"
    )


def inspect_class_names(names) -> Dict[int, str]:
    """Normalize a YOLOv5 names dict/list to {id: lowercase name}."""
    if names is None:
        return {}
    if isinstance(names, dict):
        return {int(key): str(value).strip().lower() for key, value in names.items()}
    return {index: str(value).strip().lower() for index, value in enumerate(names)}


def resolve_weapon_class_ids(
    name_map: Dict[int, str], configured: Optional[Sequence[str]] = None
) -> Tuple[List[int], List[str]]:
    """
    Choose weapon class ids from the model's real names.

    Empty configured list: use every non-person class (single-class models
    such as {0: weapon} work automatically).
    Explicit WEAPON_CLASSES: every listed name must exist; person is never
    treated as a weapon.
    """
    if not name_map:
        raise WeaponModelError(
            "ERROR: Weapon model has no class names. "
            "The file is not a usable YOLOv5 detection model."
        )

    configured_list = [str(name).strip().lower() for name in (configured or []) if str(name).strip()]
    model_names = [name_map[key] for key in sorted(name_map)]

    if configured_list:
        if any(name in PERSON_CLASS_NAMES for name in configured_list):
            raise WeaponModelError(
                "ERROR: WEAPON_CLASSES must not include a person class. "
                f"Configured={configured_list} model={model_names}"
            )
        missing = [name for name in configured_list if name not in model_names]
        if missing:
            raise WeaponModelError(
                "ERROR: Configured weapon class(es) were not found in the model.\n"
                f"Missing: {missing}\n"
                f"Model classes: {model_names}\n"
                "Set WEAPON_CLASSES to names that exist in models/best.pt."
            )
        selected = configured_list
    else:
        selected = [name for name in model_names if name not in PERSON_CLASS_NAMES]
        if not selected:
            raise WeaponModelError(
                "ERROR: Weapon model has no non-person classes.\n"
                f"Model classes: {model_names}\n"
                "This file cannot be used as a weapon detector."
            )

    class_ids = [idx for idx, name in name_map.items() if name in selected]
    if not class_ids:
        raise WeaponModelError(
            "ERROR: No weapon class ids resolved from the model.\n"
            f"Model classes: {model_names}"
        )
    return class_ids, [name_map[idx] for idx in class_ids]


def parse_yolov5_predictions(
    rows: Iterable,
    confidence_threshold: float,
    allowed_class_ids: Optional[Sequence[int]] = None,
) -> List[Dict]:
    """Parse YOLOv5 rows of [x1, y1, x2, y2, conf, cls]."""
    allowed = None if allowed_class_ids is None else set(int(v) for v in allowed_class_ids)
    detections: List[Dict] = []
    for row in rows:
        try:
            values = list(row)
        except TypeError:
            continue
        if len(values) < 6:
            continue
        try:
            x1, y1, x2, y2, conf, cls = values[:6]
            conf = float(conf)
            cls = int(float(cls))
        except (TypeError, ValueError):
            continue
        if conf < confidence_threshold:
            continue
        if allowed is not None and cls not in allowed:
            continue
        detections.append(
            {
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "confidence": conf,
                "class_id": cls,
            }
        )
    return detections


def ensure_yolov5n_weights(path: str = DEFAULT_PERSON_MODEL) -> Path:
    """Use local YOLOv5n weights, or fetch the official ~4MB nano file once."""
    dest = Path(path)
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading official YOLOv5n weights to %s", dest)
    try:
        import urllib.request

        tmp = dest.with_suffix(".pt.download")
        urllib.request.urlretrieve(YOLOV5N_URL, tmp)
        tmp.replace(dest)
    except Exception as exc:
        raise PersonModelError(
            "ERROR: Person weights models/yolov5n.pt were not found and download failed.\n"
            "On the Pi run:\n"
            f"  mkdir -p models && wget -O {dest} {YOLOV5N_URL}\n"
            f"Detail: {exc}"
        ) from exc
    if not dest.is_file():
        raise PersonModelError(
            f"ERROR: Failed to install YOLOv5n weights at {dest}"
        )
    return dest


def cuda_torch_arm_warning(torch_version: str, machine: str) -> Optional[str]:
    """Warn when a CUDA torch wheel is installed on ARM (common Pi SIGILL cause)."""
    version = (torch_version or "").lower()
    arch = (machine or "").lower()
    arm = any(token in arch for token in ("aarch64", "armv7", "armv8", "arm64", "arm"))
    if not arm:
        return None
    if "+cu" not in version and "cuda" not in version:
        return None
    return (
        "WARNING: PyTorch looks like a CUDA wheel "
        f"({torch_version}) on ARM ({machine}).\n"
        "The Pi has no NVIDIA GPU. That wheel can crash with "
        "Illegal instruction during YOLOv5 layer fusion.\n"
        "Reinstall CPU torch, then retry:\n"
        "  source venv/bin/activate\n"
        "  pip uninstall -y torch torchvision\n"
        "  pip freeze | grep -E '^(nvidia-|cuda-)' | cut -d= -f1 | xargs -r pip uninstall -y\n"
        "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu\n"
        "To prove the USB camera without YOLO: python3 app.py --person-only --display --backend hog\n"
    )


def _disable_ultralytics_fuse() -> None:
    """Skip ultralytics BaseModel.fuse(); it can SIGILL on some ARM torch wheels."""
    try:
        from ultralytics.nn.tasks import BaseModel

        def _skip_fuse(self, *args, **kwargs):
            return self

        BaseModel.fuse = _skip_fuse
    except Exception:
        pass


def _load_yolov5_ultralytics(weights_path: str):
    """Load YOLOv5 `.pt` weights through the ultralytics runtime (CPU, no fuse)."""
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise PersonModelError(
            "ERROR: The YOLOv5 runtime needs the ultralytics package.\n"
            "On the Pi run:\n"
            "  source venv/bin/activate\n"
            "  pip install ultralytics\n"
        ) from exc
    _disable_ultralytics_fuse()
    model = YOLO(str(weights_path))
    return model


def _load_yolov5(weights_or_name: str):
    """
    Load a YOLOv5 hub model once without fusing layers.

    Isolates torch.hub from this project on sys.path so the hub 'utils'
    package cannot collide with a local package. autoshape=False stops
    DetectMultiBackend from calling fuse() (SIGILL on CUDA aarch64 wheels).
    AutoShape is applied afterwards so model(image, size=...) still works.
    """
    import torch

    saved_path = sys.path[:]
    saved_modules = {
        key: sys.modules[key]
        for key in list(sys.modules)
        if key == "utils" or key.startswith("utils.")
    }
    project_root = str(PROJECT_ROOT.resolve())
    for key in saved_modules:
        sys.modules.pop(key, None)
    sys.path = [
        item
        for item in sys.path
        if os.path.abspath(item) != os.path.abspath(project_root)
    ]
    try:
        path = Path(weights_or_name)
        hub_repo = Path.home() / ".cache" / "torch" / "hub" / "ultralytics_yolov5_master"
        if hub_repo.is_dir():
            repo, source = str(hub_repo), "local"
        else:
            repo, source = "ultralytics/yolov5", "github"
        load_kw = {
            "source": source,
            "trust_repo": True,
            "verbose": False,
            "autoshape": False,
        }
        if path.is_file():
            model = torch.hub.load(repo, "custom", path=str(path), **load_kw)
        else:
            model = torch.hub.load(repo, weights_or_name, **load_kw)
        try:
            import models.common as common

            if not isinstance(model, common.AutoShape):
                model = common.AutoShape(model)
        except Exception:
            pass
        if hasattr(model, "to"):
            model.to("cpu")
        if hasattr(model, "eval"):
            model.eval()
        return model
    finally:
        sys.path = saved_path
        for key, module in saved_modules.items():
            sys.modules.setdefault(key, module)


def _predict_ultralytics(model, frame, infer_size, confidence, class_ids, max_det):
    results = model.predict(
        frame,
        imgsz=infer_size,
        conf=confidence,
        classes=class_ids,
        verbose=False,
        device="cpu",
        max_det=max_det,
    )
    if not results:
        return []
    boxes = getattr(results[0], "boxes", None)
    if boxes is None:
        return []
    rows = []
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    clss = boxes.cls.cpu().numpy()
    for bbox, conf, cls in zip(xyxy, confs, clss):
        rows.append([*bbox, conf, cls])
    return parse_yolov5_predictions(rows, confidence, allowed_class_ids=class_ids)


def _predict_hub(model, frame, infer_size, confidence, class_ids, max_det):
    import torch

    if hasattr(model, "conf"):
        model.conf = confidence
    if hasattr(model, "classes"):
        model.classes = class_ids
    if hasattr(model, "max_det"):
        model.max_det = max_det
    with torch.inference_mode():
        results = model(frame, size=infer_size)
    return parse_yolov5_predictions(
        _yolov5_xyxy(results),
        confidence,
        allowed_class_ids=class_ids,
    )


def _yolov5_xyxy(results) -> List:
    if results is None:
        return []
    if hasattr(results, "xyxy") and results.xyxy:
        tensor = results.xyxy[0]
    elif hasattr(results, "pred") and results.pred:
        tensor = results.pred[0]
    else:
        return []
    if tensor is None:
        return []
    if hasattr(tensor, "detach"):
        tensor = tensor.detach().cpu().numpy()
    return tensor


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
    width = x2 - x1
    height = y2 - y1
    dx = width * ratio
    dy = height * ratio
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
    PERSON WPN. A frame with no person never becomes WPN or NO_WPN.
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
    """Lightweight YOLOv5n person detector. Loaded once."""

    def __init__(
        self,
        backend: str = "yolov5",
        model_path: str = "models/yolov5n.pt",
        confidence: float = 0.45,
        infer_size: int = 320,
    ):
        self.backend = backend.lower()
        if self.backend == "yolo":
            self.backend = "yolov5"
        self.model_path = model_path
        self.confidence = confidence
        self.infer_size = infer_size
        self.model_name = self.backend
        self.class_names: Dict[int, str] = {}
        self.person_class_ids: List[int] = [0]
        self._model = None
        self._hog = None
        self._runtime = "none"
        self.runtime = "none"
        self._load()

    def _load(self) -> None:
        if self.backend == "hog":
            import cv2

            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self._hog = hog
            self.model_name = "opencv-hog"
            self._runtime = "hog"
            self.runtime = "hog"
            logger.info("Person detector: OpenCV HOG")
            return

        if self.backend != "yolov5":
            raise PersonModelError(f"Unknown person detection backend: {self.backend}")

        weights = ensure_yolov5n_weights(self.model_path)
        errors = []
        # Prefer ultralytics on the Pi. torch.hub YOLOv5 auto-fuses and can
        # die with "Illegal instruction" on CUDA aarch64 wheels.
        try:
            self._model = _load_yolov5_ultralytics(str(weights))
            self._runtime = "ultralytics"
        except Exception as ultra_exc:
            errors.append(f"ultralytics: {ultra_exc}")
            try:
                self._model = _load_yolov5(str(weights))
                self._runtime = "hub"
            except Exception as hub_exc:
                errors.append(f"torch.hub: {hub_exc}")
                raise PersonModelError(
                    "ERROR: Failed to load the YOLOv5 person model.\n"
                    f"Tried: {weights}\n"
                    "On the Pi run:\n"
                    "  source venv/bin/activate\n"
                    "  pip install ultralytics\n"
                    f"  mkdir -p models && wget -O {weights} {YOLOV5N_URL}\n"
                    "If you see Illegal instruction, pip installed a CUDA "
                    "torch wheel (+cu130). Reinstall CPU torch (see README), "
                    "or prove the camera with --backend hog.\n"
                    "Detail:\n  " + "\n  ".join(errors)
                ) from hub_exc

        names = getattr(self._model, "names", {0: "person"})
        self.class_names = inspect_class_names(names)
        person_ids = [
            idx for idx, name in self.class_names.items() if name in PERSON_CLASS_NAMES
        ]
        self.person_class_ids = person_ids or [0]
        if self._runtime == "hub":
            self._model.conf = self.confidence
            self._model.classes = self.person_class_ids
            self._model.max_det = 10
        self.model_name = weights.name
        self.runtime = self._runtime
        logger.info(
            "Person detector: YOLOv5n %s runtime=%s imgsz=%s classes=%s",
            self.model_name,
            self._runtime,
            self.infer_size,
            [self.class_names.get(i, str(i)) for i in self.person_class_ids],
        )

    def detect(self, frame) -> List[Dict]:
        try:
            if self._hog is not None:
                return self._detect_hog(frame)
            return self._detect_yolov5(frame)
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
                    "class_id": 0,
                }
            )
        return persons

    def _detect_yolov5(self, frame) -> List[Dict]:
        if self._runtime == "ultralytics":
            return _predict_ultralytics(
                self._model,
                frame,
                self.infer_size,
                self.confidence,
                self.person_class_ids,
                10,
            )
        return _predict_hub(
            self._model,
            frame,
            self.infer_size,
            self.confidence,
            self.person_class_ids,
            10,
        )


class WeaponDetector:
    """
    Required YOLOv5 weapon detector for full detection mode.

    Loads models/best.pt once. Never invents COCO classes as weapons.
    Never reports PERSON NO_WPN just because the file is missing.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_WEAPON_MODEL,
        class_names: Optional[List[str]] = None,
        confidence: float = 0.40,
        infer_size: int = 256,
        required: bool = True,
    ):
        self.model_path = (model_path or DEFAULT_WEAPON_MODEL).strip()
        self.configured_class_names = [name.lower() for name in (class_names or [])]
        self.confidence = confidence
        self.infer_size = infer_size
        self.required = required
        self.enabled = False
        self.model_name = "not-loaded"
        self.model_class_names: List[str] = []
        self.selected_class_names: List[str] = []
        self._class_ids: List[int] = []
        self._model = None
        self._runtime = "none"
        if required:
            self._load_required()

    def _load_required(self) -> None:
        path = Path(self.model_path)
        if not path.is_file():
            raise WeaponModelError(weapon_model_missing_message(self.model_path))

        errors = []
        try:
            self._model = _load_yolov5_ultralytics(str(path))
            self._runtime = "ultralytics"
        except Exception as ultra_exc:
            errors.append(f"ultralytics: {ultra_exc}")
            try:
                self._model = _load_yolov5(str(path))
                self._runtime = "hub"
            except WeaponModelError:
                raise
            except Exception as exc:
                errors.append(f"torch.hub: {exc}")
                raise WeaponModelError(
                    "ERROR: Failed to load the YOLOv5 weapon model.\n"
                    f"Path: {path}\n"
                    "The file must be a trained YOLOv5 weapon-detection weight "
                    "(not stock COCO YOLOv5, not YOLOv8).\n"
                    "If you see Illegal instruction, reinstall CPU torch "
                    "(see README).\n"
                    "Detail:\n  " + "\n  ".join(errors)
                ) from exc

        name_map = inspect_class_names(getattr(self._model, "names", None))
        if not name_map:
            raise WeaponModelError(
                "ERROR: Weapon model has no class names.\n"
                f"Path: {path}"
            )
        self.model_class_names = [name_map[key] for key in sorted(name_map)]
        self._class_ids, self.selected_class_names = resolve_weapon_class_ids(
            name_map, self.configured_class_names
        )
        if self._runtime == "hub":
            self._model.conf = self.confidence
            self._model.classes = self._class_ids
            self._model.max_det = 5

        try:
            self._warmup()
        except Exception as exc:
            raise WeaponModelError(
                "ERROR: Weapon model loaded but test inference failed.\n"
                f"Path: {path}\n"
                f"Detail: {exc}"
            ) from exc

        self.enabled = True
        self.model_name = path.name
        print("Weapon model:")
        print(f"Path: {path}")
        print(f"Classes: {self.model_class_names}")
        print("Weapon model loaded:")
        print(str(path))
        print(f"Runtime: {self._runtime} (fuse skipped)")
        print("Weapon classes:")
        print(str(self.model_class_names))
        print("Configured weapon classes:")
        print(str(self.selected_class_names))

    def _warmup(self) -> None:
        import numpy as np

        dummy = np.zeros((self.infer_size, self.infer_size, 3), dtype=np.uint8)
        self._infer(dummy)

    def detect_in_region(self, frame, person_box: Box) -> Tuple[List[Dict], bool]:
        """
        Run YOLOv5 on one expanded person crop.

        Returns (detections, inference_ok). inference_ok is False only when
        the model raised; a clean empty result is a real NO_WPN for that crop.
        """
        if not self.enabled or self._model is None:
            return [], False
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in expand_box(person_box, 0.15, width, height)]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return [], True
        crop = frame[y1:y2, x1:x2]
        try:
            items = self._infer(crop)
        except Exception as exc:
            logger.warning("Weapon inference failed: %s", exc)
            return [], False

        found: List[Dict] = []
        for item in items:
            box = item["bbox"]
            found.append(
                {
                    "bbox": [
                        float(box[0] + x1),
                        float(box[1] + y1),
                        float(box[2] + x1),
                        float(box[3] + y1),
                    ],
                    "confidence": item["confidence"],
                    "class_id": item["class_id"],
                }
            )
        return found, True

    def _infer(self, image) -> List[Dict]:
        if self._runtime == "ultralytics":
            return _predict_ultralytics(
                self._model,
                image,
                self.infer_size,
                self.confidence,
                self._class_ids,
                5,
            )
        return _predict_hub(
            self._model,
            image,
            self.infer_size,
            self.confidence,
            self._class_ids,
            5,
        )


class FrameClassifier:
    """Person boxes, then required per-person YOLOv5 weapon crops."""

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

        if self.person_only:
            labeled = [
                {**person, "label": "PERSON", "armed": False} for person in persons
            ]
            return None, labeled, []

        if self.weapon_detector is None or not self.weapon_detector.enabled:
            raise WeaponModelError(
                "ERROR: Weapon detection is required but the YOLOv5 weapon "
                "model is not loaded. Refusing PERSON NO_WPN.\n\n"
                "Please place the trained YOLOv5 weapon model at:\n\n"
                "models/best.pt\n"
            )

        weapons: List[Dict] = []
        ran_ok = True
        for person in persons:
            found, ok = self.weapon_detector.detect_in_region(frame, person["bbox"])
            if not ok:
                ran_ok = False
            weapons.extend(found)

        height, width = frame.shape[:2]
        state, labeled, weapons = classify_persons_and_weapons(
            persons,
            weapons,
            width,
            height,
            expand_ratio=self.expand_ratio,
        )
        # A failed weapon inference must not become a false NO_WPN.
        if state == "NO_WPN" and not ran_ok:
            return None, labeled, weapons
        return state, labeled, weapons
