"""
Local person detection on Raspberry Pi with Meshtastic UART events.

LoRa payload is a short TEXTMSG line such as:
    PERSON NO_WPN 2026-08-20 11:25:31
"""

from __future__ import annotations

import argparse
import logging
import platform
import signal
import sys
import time
from pathlib import Path

import cv2

from camera import Camera
from config import Config
from detector import FrameClassifier, PersonDetector, WeaponDetector, draw_detections
from event_manager import EventManager
from message_formatter import format_detection_message, format_timestamp
from uart_meshtastic import MeshtasticUART

logger = logging.getLogger(__name__)


def raspberry_pi_model() -> str:
    model_path = Path("/proc/device-tree/model")
    if model_path.is_file():
        try:
            return model_path.read_bytes().split(b"\x00", 1)[0].decode("utf-8", "replace")
        except Exception:
            pass
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(errors="replace").splitlines():
                if line.lower().startswith("model") or "raspberry" in line.lower():
                    return line.split(":", 1)[-1].strip() or "unknown"
        except Exception:
            pass
    return f"{platform.system()} {platform.machine()} (not a Raspberry Pi)"


def print_startup_diagnostics(cfg: Config, person: PersonDetector, weapon: WeaponDetector) -> None:
    weapon_name = weapon.model_name if weapon.enabled else "disabled"
    lines = [
        "=== startup ===",
        f"Raspberry Pi model : {raspberry_pi_model()}",
        f"Python             : {platform.python_version()}",
        f"OpenCV             : {cv2.__version__}",
        f"Person model       : {person.model_name} ({cfg.backend})",
        f"Weapon model       : {weapon_name}",
        f"Capture resolution : {cfg.frame_width}x{cfg.frame_height}",
        f"Inference size     : {cfg.infer_size}",
        f"Target infer FPS   : {cfg.target_inference_fps}",
        f"UART device        : {cfg.uart_port}",
        f"UART baud          : {cfg.uart_baud}",
        f"Display            : {cfg.enable_display}",
        "================",
    ]
    print("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raspberry Pi person detection -> Meshtastic TEXTMSG UART"
    )
    parser.add_argument("--camera", type=int, default=None, help="USB camera index")
    parser.add_argument("--video-file", default=None, help="Video file instead of camera")
    parser.add_argument("--width", type=int, default=None, help="Capture width")
    parser.add_argument("--height", type=int, default=None, help="Capture height")
    parser.add_argument("--infer-size", type=int, default=None, help="YOLO imgsz")
    parser.add_argument("--target-fps", type=float, default=None, help="Inference FPS cap")
    parser.add_argument(
        "--backend",
        choices=["yolo", "hog"],
        default=None,
        help="Person detector: yolov8n (default) or OpenCV HOG",
    )
    parser.add_argument("--person-model", default=None, help="YOLO weights path")
    parser.add_argument("--weapon-model", default=None, help="Optional weapon YOLO path")
    parser.add_argument("--person-confidence", type=float, default=None)
    parser.add_argument("--weapon-confidence", type=float, default=None)
    parser.add_argument("--confirmation-frames", type=int, default=None)
    parser.add_argument("--cooldown", type=float, default=None, help="Seconds")
    parser.add_argument("--state-change-only", action="store_true")
    parser.add_argument("--uart-port", default=None, help="UART device path")
    parser.add_argument("--uart-baud", type=int, default=None)
    parser.add_argument("--display", action="store_true", help="Show local preview")
    parser.add_argument("--person-only", action="store_true", help="Skip weapon model")
    parser.add_argument("--no-uart", action="store_true", help="Detect without UART send")
    return parser.parse_args()


class DetectionApp:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.running = True
        self.camera = Camera(
            camera_index=cfg.camera_index,
            width=cfg.frame_width,
            height=cfg.frame_height,
            fps=cfg.camera_fps,
            video_file=cfg.video_file,
        )
        self.person_detector = PersonDetector(
            backend=cfg.backend,
            model_path=cfg.person_model,
            confidence=cfg.person_confidence_threshold,
            infer_size=cfg.infer_size,
        )
        self.weapon_detector = WeaponDetector(
            model_path="" if cfg.person_only else cfg.weapon_model,
            class_names=cfg.weapon_class_list(),
            confidence=cfg.weapon_confidence_threshold,
            infer_size=cfg.infer_size,
        )
        self.classifier = FrameClassifier(
            person_detector=self.person_detector,
            weapon_detector=self.weapon_detector,
            expand_ratio=cfg.weapon_expand_ratio,
            person_only=cfg.person_only,
        )
        self.events = EventManager(
            confirmation_frames=cfg.confirmation_frames,
            cooldown_seconds=cfg.event_cooldown_seconds,
            state_change_only=cfg.state_change_only,
        )
        self.uart = None
        if not cfg.no_uart:
            self.uart = MeshtasticUART(port=cfg.uart_port, baud=cfg.uart_baud)

        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum, _frame) -> None:
        logger.info("Received signal %s", signum)
        self.running = False

    def run(self) -> None:
        print_startup_diagnostics(self.cfg, self.person_detector, self.weapon_detector)
        if self.uart is not None:
            if not self.uart.connect():
                logger.warning(
                    "UART not ready; detection continues and UART will retry"
                )

        min_interval = 0.0
        if self.cfg.target_inference_fps > 0:
            min_interval = 1.0 / self.cfg.target_inference_fps

        last_infer = 0.0
        last_fps_report = time.monotonic()
        infer_count = 0
        last_label = "NO PERSON"

        while self.running:
            frame = self.camera.read()
            if frame is None:
                time.sleep(0.1)
                continue

            now = time.monotonic()
            if min_interval and (now - last_infer) < min_interval:
                if self.cfg.enable_display:
                    display = draw_detections(frame, [], [], last_label)
                    cv2.imshow("Detection", display)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                continue

            last_infer = now
            state, persons, weapons = self.classifier.infer(frame)
            infer_count += 1

            emit_state = self.events.update(state, now=now)
            if emit_state is not None:
                try:
                    message = format_detection_message(
                        emit_state, format_timestamp()
                    )
                except ValueError as exc:
                    logger.warning("Malformed detection result: %s", exc)
                    message = None
                if message:
                    print(message)
                    last_label = message
                    if self.uart is not None:
                        self.uart.send_message(message)
            elif state is None:
                last_label = "NO PERSON"
            elif state == "WPN":
                last_label = "PERSON WPN"
            else:
                last_label = "PERSON NO_WPN"

            if now - last_fps_report >= 10.0:
                fps = infer_count / (now - last_fps_report)
                print(f"infer_fps={fps:.1f}")
                infer_count = 0
                last_fps_report = now

            if self.cfg.enable_display:
                display = draw_detections(frame, persons, weapons, last_label)
                cv2.imshow("Detection", display)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        self.shutdown()

    def shutdown(self) -> None:
        self.running = False
        self.camera.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        if self.uart is not None:
            self.uart.disconnect()
        logger.info("Shutdown complete")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = Config.from_env()
    cfg.apply_args(parse_args())
    try:
        DetectionApp(cfg).run()
        return 0
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
