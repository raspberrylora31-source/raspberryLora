"""
Object Detector - Person and Weapon Detection
Optimized for Raspberry Pi 4B
"""

import cv2
import torch
import logging
import numpy as np
from typing import Tuple, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ObjectDetector:
    """
    Lightweight object detector for person and weapon detection.
    Optimized for Raspberry Pi with minimal RAM/CPU usage.
    """

    # COCO classes
    PERSON_CLASS = 0

    # Weapon detection keywords (for post-processing)
    WEAPON_KEYWORDS = {
        "knife",
        "gun",
        "pistol",
        "rifle",
        "sword",
        "axe",
        "weapon",
        "firearm",
    }

    def __init__(
        self,
        model,
        confidence_threshold=0.45,
        skip_frames=2,
    ):
        """
        Initialize detector.

        Args:
            model: Loaded YOLO model
            confidence_threshold: Detection confidence (0-1)
            skip_frames: Skip N frames for performance (1=no skip)
        """
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.skip_frames = skip_frames
        self.frame_count = 0

        logger.info(
            f"Detector initialized: threshold={confidence_threshold}, skip={skip_frames}"
        )

    def preprocess_frame(self, frame, target_size=416) -> np.ndarray:
        """
        Preprocess frame for model input.
        Resizes to reduce computation while maintaining detection quality.

        Args:
            frame: Input frame from camera
            target_size: Target resolution (416 or 320 for extreme optimization)

        Returns:
            Preprocessed frame
        """
        # Resize to target size (significantly reduces computation)
        h, w = frame.shape[:2]
        aspect_ratio = w / h

        # Maintain aspect ratio
        if w > h:
            new_w = target_size
            new_h = int(target_size / aspect_ratio)
        else:
            new_h = target_size
            new_w = int(target_size * aspect_ratio)

        # Resize frame
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Pad to target size
        padded = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
        top = (target_size - new_h) // 2
        left = (target_size - new_w) // 2
        padded[top : top + new_h, left : left + new_w] = resized

        return padded

    @staticmethod
    def _extract_predictions(results):
        """
        Normalize supported YOLO result formats to prediction rows.

        YOLOv5 returns an object with ``pred`` tensors. Ultralytics YOLOv8
        returns a list of Results objects with bounding boxes on ``boxes.data``.
        Both row formats are [x1, y1, x2, y2, confidence, class].
        """
        if hasattr(results, "pred"):
            return results.pred[0]

        if isinstance(results, (list, tuple)) and results:
            first_result = results[0]
            if hasattr(first_result, "boxes") and first_result.boxes is not None:
                return first_result.boxes.data
            return first_result

        if hasattr(results, "boxes") and results.boxes is not None:
            return results.boxes.data

        return results

    def detect(self, frame) -> Tuple[bool, bool, Dict]:
        """
        Run object detection on frame.

        Args:
            frame: Input frame from camera

        Returns:
            Tuple: (person_detected, weapon_detected, detections_dict)
        """
        self.frame_count += 1

        # Frame skipping for performance optimization
        if self.frame_count % self.skip_frames != 0:
            return False, False, {}

        person_detected = False
        weapon_detected = False
        detections = {
            "persons": [],
            "weapons": [],
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Preprocess frame
            processed_frame = self.preprocess_frame(frame, target_size=416)

            # Run inference
            with torch.no_grad():
                results = self.model(processed_frame)

            # Process results
            predictions = self._extract_predictions(results)

            # Handle different model output formats
            if isinstance(predictions, (torch.Tensor, np.ndarray, list, tuple)):
                # YOLOv5 format: [x1, y1, x2, y2, conf, class]
                for pred in predictions:
                    values = pred
                    if isinstance(pred, torch.Tensor):
                        values = pred.detach().cpu().tolist()
                    elif hasattr(pred, "tolist"):
                        values = pred.tolist()

                    if len(values) >= 6:
                        x1, y1, x2, y2, conf, cls = values[:6]
                        conf = float(conf)
                        cls = int(cls)

                        if conf >= self.confidence_threshold:
                            if cls == self.PERSON_CLASS:
                                person_detected = True
                                detections["persons"].append(
                                    {
                                        "bbox": [
                                            float(x1),
                                            float(y1),
                                            float(x2),
                                            float(y2),
                                        ],
                                        "confidence": conf,
                                    }
                                )
                                logger.debug(
                                    f"Person detected (conf: {conf:.2f})"
                                )

            logger.debug(
                f"Frame {self.frame_count}: person={person_detected}, weapon={weapon_detected}"
            )

            # NOTE: For weapon detection, we would need a custom trained model
            # For now, weapon_detected remains False
            # Future improvement: Use a weapon-specific model or custom training

        except Exception as e:
            logger.error(f"Detection error: {e}")

        return person_detected, weapon_detected, detections

    def detect_combined(
        self, frame, model=None
    ) -> Tuple[str, Dict]:
        """
        Combined detection returning high-level classification.

        Args:
            frame: Input frame
            model: Optional alternative model

        Returns:
            Tuple: (entity_type, details)
            entity_type: "Person with weapon", "Person without weapon", or "No person"
        """
        m = model or self.model
        person_detected, weapon_detected, details = self.detect(frame)

        if person_detected:
            entity_type = (
                "Person with weapon"
                if weapon_detected
                else "Person without weapon"
            )
        else:
            entity_type = "No person"

        return entity_type, details

    @staticmethod
    def draw_detections(frame, entity_type: str, confidence: float = 0.0) -> np.ndarray:
        """
        Draw detection results on frame for display.

        Args:
            frame: Input frame
            entity_type: Type of entity detected
            confidence: Detection confidence

        Returns:
            Frame with annotations
        """
        color_map = {
            "Person with weapon": (0, 0, 255),  # Red
            "Person without weapon": (0, 255, 0),  # Green
            "No person": (128, 128, 128),  # Gray
        }

        color = color_map.get(entity_type, (255, 255, 255))
        text = f"{entity_type} ({confidence:.2f})"

        # Put text
        cv2.putText(
            frame,
            text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )

        # Put timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame,
            timestamp,
            (20, frame.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        return frame

    def get_stats(self) -> Dict:
        """Get detector statistics."""
        return {
            "frames_processed": self.frame_count,
            "model": self.model.__class__.__name__ if self.model else "None",
            "confidence_threshold": self.confidence_threshold,
            "skip_frames": self.skip_frames,
        }
