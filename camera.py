"""USB webcam capture with reconnect and small buffers."""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    """Grab frames from a USB camera or a video file. Never raises to callers."""

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 360,
        fps: int = 15,
        video_file: str = "",
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.video_file = video_file or ""
        self._cap: Optional[cv2.VideoCapture] = None
        self._last_open_attempt = 0.0
        self._open_retry_sec = 2.0

    def open(self) -> bool:
        """Open the camera or video file. Returns False on failure."""
        self.release()
        try:
            if self.video_file:
                cap = cv2.VideoCapture(self.video_file)
            else:
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
                if not cap.isOpened():
                    cap.release()
                    cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                logger.warning("Camera open failed: %s", self.source_name)
                return False

            if not self.video_file:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.fps)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._cap = cap
            logger.info("Camera opened: %s", self.source_name)
            return True
        except Exception as exc:
            logger.warning("Camera open error: %s", exc)
            self._cap = None
            return False

    @property
    def source_name(self) -> str:
        if self.video_file:
            return self.video_file
        return f"index {self.camera_index}"

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def read(self) -> Optional[np.ndarray]:
        """
        Return one BGR frame, or None if the camera is unavailable.

        Empty/failed frames do not crash the process. The camera is reopened
        on a short backoff if the device disappears.
        """
        if not self.is_open():
            now = time.monotonic()
            if now - self._last_open_attempt >= self._open_retry_sec:
                self._last_open_attempt = now
                self.open()
            return None

        try:
            ok, frame = self._cap.read()
        except Exception as exc:
            logger.warning("Camera read error: %s", exc)
            self.release()
            return None

        if not ok or frame is None or getattr(frame, "size", 0) == 0:
            if self.video_file and self._cap is not None:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                try:
                    ok, frame = self._cap.read()
                except Exception:
                    return None
                if ok and frame is not None and frame.size:
                    return frame
            logger.warning("Empty camera frame; will retry")
            self.release()
            return None

        return frame

    def release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
