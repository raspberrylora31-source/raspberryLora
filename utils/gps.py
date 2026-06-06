"""Lightweight IP-based geolocation for Raspberry Pi."""

import json
import logging
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class GPSHandler:
    """
    Approximate location handler based on public IP geolocation.

    This is not true GPS. Accuracy depends on the ISP/network and may be city
    or region level, especially behind VPNs, proxies, hotspots, or carrier NAT.
    """

    DEFAULT_LATITUDE = "0.0000"
    DEFAULT_LONGITUDE = "0.0000"
    DEFAULT_API_URL = "https://ipinfo.io/json"

    def __init__(
        self,
        update_interval_seconds: int = 25,
        timeout_seconds: float = 3.0,
        max_retries: int = 2,
        api_url: str = DEFAULT_API_URL,
    ):
        """
        Initialize IP geolocation.

        Args:
            update_interval_seconds: Minimum seconds between API calls.
            timeout_seconds: HTTP timeout per request.
            max_retries: Retry attempts before falling back to cached location.
            api_url: Free IP geolocation endpoint.
        """
        self.update_interval_seconds = update_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.api_url = api_url
        self.current_latitude = self.DEFAULT_LATITUDE
        self.current_longitude = self.DEFAULT_LONGITUDE
        self.last_update_time = 0.0

        print("IP geolocation enabled")
        print("Note: IP geolocation is approximate, not true GPS")
        logger.info(
            "IP geolocation initialized: interval=%ss timeout=%ss retries=%s api=%s",
            update_interval_seconds,
            timeout_seconds,
            max_retries,
            api_url,
        )

    def get_current_location(self) -> Tuple[str, str]:
        """Return cached coordinates, refreshing from IP geolocation on cooldown."""
        now = time.monotonic()
        elapsed = now - self.last_update_time

        if elapsed < self.update_interval_seconds:
            print(
                "Using cached IP location: "
                f"{self.current_latitude},{self.current_longitude}"
            )
            return self.current_latitude, self.current_longitude

        for attempt in range(1, self.max_retries + 1):
            try:
                print(
                    "Fetching IP location "
                    f"(attempt {attempt}/{self.max_retries}) from {self.api_url}"
                )
                response = requests.get(self.api_url, timeout=self.timeout_seconds)
                response.raise_for_status()
                data = json.loads(response.text)

                if data.get("status") == "fail":
                    raise ValueError(data.get("message", "IP geolocation failed"))

                latitude, longitude = self._extract_coordinates(data)
                if latitude is None or longitude is None:
                    raise ValueError("IP geolocation response missing coordinates")

                self.current_latitude = latitude
                self.current_longitude = longitude
                self.last_update_time = now

                print(
                    "Updated IP location: "
                    f"{self.current_latitude},{self.current_longitude}"
                )
                return self.current_latitude, self.current_longitude

            except Exception as e:
                warning = f"WARNING: IP geolocation failed: {e}"
                print(warning)
                logger.warning(warning)

        print(
            "WARNING: Using last known location: "
            f"{self.current_latitude},{self.current_longitude}"
        )
        return self.current_latitude, self.current_longitude

    @staticmethod
    def _extract_coordinates(data: dict) -> Tuple[Optional[str], Optional[str]]:
        """Support ip-api.com and ipinfo.io response shapes."""
        if "lat" in data and "lon" in data:
            return str(data["lat"]), str(data["lon"])

        if "loc" in data:
            parts = str(data["loc"]).split(",", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0], parts[1]

        return None, None

    def get_location(self) -> Tuple[str, str]:
        """Backward-compatible alias used by the detection loop."""
        return self.get_current_location()

    def get_location_string(self) -> str:
        """Return location as 'LAT,LON'."""
        lat, lon = self.get_current_location()
        return f"{lat},{lon}"

    def set_cached_location(self, latitude: str, longitude: str) -> None:
        """Set cached location manually for tests or offline startup."""
        self.current_latitude = latitude
        self.current_longitude = longitude
        self.last_update_time = time.monotonic()
        print(f"Cached IP location set to: {latitude},{longitude}")
        logger.info(f"Cached IP location set to: {latitude},{longitude}")

    def close(self) -> None:
        """No persistent hardware connection is used."""
        return None
