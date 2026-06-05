"""
Main Orchestrator - Real-time Object Detection System for Raspberry Pi
Integrates detection, LoRa communication, GPS, and logging
"""

import logging
import argparse
import signal
import sys
from typing import List, Optional

from utils.logger import LocalLogger


class DetectionSystem:
    """
    Main detection system orchestrator.
    Manages camera, detection, LoRa, GPS, and logging.
    """

    def __init__(
        self,
        model_name: str = "yolov5n",
        camera_id: int = 0,
        confidence_threshold: float = 0.45,
        skip_frames: int = 2,
        camera_width: int = 640,
        camera_height: int = 480,
        use_gps: bool = True,
        gps_simulation: bool = True,
        lora_port: str = "/dev/ttyUSB0",
        lora_connection: str = "uart",
        lora_wifi_host: str = "192.168.1.100",
        lora_wifi_port: int = 8080,
        lora_cooldown: int = 30,
        enable_display: bool = False,
    ):
        """
        Initialize detection system.

        Args:
            model_name: YOLO model ("yolov5n" or "yolov8n")
            camera_id: Camera device ID
            confidence_threshold: Detection confidence threshold
            skip_frames: Frame skip for performance
            camera_width: Camera frame width
            camera_height: Camera frame height
            use_gps: Enable GPS
            gps_simulation: Use simulated GPS
            lora_port: Serial port for UART/USB
            lora_connection: Connection type ("uart", "usb", "wifi", "http", "ble", "btc")
            lora_wifi_host: IP for WiFi connection
            lora_wifi_port: Port for WiFi connection
            lora_cooldown: LoRa message cooldown in seconds
            enable_display: Show camera feed with detections
        """
        self.logger = logging.getLogger(__name__)
        self.running = True
        self.camera = None
        self.serial_handler = None
        self.gps_handler = None

        try:
            import cv2
            from detector import YOLOModelLoader, ObjectDetector
            from lora import SerialHandler, LoRaMessenger
            from utils.gps import GPSHandler
        except ImportError as exc:
            raise RuntimeError(
                "Missing runtime dependency. Install dependencies with "
                "`python3 -m pip install -r requirements.txt`."
            ) from exc

        self.cv2 = cv2
        self.ObjectDetector = ObjectDetector

        # Configuration
        self.config = {
            "model": model_name,
            "camera_id": camera_id,
            "confidence": confidence_threshold,
            "skip_frames": skip_frames,
            "camera_size": (camera_width, camera_height),
            "use_gps": use_gps,
            "lora_connection": lora_connection,
            "lora_port": lora_port,
            "lora_wifi_host": lora_wifi_host,
            "lora_wifi_port": lora_wifi_port,
            "lora_cooldown": lora_cooldown,
            "enable_display": enable_display,
        }

        # Initialize components
        self.logger.info("Initializing detection system...")

        # 1. Load model
        self.model_loader = YOLOModelLoader(model_name=model_name)
        self.model = self.model_loader.load_model()
        self.detector = ObjectDetector(
            model=self.model,
            confidence_threshold=confidence_threshold,
            skip_frames=skip_frames,
        )

        # 2. Initialize camera
        self.camera_width = camera_width
        self.camera_height = camera_height
        self._init_camera(camera_id)

        # 3. Initialize LoRa (with multiple connection options)
        self.serial_handler = SerialHandler(
            connection_type=lora_connection,
            port=lora_port,
            wifi_host=lora_wifi_host,
            wifi_port=lora_wifi_port,
        )
        self.lora_messenger = LoRaMessenger(
            serial_handler=self.serial_handler,
            cooldown_seconds=lora_cooldown,
        )
        if not self.serial_handler.connect():
            self.logger.warning(
                "LoRa connection unavailable; detections will be logged locally only"
            )

        # 4. Initialize GPS
        self.gps_handler = GPSHandler(use_simulation=gps_simulation)

        # 5. Initialize logger
        self.local_logger = LocalLogger(log_dir="logs", enable_file_logging=True)

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.local_logger.log_startup(self.config)

    def _init_camera(self, camera_id: int) -> bool:
        """
        Initialize USB camera.

        Args:
            camera_id: Camera device ID

        Returns:
            True if successful
        """
        try:
            self.camera = self.cv2.VideoCapture(camera_id)

            if not self.camera.isOpened():
                self.logger.error(f"Failed to open camera {camera_id}")
                return False

            # Set camera resolution (lower resolution = better performance)
            self.camera.set(self.cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
            self.camera.set(self.cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
            self.camera.set(self.cv2.CAP_PROP_FPS, 15)  # Lower FPS for RPi

            # Reduce buffering to minimize lag
            self.camera.set(self.cv2.CAP_PROP_BUFFERSIZE, 1)

            self.logger.info(
                f"✓ Camera initialized (ID: {camera_id}, "
                f"{self.camera_width}x{self.camera_height})"
            )
            return True

        except Exception as e:
            self.logger.error(f"Camera initialization error: {e}")
            return False

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals."""
        self.logger.info("Shutdown signal received")
        self.shutdown()

    def run(self) -> None:
        """
        Main detection loop.
        Continuously captures frames, detects objects, and sends LoRa messages.
        """
        self.logger.info("Starting detection loop...")
        frame_count = 0

        try:
            while self.running:
                # Capture frame
                ret, frame = self.camera.read()
                if not ret:
                    self.logger.error("Failed to read frame from camera")
                    break

                frame_count += 1

                # Run detection
                entity_type, details = self.detector.detect_combined(frame)

                # Get GPS location
                latitude, longitude = self.gps_handler.get_location()

                # Only process certain detections
                if entity_type in ["Person with weapon", "Person without weapon"]:
                    # Log detection
                    self.local_logger.log_detection(
                        entity_type, latitude, longitude
                    )

                    # Print to terminal (required output format)
                    timestamp = details["timestamp"]
                    output = (
                        f"\nEntity: {entity_type}\n"
                        f"Date and Time: {timestamp}\n"
                        f"Location: {latitude},{longitude}"
                    )
                    print(output)

                    # Send via LoRa (with cooldown)
                    self.lora_messenger.send_detection(
                        entity_type, latitude, longitude
                    )

                # Draw and display if enabled
                if self.config["enable_display"]:
                    display_frame = self.ObjectDetector.draw_detections(
                        frame, entity_type
                    )
                    self.cv2.imshow("Detection", display_frame)

                    # Press 'q' to quit
                    if self.cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                # Status logging every 100 frames
                if frame_count % 100 == 0:
                    self.logger.debug(
                        f"Processed {frame_count} frames, "
                        f"detector stats: {self.detector.get_stats()}"
                    )

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Error in detection loop: {e}")
            self.local_logger.log_error("Detection loop error", e)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Gracefully shutdown all systems."""
        self.logger.info("Shutting down detection system...")
        self.running = False

        # Close camera
        if self.camera:
            self.camera.release()
            self.cv2.destroyAllWindows()

        # Disconnect LoRa
        if self.serial_handler:
            self.serial_handler.disconnect()

        # Close GPS
        if self.gps_handler:
            self.gps_handler.close()

        # Log shutdown
        self.local_logger.log_shutdown("Normal shutdown")

        self.logger.info("✓ System shutdown complete")


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Real-time Object Detection for Raspberry Pi with LoRa"
    )

    # Model selection
    parser.add_argument(
        "--model",
        choices=["yolov5n", "yolov8n"],
        default="yolov5n",
        help="Detection model (default: yolov5n)",
    )

    # Camera settings
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera device ID (default: 0)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=640,
        help="Camera frame width (default: 640)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Camera frame height (default: 480)",
    )

    # Detection settings
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.45,
        help="Confidence threshold (default: 0.45)",
    )
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=2,
        help="Skip N frames for performance (default: 2)",
    )

    # LoRa connection settings
    parser.add_argument(
        "--lora-connection",
        choices=["uart", "usb", "wifi", "http", "ble", "btc"],
        default="uart",
        help="LoRa connection type (default: uart)",
    )
    parser.add_argument(
        "--lora-port",
        default="/dev/ttyUSB0",
        help="Serial port for UART/USB (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--lora-wifi-host",
        default="192.168.1.100",
        help="WiFi IP address for ESP32 (default: 192.168.1.100)",
    )
    parser.add_argument(
        "--lora-wifi-port",
        type=int,
        default=8080,
        help="WiFi port for ESP32 (default: 8080)",
    )
    parser.add_argument(
        "--lora-cooldown",
        type=int,
        default=30,
        help="LoRa message cooldown in seconds (default: 30)",
    )

    # GPS settings
    parser.add_argument(
        "--gps-simulation",
        action="store_true",
        default=True,
        help="Use simulated GPS location",
    )
    parser.add_argument(
        "--no-gps-simulation",
        dest="gps_simulation",
        action="store_false",
        help="Disable GPS simulation (use real GPS module)",
    )

    # Display
    parser.add_argument(
        "--display",
        action="store_true",
        help="Show camera feed with detections",
    )

    return parser


def main(argv: Optional[List[str]] = None):
    """Main entry point."""
    parser = build_parser()

    # Parse arguments
    args = parser.parse_args(argv)

    # Initialize logging
    local_logger = LocalLogger(enable_file_logging=True)

    # Create and run system
    try:
        system = DetectionSystem(
            model_name=args.model,
            camera_id=args.camera,
            confidence_threshold=args.confidence,
            skip_frames=args.skip_frames,
            camera_width=args.width,
            camera_height=args.height,
            use_gps=True,
            gps_simulation=args.gps_simulation,
            lora_port=args.lora_port,
            lora_connection=args.lora_connection,
            lora_wifi_host=args.lora_wifi_host,
            lora_wifi_port=args.lora_wifi_port,
            lora_cooldown=args.lora_cooldown,
            enable_display=args.display,
        )

        system.run()

    except Exception as e:
        local_logger.log_error("System initialization error", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
