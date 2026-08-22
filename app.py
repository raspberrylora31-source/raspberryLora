"""
USB webcam person + YOLOv5 weapon detection on a Raspberry Pi.

Confirmed events are sent as compact TEXTMSG lines over GPIO UART to a
LILYGO T-Beam running Meshtastic. Images and video are never sent over LoRa.
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import signal
import sys
import time
from pathlib import Path

from camera import Camera, CameraOpenError, USB_CAMERA_ERROR
from config import Config
from detector import (
    FrameClassifier,
    PersonDetector,
    PersonModelError,
    WeaponDetector,
    WeaponModelError,
    cuda_torch_arm_warning,
    draw_detections,
)
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


def pytorch_version() -> str:
    try:
        import torch

        return torch.__version__
    except Exception:
        return "not imported"


def opencv_version() -> str:
    try:
        import cv2

        return cv2.__version__
    except Exception:
        return "not imported"


def process_rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


def process_cpu_seconds() -> float:
    try:
        with open("/proc/self/stat", encoding="utf-8") as handle:
            parts = handle.read().split()
        ticks = os.sysconf("SC_CLK_TCK")
        return (int(parts[13]) + int(parts[14])) / float(ticks)
    except Exception:
        return 0.0


class ResourceMonitor:
    """Low-frequency FPS / RAM / CPU reporter."""

    def __init__(self):
        now = time.monotonic()
        self._window_start = now
        self._infer_count = 0
        self._cpu_start = process_cpu_seconds()
        self.last_fps = 0.0

    def mark_inference(self) -> None:
        self._infer_count += 1

    def maybe_report(self, now: float, interval: float = 10.0) -> None:
        if now - self._window_start < interval:
            return
        elapsed = max(now - self._window_start, 1e-6)
        self.last_fps = self._infer_count / elapsed
        cpu_now = process_cpu_seconds()
        cpu_pct = max(0.0, (cpu_now - self._cpu_start) / elapsed * 100.0)
        ram_mb = process_rss_mb()
        print(f"FPS: {self.last_fps:.1f}")
        print(f"RAM: {ram_mb:.0f} MB")
        print(f"CPU: {cpu_pct:.0f}%")
        self._window_start = now
        self._infer_count = 0
        self._cpu_start = cpu_now


def print_startup_diagnostics(
    cfg: Config, person: PersonDetector, weapon: WeaponDetector | None
) -> None:
    if cfg.person_only:
        weapon_name = "not loaded (person-only test)"
        weapon_infer = "n/a"
    elif weapon is not None and weapon.enabled:
        weapon_name = f"{weapon.model_name} {weapon.selected_class_names}"
        weapon_infer = str(cfg.weapon_infer_size)
    else:
        weapon_name = "ERROR not loaded"
        weapon_infer = str(cfg.weapon_infer_size)

    lines = [
        "=== startup ===",
        f"Raspberry Pi model : {raspberry_pi_model()}",
        f"Python             : {platform.python_version()}",
        f"OpenCV             : {opencv_version()}",
        f"PyTorch            : {pytorch_version()}",
        f"Person model       : {person.model_name} ({cfg.backend}/{person.runtime})",
        f"Weapon model       : {weapon_name}",
        f"Camera resolution  : {cfg.frame_width}x{cfg.frame_height}",
        f"Person infer size  : {cfg.person_infer_size}",
        f"Weapon infer size  : {weapon_infer}",
        f"Target infer FPS   : {cfg.target_inference_fps}",
        f"UART device        : {cfg.uart_port}",
        f"UART baud          : {cfg.uart_baud}",
        f"Display            : {cfg.enable_display}",
        f"Mode               : {_mode_name(cfg)}",
        "================",
    ]
    print("\n".join(lines))
    warning = cuda_torch_arm_warning(pytorch_version(), platform.machine())
    if warning:
        print(warning, file=sys.stderr)


def _mode_name(cfg: Config) -> str:
    if cfg.person_only:
        return "person-only camera test"
    if cfg.no_uart:
        return "full detection without UART"
    return "full detection + UART"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raspberry Pi person + YOLOv5 weapon detection -> Meshtastic TEXTMSG"
    )
    parser.add_argument("--camera", type=int, default=None, help="USB camera index")
    parser.add_argument("--video-file", default=None, help="Video file instead of camera")
    parser.add_argument(
        "--image",
        default=None,
        help="Still image instead of camera (weapon test without a live webcam)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Stop after N inference frames (still-image / video tests)",
    )
    parser.add_argument(
        "--save-preview",
        default=None,
        help="Write the last annotated frame to this image path",
    )
    parser.add_argument("--width", type=int, default=None, help="Capture width")
    parser.add_argument("--height", type=int, default=None, help="Capture height")
    parser.add_argument("--person-infer-size", type=int, default=None)
    parser.add_argument("--weapon-infer-size", type=int, default=None)
    parser.add_argument("--infer-size", type=int, default=None, help="Alias for person infer size")
    parser.add_argument("--target-fps", type=float, default=None, help="Inference FPS cap")
    parser.add_argument(
        "--backend",
        choices=["yolov5", "yolo", "hog"],
        default=None,
        help="Person detector: yolov5n (default) or OpenCV HOG",
    )
    parser.add_argument("--person-model", default=None, help="YOLOv5n weights path")
    parser.add_argument("--weapon-model", default=None, help="YOLOv5 weapon weights (models/best.pt)")
    parser.add_argument("--weapon-classes", default=None, help="Comma-separated model class names")
    parser.add_argument("--person-confidence", type=float, default=None)
    parser.add_argument("--weapon-confidence", type=float, default=None)
    parser.add_argument("--confirmation-frames", type=int, default=None)
    parser.add_argument("--cooldown", type=float, default=None, help="Seconds")
    parser.add_argument("--state-change-only", action="store_true")
    parser.add_argument("--uart-port", default=None, help="UART device path")
    parser.add_argument("--uart-baud", type=int, default=None)
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--display", action="store_true", help="Show local preview")
    display.add_argument(
        "--no-display",
        action="store_true",
        help="Headless mode (no X/desktop required)",
    )
    parser.add_argument(
        "--person-only",
        action="store_true",
        help="USB camera + person boxes only (no weapon model, no UART)",
    )
    parser.add_argument(
        "--no-uart",
        action="store_true",
        help="Full person+weapon test without UART/T-Beam",
    )
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
            infer_size=cfg.person_infer_size,
        )
        self.weapon_detector = None
        if not cfg.person_only:
            self.weapon_detector = WeaponDetector(
                model_path=cfg.weapon_model,
                class_names=cfg.weapon_class_list(),
                confidence=cfg.weapon_confidence_threshold,
                infer_size=cfg.weapon_infer_size,
                required=True,
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
        if not cfg.no_uart and not cfg.person_only:
            self.uart = MeshtasticUART(port=cfg.uart_port, baud=cfg.uart_baud)

        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum, _frame) -> None:
        logger.info("Received signal %s", signum)
        self.running = False

    def run(self) -> None:
        print_startup_diagnostics(self.cfg, self.person_detector, self.weapon_detector)
        try:
            self.camera.open_or_raise()
        except CameraOpenError as exc:
            print(str(exc), file=sys.stderr)
            self.shutdown()
            raise

        if self.uart is not None:
            if not self.uart.connect():
                logger.warning(
                    "UART not ready; detection continues and UART will retry"
                )

        min_interval = 0.0
        if self.cfg.target_inference_fps > 0:
            min_interval = 1.0 / self.cfg.target_inference_fps

        last_infer = 0.0
        last_label = "NO PERSON EVENT"
        monitor = ResourceMonitor()
        persons: list = []
        weapons: list = []
        infer_count = 0
        last_preview = None

        while self.running:
            frame = self.camera.read()
            if frame is None:
                time.sleep(0.1)
                continue

            now = time.monotonic()
            if min_interval and (now - last_infer) < min_interval:
                if self.cfg.enable_display:
                    self._show(frame, persons, weapons, last_label, monitor.last_fps)
                del frame
                continue

            last_infer = now
            try:
                state, persons, weapons = self.classifier.infer(frame)
            except WeaponModelError as exc:
                print(str(exc), file=sys.stderr)
                break
            except Exception as exc:
                logger.warning("Inference error: %s", exc)
                state, persons, weapons = None, [], []
            monitor.mark_inference()

            emit_state = None
            if not self.cfg.person_only:
                emit_state = self.events.update(state, now=now)
            if emit_state is not None:
                try:
                    message = format_detection_message(emit_state, format_timestamp())
                except ValueError as exc:
                    logger.warning("Malformed detection result: %s", exc)
                    message = None
                if message:
                    print(message)
                    last_label = message
                    if self.uart is not None:
                        self.uart.send_message(message)
            elif self.cfg.person_only:
                last_label = "PERSON" if persons else "NO PERSON EVENT"
            elif state is None:
                last_label = "NO PERSON EVENT"
            elif state == "WPN":
                last_label = "PERSON WPN"
            else:
                last_label = "PERSON NO_WPN"

            infer_count += 1
            monitor.maybe_report(now)
            if self.cfg.enable_display or self.cfg.save_preview:
                last_preview = draw_detections(frame, persons, weapons, last_label)
            if self.cfg.enable_display and last_preview is not None:
                self._show_array(last_preview, monitor.last_fps)
            if self.cfg.max_frames > 0 and infer_count >= self.cfg.max_frames:
                print(last_label)
                self.running = False
            del frame

        if self.cfg.save_preview and last_preview is not None:
            try:
                import cv2

                Path(self.cfg.save_preview).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(self.cfg.save_preview, last_preview)
                print(f"Saved preview: {self.cfg.save_preview}")
            except Exception as exc:
                logger.warning("Could not save preview: %s", exc)

        self.shutdown()

    def _show(self, frame, persons, weapons, last_label: str, fps: float) -> None:
        display = draw_detections(frame, persons, weapons, last_label)
        self._show_array(display, fps)

    def _show_array(self, display, fps: float) -> None:
        try:
            import cv2

            if fps > 0:
                cv2.putText(
                    display,
                    f"FPS:{fps:.1f}",
                    (12, 54),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )
            cv2.imshow("Detection", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.running = False
        except Exception as exc:
            print(
                "ERROR: Display is not available. Use --no-display for headless mode.",
                file=sys.stderr,
            )
            logger.warning("Display failed: %s", exc)
            self.cfg.enable_display = False

    def shutdown(self) -> None:
        self.running = False
        self.camera.release()
        try:
            import cv2

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
    except CameraOpenError as exc:
        print(str(exc) if str(exc) else USB_CAMERA_ERROR, file=sys.stderr)
        return 2
    except WeaponModelError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except PersonModelError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
