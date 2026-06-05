"""
Model Loader - Optimized for Raspberry Pi 4B
Loads lightweight YOLO models for person and weapon detection
"""

import os
import sys
import torch
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_yolov5_from_hub(model_name: str = "yolov5n"):
    """
    Load YOLOv5 via torch.hub without conflicting with this project's `utils` package.
    """
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
        p for p in sys.path if os.path.abspath(p) != os.path.abspath(project_root)
    ]

    try:
        return torch.hub.load(
            "ultralytics/yolov5",
            model_name,
            pretrained=True,
            force_reload=False,
            verbose=False,
            trust_repo=True,
        )
    finally:
        sys.path = saved_path
        for key, module in saved_modules.items():
            sys.modules.setdefault(key, module)


class YOLOModelLoader:
    """
    Lightweight YOLO model loader optimized for Raspberry Pi.
    Uses YOLOv5n or YOLOv8n for minimal memory footprint.
    """

    # Model constants
    AVAILABLE_MODELS = {
        "yolov5n": "yolov5n.pt",
        "yolov8n": "yolov8n.pt",
    }

    DEVICE_AUTO = "cpu"  # Force CPU for Raspberry Pi - GPU not reliable
    CONFIDENCE_THRESHOLD = 0.45

    def __init__(self, model_name="yolov5n", model_dir="models", use_fp16=False):
        """
        Initialize model loader.

        Args:
            model_name: "yolov5n" or "yolov8n" (recommended for RPi)
            model_dir: Directory to store models
            use_fp16: Use half-precision (not recommended on RPi CPU)
        """
        self.model_name = model_name
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)
        self.use_fp16 = False  # Disable FP16 on CPU - slower
        self.device = self.DEVICE_AUTO
        self.model = None

    def load_model(self):
        """
        Load YOLO model with optimizations for Raspberry Pi.
        Uses in-built COCO weights (persons already included).
        """
        try:
            logger.info(f"Loading {self.model_name} model on {self.device}...")

            if self.model_name == "yolov5n":
                # YOLOv5 nano - ~7.5MB, ~2M params
                self.model = _load_yolov5_from_hub("yolov5n")
            elif self.model_name == "yolov8n":
                # YOLOv8 nano - ~6.3MB, ~3.2M params
                try:
                    from ultralytics import YOLO

                    model_path = self.model_dir / self.AVAILABLE_MODELS["yolov8n"]
                    self.model = YOLO(str(model_path))
                except ImportError:
                    logger.warning(
                        "YOLOv8 not available, falling back to YOLOv5n"
                    )
                    return self.load_model_yolov5n()
            else:
                raise ValueError(f"Unknown model: {self.model_name}")

            # Set model to eval mode and move to device
            if hasattr(self.model, "to"):
                self.model.to(self.device)
            if hasattr(self.model, "eval"):
                self.model.eval()

            logger.info(
                f"✓ Model loaded successfully on {self.device}"
            )
            return self.model

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def load_model_yolov5n(self):
        """Load YOLOv5n as fallback."""
        self.model = _load_yolov5_from_hub("yolov5n")
        self.model.to(self.device)
        self.model.eval()
        return self.model

    @staticmethod
    def get_class_indices():
        """
        COCO dataset class indices.
        Person is index 0, weapons not in standard COCO.
        """
        coco_classes = {
            0: "person",
            1: "bicycle",
            2: "car",
            # ... other classes (we mainly care about person for now)
        }
        return coco_classes

    @staticmethod
    def optimize_model_for_inference(model):
        """
        Apply inference-time optimizations for Raspberry Pi.
        """
        if hasattr(model, "half"):
            pass  # Skip half precision on CPU
        if hasattr(model, "fuse"):
            try:
                model.fuse()  # Fuse conv+bn layers
            except Exception as e:
                logger.warning(f"Could not fuse model: {e}")
        return model
