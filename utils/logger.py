"""
Logger Module - Lightweight event logging for Raspberry Pi
Logs detections locally and to terminal
"""

import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


class LocalLogger:
    """
    Lightweight event logger for detection events.
    Logs to both terminal and local files.
    """

    def __init__(self, log_dir: str = "logs", enable_file_logging: bool = True):
        """
        Initialize logger.

        Args:
            log_dir: Directory for log files
            enable_file_logging: Whether to save logs to files
        """
        self.log_dir = Path(log_dir)
        self.enable_file_logging = enable_file_logging

        if enable_file_logging:
            self.log_dir.mkdir(exist_ok=True)
            self.detection_log_path = self.log_dir / "detections.log"
            self.error_log_path = self.log_dir / "errors.log"
        else:
            self.detection_log_path = None
            self.error_log_path = None

        self.setup_logging()

    def setup_logging(self) -> None:
        """Configure Python logging."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        def has_named_handler(handler_name: str) -> bool:
            return any(
                getattr(handler, "name", None) == handler_name
                for handler in root_logger.handlers
            )

        # Console handler
        console_handler_name = "raspberry_lora_console"
        console_formatter = logging.Formatter(log_format, datefmt=date_format)
        if not has_named_handler(console_handler_name):
            console_handler = logging.StreamHandler()
            console_handler.name = console_handler_name
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # File handlers
        if self.enable_file_logging:
            detection_handler_name = f"raspberry_lora_detection:{self.detection_log_path}"
            if not has_named_handler(detection_handler_name):
                detection_handler = logging.FileHandler(self.detection_log_path)
                detection_handler.name = detection_handler_name
                detection_handler.setLevel(logging.INFO)
                detection_handler.setFormatter(console_formatter)
                root_logger.addHandler(detection_handler)

            error_handler_name = f"raspberry_lora_error:{self.error_log_path}"
            if not has_named_handler(error_handler_name):
                error_handler = logging.FileHandler(self.error_log_path)
                error_handler.name = error_handler_name
                error_handler.setLevel(logging.ERROR)
                error_handler.setFormatter(console_formatter)
                root_logger.addHandler(error_handler)

    def log_detection(
        self, entity_type: str, latitude: str, longitude: str
    ) -> None:
        """
        Log detection event to file and terminal.

        Args:
            entity_type: Type of detection
            latitude: GPS latitude
            longitude: GPS longitude
        """
        logger = logging.getLogger(__name__)

        # Format output as required
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output = (
            f"Entity: {entity_type}\n"
            f"Date and Time: {timestamp}\n"
            f"Location: {latitude},{longitude}"
        )

        logger.info(f"DETECTION: {output.replace(chr(10), ' | ')}")

        # Save to file if enabled
        if self.enable_file_logging:
            try:
                with open(self.detection_log_path, "a") as f:
                    f.write(output + "\n" + "=" * 60 + "\n")
            except Exception as e:
                logger.error(f"Failed to write detection log: {e}")

    def log_error(self, message: str, exception: Optional[Exception] = None) -> None:
        """
        Log error event.

        Args:
            message: Error message
            exception: Exception object (optional)
        """
        logger = logging.getLogger(__name__)

        if exception:
            logger.error(f"{message}: {exception}")
        else:
            logger.error(message)

    def log_startup(self, config: dict) -> None:
        """
        Log system startup information.

        Args:
            config: Configuration dictionary
        """
        logger = logging.getLogger(__name__)

        startup_msg = (
            f"System started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Config: {config}"
        )

        logger.info(startup_msg)

    def log_shutdown(self, reason: str = "Normal shutdown") -> None:
        """
        Log system shutdown.

        Args:
            reason: Shutdown reason
        """
        logger = logging.getLogger(__name__)
        logger.info(f"System shutdown: {reason}")

    def get_log_file_path(self, log_type: str = "detection") -> Optional[str]:
        """
        Get path to log file.

        Args:
            log_type: "detection" or "error"

        Returns:
            Path to log file or None if logging disabled
        """
        if log_type == "detection":
            return str(self.detection_log_path) if self.detection_log_path else None
        elif log_type == "error":
            return str(self.error_log_path) if self.error_log_path else None

        return None

    def clear_old_logs(self, max_age_days: int = 7) -> int:
        """
        Clear log files older than specified days.

        Args:
            max_age_days: Age threshold in days

        Returns:
            Number of files deleted
        """
        logger = logging.getLogger(__name__)
        deleted_count = 0

        if not self.enable_file_logging:
            return 0

        from time import time

        current_time = time()
        max_age_seconds = max_age_days * 86400

        try:
            for log_file in self.log_dir.glob("*.log"):
                file_age = current_time - log_file.stat().st_mtime
                if file_age > max_age_seconds:
                    log_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old log: {log_file}")
        except Exception as e:
            logger.error(f"Error clearing old logs: {e}")

        return deleted_count
