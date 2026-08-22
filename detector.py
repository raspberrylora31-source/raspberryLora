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
import platform
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
# Public YOLOv5 (not v8, not COCO) weapon weights. Inspected classes: gun, knife.
# Primary is YOLOv5s (~14 MB) from zaizou1003/knife_Gun_Detection (GitHub raw).
# Fallback is the GPL-3.0 chunmusic/Gun_Detection checkpoint.
WEAPON_WEIGHT_SOURCES = (
    {
        "url": (
            "https://raw.githubusercontent.com/zaizou1003/"
            "knife_Gun_Detection/main/exp6/weights/best.pt"
        ),
        "label": "YOLOv5s gun+knife (zaizou1003/knife_Gun_Detection)",
        "classes": ("gun", "knife"),
    },
    {
        "url": (
            "https://raw.githubusercontent.com/chunmusic/Gun_Detection/"
            "master/runs/train/exp13/weights/best.pt"
        ),
        "label": "YOLOv5s gun (chunmusic/Gun_Detection, GPL-3.0)",
        "classes": ("gun",),
    },
)
WEAPON_UNAVAILABLE = "ERROR: weapon detection unavailable"
PERSON_CLASS_NAMES = frozenset({"person", "people", "human"})
WEAPON_NAME_HINTS = frozenset(
    {
        "gun",
        "guns",
        "knife",
        "knives",
        "pistol",
        "rifle",
        "weapon",
        "weapons",
        "firearm",
        "firearms",
        "handgun",
        "shotgun",
        "revolver",
        "blade",
    }
)
COCO_TELLTALES = frozenset({"bicycle", "car", "dog", "chair", "tv", "toothbrush"})
Box = Sequence[float]


class WeaponModelError(Exception):
    """Full detection cannot start or continue without a valid weapon model."""


class PersonModelError(Exception):
    """Person detector failed to load."""


