"""
GPS Module - Location service for Raspberry Pi
Supports USB GPS modules and location simulation
"""

import logging
import os
from typing import Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GPSHandler:
    """
    GPS location handler for Raspberry Pi.
    Supports USB GPS modules (NMEA protocol) or location simulation.
    """

    # Default location (simulation fallback)
    DEFAULT_LATITUDE = "0.0000"
    DEFAULT_LONGITUDE = "0.0000"

    def __init__(self, use_simulation: bool = True, gps_port: str = "/dev/ttyUSB1"):
        """
        Initialize GPS handler.

        Args:
            use_simulation: If True, use simulated location instead of real GPS
            gps_port: Serial port for GPS module (if not simulating)
        """
        self.use_simulation = use_simulation
        self.gps_port = gps_port
        self.current_latitude = self.DEFAULT_LATITUDE
        self.current_longitude = self.DEFAULT_LONGITUDE
        self.last_fix_time = None
        self.gps_module = None

        if use_simulation:
            logger.info("GPS Handler: Using simulated location mode")
            self.init_simulation()
        else:
            logger.info(f"GPS Handler: Using GPS module on {gps_port}")
            self.init_gps_module()

    def init_simulation(self) -> None:
        """Initialize simulated GPS with default location."""
        self.current_latitude = os.getenv("SIM_LAT", self.DEFAULT_LATITUDE)
        self.current_longitude = os.getenv("SIM_LON", self.DEFAULT_LONGITUDE)
        logger.info(
            f"Simulated location: {self.current_latitude}, {self.current_longitude}"
        )

    def init_gps_module(self) -> None:
        """Initialize real GPS module (USB NMEA)."""
        try:
            import serial

            self.gps_module = serial.Serial(
                port=self.gps_port, baudrate=9600, timeout=2
            )
            logger.info(f"GPS module initialized on {self.gps_port}")
        except ImportError:
            logger.warning("pyserial not available, using simulation")
            self.use_simulation = True
        except Exception as e:
            logger.warning(f"GPS module init failed: {e}, using simulation")
            self.use_simulation = True

    def get_location(self) -> Tuple[str, str]:
        """
        Get current GPS location.

        Returns:
            Tuple: (latitude, longitude) as strings
        """
        if self.use_simulation:
            return self.current_latitude, self.current_longitude

        try:
            if self.gps_module and self.gps_module.is_open:
                line = self.gps_module.readline().decode("utf-8").strip()
                lat, lon = self._parse_nmea(line)
                if lat and lon:
                    self.current_latitude = lat
                    self.current_longitude = lon
                    self.last_fix_time = datetime.now()
        except Exception as e:
            logger.debug(f"GPS read error: {e}")

        return self.current_latitude, self.current_longitude

    def get_location_string(self) -> str:
        """
        Get location as formatted string.

        Returns:
            Formatted location string "LAT,LON"
        """
        lat, lon = self.get_location()
        return f"{lat},{lon}"

    @staticmethod
    def _parse_nmea(nmea_sentence: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse NMEA GPS sentence.

        Args:
            nmea_sentence: NMEA sentence string

        Returns:
            Tuple: (latitude, longitude) or (None, None)
        """
        try:
            if not nmea_sentence.startswith("$GPGGA"):
                return None, None

            parts = nmea_sentence.split(",")
            if len(parts) < 6:
                return None, None

            # Extract lat/lon from NMEA format
            lat = parts[2]
            lon = parts[4]

            # Convert to decimal degrees if needed
            if lat and lon:
                return lat, lon
        except Exception as e:
            logger.debug(f"NMEA parse error: {e}")

        return None, None

    def set_simulation_location(self, latitude: str, longitude: str) -> None:
        """
        Set simulated location (for testing).

        Args:
            latitude: Latitude string
            longitude: Longitude string
        """
        self.current_latitude = latitude
        self.current_longitude = longitude
        logger.info(f"Simulation location set to: {latitude}, {longitude}")

    def close(self) -> None:
        """Close GPS module connection."""
        if self.gps_module:
            try:
                self.gps_module.close()
            except Exception as e:
                logger.warning(f"Error closing GPS: {e}")
