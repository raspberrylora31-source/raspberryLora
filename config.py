"""Application configuration from environment variables and defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    """Runtime configuration. Environment variables override defaults."""

    uart_port: str = "/dev/serial0"
    uart_baud: int = 38400
    camera_index: int = 0
    video_file: str = ""
    frame_width: int = 640
    frame_height: int = 360
    camera_fps: int = 15
    infer_size: int = 320
    target_inference_fps: float = 7.0
    backend: str = "yolo"
    person_model: str = "models/yolov8n.pt"
    weapon_model: str = ""
    weapon_classes: str = "gun,pistol,rifle,weapon,firearm"
    person_confidence_threshold: float = 0.45
    weapon_confidence_threshold: float = 0.40
    weapon_expand_ratio: float = 0.25
    confirmation_frames: int = 3
    event_cooldown_seconds: float = 30.0
    state_change_only: bool = False
    enable_display: bool = False
    person_only: bool = False
    no_uart: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            uart_port=_env_str("UART_PORT", "/dev/serial0"),
            uart_baud=_env_int("UART_BAUD", 38400),
            camera_index=_env_int("CAMERA_INDEX", 0),
            video_file=_env_str("VIDEO_FILE", ""),
            frame_width=_env_int("FRAME_WIDTH", 640),
            frame_height=_env_int("FRAME_HEIGHT", 360),
            camera_fps=_env_int("CAMERA_FPS", 15),
            infer_size=_env_int("INFER_SIZE", 320),
            target_inference_fps=_env_float("TARGET_INFERENCE_FPS", 7.0),
            backend=_env_str("DETECTION_BACKEND", "yolo").lower(),
            person_model=_env_str("PERSON_MODEL", "models/yolov8n.pt"),
            weapon_model=_env_str("WEAPON_MODEL", ""),
            weapon_classes=_env_str(
                "WEAPON_CLASSES", "gun,pistol,rifle,weapon,firearm"
            ),
            person_confidence_threshold=_env_float(
                "PERSON_CONFIDENCE_THRESHOLD", 0.45
            ),
            weapon_confidence_threshold=_env_float(
                "WEAPON_CONFIDENCE_THRESHOLD", 0.40
            ),
            weapon_expand_ratio=_env_float("WEAPON_EXPAND_RATIO", 0.25),
            confirmation_frames=_env_int("CONFIRMATION_FRAMES", 3),
            event_cooldown_seconds=_env_float("EVENT_COOLDOWN_SECONDS", 30.0),
            state_change_only=_env_bool("STATE_CHANGE_ONLY", False),
            enable_display=_env_bool("ENABLE_DISPLAY", False),
            person_only=_env_bool("PERSON_ONLY", False),
            no_uart=_env_bool("NO_UART", False),
        )

    def apply_args(self, args) -> None:
        """Overlay argparse values when the flag was explicitly provided."""
        mapping = {
            "uart_port": "uart_port",
            "uart_baud": "uart_baud",
            "camera": "camera_index",
            "video_file": "video_file",
            "width": "frame_width",
            "height": "frame_height",
            "infer_size": "infer_size",
            "target_fps": "target_inference_fps",
            "backend": "backend",
            "person_model": "person_model",
            "weapon_model": "weapon_model",
            "person_confidence": "person_confidence_threshold",
            "weapon_confidence": "weapon_confidence_threshold",
            "confirmation_frames": "confirmation_frames",
            "cooldown": "event_cooldown_seconds",
        }
        for arg_name, field_name in mapping.items():
            value = getattr(args, arg_name, None)
            if value is not None:
                setattr(self, field_name, value)

        if getattr(args, "display", False):
            self.enable_display = True
        if getattr(args, "person_only", False):
            self.person_only = True
        if getattr(args, "no_uart", False):
            self.no_uart = True
        if getattr(args, "state_change_only", False):
            self.state_change_only = True

    def weapon_class_list(self) -> list:
        return [
            item.strip().lower()
            for item in self.weapon_classes.split(",")
            if item.strip()
        ]

    def as_startup_dict(self) -> dict:
        return {field.name: getattr(self, field.name) for field in fields(self)}