def weapon_model_missing_message(path: str = DEFAULT_WEAPON_MODEL) -> str:
    primary = WEAPON_WEIGHT_SOURCES[0]["url"]
    return (
        f"{WEAPON_UNAVAILABLE}\n"
        "\n"
        "Full detection needs a YOLOv5 weapon-class weight file.\n"
        f"Expected path: {path}\n"
        "\n"
        "Download the public YOLOv5s gun+knife weights:\n"
        "  python3 tools/download_weapon_model.py\n"
        "or:\n"
        f"  mkdir -p models && wget -O {DEFAULT_WEAPON_MODEL} {primary}\n"
        "\n"
        "Do not use stock COCO YOLOv5. Those have no weapon classes.\n"
        "A missing model is not PERSON NO_WPN.\n"
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

    if (
        not configured_list
        and not any(name in WEAPON_NAME_HINTS for name in model_names)
        and len(model_names) >= 70
        and len(set(model_names) & COCO_TELLTALES) >= 3
    ):
        raise WeaponModelError(
            f"{WEAPON_UNAVAILABLE}\n"
            "This looks like stock COCO YOLOv5, not a weapon model.\n"
            f"Model classes: {model_names[:12]} ...\n"
            "Download the gun+knife weights with:\n"
            "  python3 tools/download_weapon_model.py"
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


def _looks_like_yolov5_weights(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1_000_000:
        return False
    try:
        header = path.read_bytes()[:8]
    except OSError:
        return False
    return header[:2] == b"PK" or header[:1] == b"\x80"


def _download_file(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".download")
    logger.info("Downloading %s", url)
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


def ensure_weapon_weights(
    path: str = DEFAULT_WEAPON_MODEL, download: bool = True
) -> Path:
    """
    Return a local YOLOv5 weapon weight file.

    If the default models/best.pt is missing, download the public YOLOv5s
    gun+knife checkpoint. Custom paths are never silently replaced.
    """
    dest = Path(path)
    if not dest.is_absolute():
        dest = PROJECT_ROOT / dest
    if _looks_like_yolov5_weights(dest):
        return dest

    default_dest = (PROJECT_ROOT / DEFAULT_WEAPON_MODEL).resolve()
    if dest.resolve() != default_dest or not download:
        raise WeaponModelError(weapon_model_missing_message(str(dest)))

    errors = []
    for source in WEAPON_WEIGHT_SOURCES:
        try:
            print(f"Downloading weapon model: {source['label']}")
            print(source["url"])
            _download_file(source["url"], dest)
            if _looks_like_yolov5_weights(dest):
                print(f"Saved {dest} ({dest.stat().st_size} bytes)")
                return dest
            errors.append(f"{source['label']}: file was not a YOLOv5 .pt")
        except Exception as exc:
            errors.append(f"{source['label']}: {exc}")
            if dest.exists() and not _looks_like_yolov5_weights(dest):
                dest.unlink()

    raise WeaponModelError(
        f"{WEAPON_UNAVAILABLE}\n"
        "\n"
        "Could not download a public YOLOv5 weapon model.\n"
        f"Tried to write: {dest}\n"
        "Detail:\n  " + "\n  ".join(errors) + "\n"
        "\n"
        "Place a YOLOv5 weapon-class .pt at models/best.pt and retry.\n"
        "Do not use stock COCO weights. A missing model is not PERSON NO_WPN."
    )


PI4_TORCH = "2.3.1"
PI4_TORCHVISION = "0.18.1"


def _is_arm_machine(machine: str) -> bool:
    arch = (machine or "").lower()
    return any(token in arch for token in ("aarch64", "armv7", "armv8", "arm64", "arm"))


def _is_cuda_torch(torch_version: str) -> bool:
    version = (torch_version or "").lower()
    return "+cu" in version or "cuda" in version


def parse_torch_version(torch_version: str) -> Tuple[int, int, int]:
    core = (torch_version or "").split("+", 1)[0].strip()
    parts = core.split(".")
    if len(parts) < 2:
        raise ValueError(torch_version)
    major = int(parts[0])
    minor = int(parts[1])
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return major, minor, patch


def cpu_has_arm_lse(cpuinfo: str) -> bool:
    """True when /proc/cpuinfo advertises ARMv8.1 LSE atomics."""
    return "atomics" in (cpuinfo or "").lower()


def torch_is_pi4_safe(torch_version: str) -> bool:
    """Pi 4 Cortex-A72 is ARMv8.0. Official wheels from 2.4+ often SIGILL (LSE)."""
    if _is_cuda_torch(torch_version):
        return False
    try:
        major, minor, _patch = parse_torch_version(torch_version)
    except (TypeError, ValueError):
        return False
    return (major, minor) <= (2, 3)


def unsafe_torch_message(
    torch_version: str,
    machine: str,
    cpuinfo: Optional[str] = None,
) -> Optional[str]:
    """
    Return a hard-error string when this ARM board cannot run the installed torch.

    Raspberry Pi 4 (no LSE) dies with Illegal instruction on CUDA wheels and on
    current official 2.10+/2.13 wheels. A warning is not enough: the process
    is killed by SIGILL on first inference.
    """
    if not _is_arm_machine(machine):
        return None
    if cpuinfo is None:
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(errors="replace")
        except Exception:
            cpuinfo = ""
    has_lse = cpu_has_arm_lse(cpuinfo)
    cuda = _is_cuda_torch(torch_version)
    too_new_for_pi4 = (not has_lse) and (not torch_is_pi4_safe(torch_version))
    if not cuda and not too_new_for_pi4:
        return None
    reason = (
        f"CUDA wheel {torch_version} on ARM ({machine})"
        if cuda
        else f"PyTorch {torch_version} uses ARMv8.1+ instructions this Pi 4 CPU does not have"
    )
    return (
        "ERROR: Refusing to start YOLOv5. The installed PyTorch will kill the "
        "process with Illegal instruction.\n"
        f"Detail: {reason}.\n"
        "Raspberry Pi 4 (Cortex-A72) needs a CPU torch build from the 2.3 line, "
        "not CUDA and not current 2.10+/2.13 wheels.\n"
        "\n"
        "On the Pi:\n"
        "  source venv/bin/activate\n"
        "  bash tools/fix_pi_torch.sh\n"
        "\n"
        "Or by hand:\n"
        "  pip uninstall -y torch torchvision torchaudio\n"
        "  pip freeze | grep -E '^(nvidia-|cuda-)' | cut -d= -f1 | xargs -r pip uninstall -y\n"
        f"  pip install torch=={PI4_TORCH} torchvision=={PI4_TORCHVISION}\n"
        "  python3 -c \"import torch; print(torch.__version__); print(torch.zeros(1)+1)\"\n"
        "\n"
        "Then:\n"
        "  python3 app.py --person-only --display\n"
        "\n"
        "Camera only, no YOLO:\n"
        "  python3 app.py --person-only --display --backend hog\n"
    )


def cuda_torch_arm_warning(
    torch_version: str,
    machine: str,
    cpuinfo: Optional[str] = None,
) -> Optional[str]:
    """Alias used by startup diagnostics; same text as unsafe_torch_message."""
    return unsafe_torch_message(torch_version, machine, cpuinfo=cpuinfo)


def raise_if_unsafe_torch() -> None:
    """Abort YOLO load before the first inference can SIGILL."""
    try:
        import torch

        version = getattr(torch, "__version__", "unknown")
    except Exception:
        return
    message = unsafe_torch_message(version, platform.machine())
    if message:
        raise PersonModelError(message)


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


def _yolov5_hub_repo() -> Path:
    return Path.home() / ".cache" / "torch" / "hub" / "ultralytics_yolov5_master"


def _sys_path_without_project_shadows(extra_first: Optional[Path] = None) -> List[str]:
    """
    torch.hub YOLOv5 imports `models.common`. This repo has a data directory
    named models/ (weights), which shadows that package if cwd is on sys.path.
    """
    blocked = {
        str(PROJECT_ROOT.resolve()),
        os.path.abspath(os.getcwd()),
        "",
        ".",
    }
    cleaned = []
    for item in sys.path:
        if item in blocked:
            continue
        try:
            if os.path.abspath(item) in blocked:
                continue
        except Exception:
            pass
        cleaned.append(item)
    if extra_first is not None and extra_first.is_dir():
        cleaned.insert(0, str(extra_first))
    return cleaned


def _purge_shadow_modules() -> Dict[str, object]:
    saved = {}
    for key in list(sys.modules):
        if key in {"models", "utils"} or key.startswith(("models.", "utils.")):
            saved[key] = sys.modules.pop(key)
    return saved


def _load_yolov5(weights_or_name: str):
    """
    Load a classic YOLOv5 checkpoint via torch.hub.

    Official `ultralytics` YOLO() rejects custom YOLOv5 train.py weights
    ("NOT forwards compatible with YOLOv8"). Hub load must not see this
    project's models/ folder.
    """
    import torch

    saved_path = sys.path[:]
    saved_modules = _purge_shadow_modules()
    hub_repo = _yolov5_hub_repo()
    sys.path = _sys_path_without_project_shadows(
        extra_first=hub_repo if (hub_repo / "hubconf.py").is_file() else None
    )
    try:
        path = Path(weights_or_name)
        load_kw = {
            "trust_repo": True,
            "verbose": False,
            "autoshape": True,
        }
        model = None
        errors = []
        if path.is_file() and (hub_repo / "hubconf.py").is_file():
            try:
                model = torch.hub.load(
                    str(hub_repo), "custom", path=str(path), source="local", **load_kw
                )
            except Exception as exc:
                errors.append(f"local hub: {exc}")
                model = None
        if model is None:
            repo = "ultralytics/yolov5"
            try:
                if path.is_file():
                    model = torch.hub.load(
                        repo, "custom", path=str(path), source="github", **load_kw
                    )
                else:
                    model = torch.hub.load(
                        repo, weights_or_name, source="github", **load_kw
                    )
            except Exception as exc:
                errors.append(f"github hub: {exc}")
                raise RuntimeError(
                    "torch.hub could not load classic YOLOv5 weights.\n  "
                    + "\n  ".join(errors)
                ) from exc
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
        # Preview boxes look like a normal model: PERSON, or PERSON WPN
        # when a weapon is associated. UART still uses WPN / NO_WPN.
        label = "PERSON WPN" if armed else "PERSON"
        any_armed = any_armed or armed
        labeled_persons.append({**person, "label": label, "armed": armed})

    if not labeled_persons:
        return None, labeled_persons, weapons
    return ("WPN" if any_armed else "NO_WPN"), labeled_persons, weapons


def display_overlay_label(state: Optional[str], persons: Sequence[Dict]) -> str:
    """Local preview banner. Mesh text is still PERSON WPN / PERSON NO_WPN."""
    if state == "WPN":
        return "PERSON WPN"
    if persons:
        return "PERSON"
    return "NO PERSON EVENT"


def _draw_box(out, box: Box, label: str, color) -> None:
    import cv2

    x1, y1, x2, y2 = [int(v) for v in box]
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


def draw_detections(
    frame,
    labeled_persons: List[Dict],
    weapons: List[Dict],
    overlay_text: str = "",
    others: Optional[List[Dict]] = None,
):
    """Draw person / weapon / other-object boxes. Display-only."""
    import cv2

    out = frame
    for person in labeled_persons:
        armed = person.get("armed", False)
        color = (0, 0, 255) if armed else (0, 200, 0)
        _draw_box(out, person["bbox"], person.get("label", "PERSON"), color)

    for weapon in weapons:
        name = str(weapon.get("class_name") or weapon.get("label") or "WPN")
        _draw_box(out, weapon["bbox"], name.upper(), (0, 140, 255))

    for obj in others or []:
        name = str(obj.get("class_name") or obj.get("label") or "object")
        _draw_box(out, obj["bbox"], name, (255, 180, 0))

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

        raise_if_unsafe_torch()
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
            self._model.classes = None
            self._model.max_det = 20
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
        persons, _others = self.detect_scene(frame)
        return persons

    def detect_scene(self, frame) -> Tuple[List[Dict], List[Dict]]:
        """Persons for events, plus other scene classes for display only."""
        try:
            if self._hog is not None:
                return self._detect_hog(frame), []
            rows = self._detect_yolov5(frame)
        except Exception as exc:
            logger.warning("Person inference failed: %s", exc)
            return [], []
        persons: List[Dict] = []
        others: List[Dict] = []
        for item in rows:
            name = self.class_names.get(item["class_id"], str(item["class_id"]))
            labeled = {**item, "class_name": name, "label": name}
            if item["class_id"] in self.person_class_ids or name in PERSON_CLASS_NAMES:
                persons.append(labeled)
            else:
                others.append(labeled)
        return persons, others

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
                    "class_name": "person",
                    "label": "person",
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
                None,
                20,
            )
        return _predict_hub(
            self._model,
            frame,
            self.infer_size,
            self.confidence,
            None,
            20,
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
        self._name_map: Dict[int, str] = {}
        self._class_ids: List[int] = []
        self._model = None
        self._runtime = "none"
        if required:
            self._load_required()

    def _load_required(self) -> None:
        try:
            path = ensure_weapon_weights(self.model_path, download=True)
        except WeaponModelError:
            raise

        try:
            raise_if_unsafe_torch()
        except PersonModelError as exc:
            raise WeaponModelError(
                f"{WEAPON_UNAVAILABLE}\n{exc}"
            ) from exc

        errors = []
        # Custom YOLOv5 train.py weights are not loadable by ultralytics YOLO().
        # Use torch.hub first. Keep the project's models/ weights dir off sys.path.
        try:
            self._model = _load_yolov5(str(path))
            self._runtime = "hub"
        except Exception as hub_exc:
            errors.append(f"torch.hub: {hub_exc}")
            try:
                self._model = _load_yolov5_ultralytics(str(path))
                self._runtime = "ultralytics"
            except Exception as ultra_exc:
                errors.append(f"ultralytics: {ultra_exc}")
                raise WeaponModelError(
                    f"{WEAPON_UNAVAILABLE}\n"
                    "Failed to load the YOLOv5 weapon model.\n"
                    f"Path: {path}\n"
                    "This file is a classic YOLOv5 checkpoint and must load "
                    "through torch.hub, not the ultralytics YOLOv8 package.\n"
                    "Detail:\n  " + "\n  ".join(errors)
                ) from ultra_exc

        name_map = inspect_class_names(getattr(self._model, "names", None))
        if not name_map:
            raise WeaponModelError(
                f"{WEAPON_UNAVAILABLE}\n"
                "Weapon model has no class names.\n"
                f"Path: {path}"
            )
        self._name_map = name_map
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
                f"{WEAPON_UNAVAILABLE}\n"
                "Weapon model loaded but test inference failed.\n"
                f"Path: {path}\n"
                f"Detail: {exc}"
            ) from exc

        self.enabled = True
        self.model_name = path.name
        print(f"Weapon model loaded: {path}")
        print(f"Weapon classes: {self.model_class_names}")
        print(f"Configured weapon classes: {self.selected_class_names}")
        print(f"Weapon runtime: {self._runtime} (fuse skipped)")

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
            class_id = item["class_id"]
            class_name = self._name_map.get(class_id, "weapon")
            found.append(
                {
                    "bbox": [
                        float(box[0] + x1),
                        float(box[1] + y1),
                        float(box[2] + x1),
                        float(box[3] + y1),
                    ],
                    "confidence": item["confidence"],
                    "class_id": class_id,
                    "class_name": class_name,
                    "label": class_name,
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

    def infer(
        self, frame
    ) -> Tuple[Optional[str], List[Dict], List[Dict], List[Dict]]:
        persons, others = self.person_detector.detect_scene(frame)
        if not persons:
            return None, [], [], others

        if self.person_only:
            labeled = [
                {**person, "label": "PERSON", "armed": False} for person in persons
            ]
            return None, labeled, [], others

        if self.weapon_detector is None or not self.weapon_detector.enabled:
            raise WeaponModelError(
                f"{WEAPON_UNAVAILABLE}\n"
                "The YOLOv5 weapon model is not loaded. "
                "Refusing PERSON NO_WPN.\n"
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
            return None, labeled, weapons, others
        return state, labeled, weapons, others
