"""
LoRa Communication Module
Handles LoRa message formatting and transmission
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class LoRaMessenger:
    """
    LoRa communication handler for broadcasting detection events.
    Includes cooldown to prevent message spam.
    """

    # Message format constants
    MSG_DELIMITER = "|"
    MAX_MESSAGE_LENGTH = 240  # LoRa typical payload

    def __init__(self, serial_handler, cooldown_seconds: int = 30):
        """
        Initialize LoRa messenger.

        Args:
            serial_handler: SerialHandler instance for communication
            cooldown_seconds: Cooldown between messages of same type
        """
        self.serial_handler = serial_handler
        self.cooldown_seconds = cooldown_seconds
        self.last_sent_entity = None
        self.last_sent_time = None

        logger.info(
            f"LoRaMessenger initialized (cooldown: {cooldown_seconds}s)"
        )

    def format_detection_message(
        self, entity_type: str, latitude: str, longitude: str
    ) -> str:
        """
        Format detection message for LoRa transmission.

        Args:
            entity_type: Detection type ("Person with weapon", etc.)
            latitude: GPS latitude
            longitude: GPS longitude

        Returns:
            Formatted message string
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format: Entity: <type> | Date and Time: <timestamp> | Location: <lat>,<lon>
        message = (
            f"Entity: {entity_type}{self.MSG_DELIMITER}"
            f"Date and Time: {timestamp}{self.MSG_DELIMITER}"
            f"Location: {latitude},{longitude}"
        )

        return message

    def should_send_message(self, entity_type: str) -> bool:
        """
        Check if message should be sent based on cooldown.

        Args:
            entity_type: Type of entity detected

        Returns:
            True if enough time has passed since last message of this type
        """
        # Always send different entity types
        if entity_type != self.last_sent_entity:
            return True

        # Check cooldown for same entity type
        if self.last_sent_time is None:
            return True

        time_elapsed = datetime.now() - self.last_sent_time
        if time_elapsed >= timedelta(seconds=self.cooldown_seconds):
            return True

        return False

    def send_detection(
        self, entity_type: str, latitude: str, longitude: str
    ) -> bool:
        """
        Send detection event via LoRa with cooldown.

        Args:
            entity_type: Detection type
            latitude: GPS latitude
            longitude: GPS longitude

        Returns:
            True if message was sent, False if throttled by cooldown
        """
        # Check cooldown
        if not self.should_send_message(entity_type):
            logger.debug(
                f"Message throttled: {entity_type} (cooldown active)"
            )
            return False

        # Format message
        message = self.format_detection_message(entity_type, latitude, longitude)

        # Truncate if too long
        if len(message) > self.MAX_MESSAGE_LENGTH:
            logger.warning(
                f"Message truncated ({len(message)} > {self.MAX_MESSAGE_LENGTH} bytes)"
            )
            message = message[: self.MAX_MESSAGE_LENGTH]

        # Send via serial to ESP32
        success = self.serial_handler.send_lora_message(message)

        if success:
            self.last_sent_entity = entity_type
            self.last_sent_time = datetime.now()
            logger.info(f"LoRa sent: {entity_type}")

        return success

    def get_cooldown_status(self) -> Tuple[Optional[str], Optional[float]]:
        """
        Get current cooldown status.

        Returns:
            Tuple: (last_entity, seconds_remaining)
        """
        if self.last_sent_time is None:
            return None, None

        time_elapsed = (datetime.now() - self.last_sent_time).total_seconds()
        seconds_remaining = max(0, self.cooldown_seconds - time_elapsed)

        return self.last_sent_entity, seconds_remaining

    def reset_cooldown(self) -> None:
        """Reset cooldown timer."""
        self.last_sent_time = None
        self.last_sent_entity = None
        logger.info("Cooldown reset")

    @staticmethod
    def parse_lora_message(raw_message: str) -> dict:
        """
        Parse received LoRa message.

        Args:
            raw_message: Raw message string from LoRa

        Returns:
            Parsed message dictionary
        """
        result = {"raw": raw_message, "entity": None, "timestamp": None, "location": None}

        try:
            parts = raw_message.split("|")
            for part in parts:
                part = part.strip()
                if part.startswith("Entity:"):
                    result["entity"] = part.replace("Entity:", "").strip()
                elif part.startswith("Date and Time:"):
                    result["timestamp"] = part.replace("Date and Time:", "").strip()
                elif part.startswith("Location:"):
                    result["location"] = part.replace("Location:", "").strip()
        except Exception as e:
            logger.error(f"Error parsing LoRa message: {e}")

        return result
