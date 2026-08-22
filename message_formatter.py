"""Compact Meshtastic text-event formatter and local timestamp helper."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

VALID_STATES = ("WPN", "NO_WPN")


def format_timestamp(when: Optional[datetime] = None) -> str:
    """Return local system time as YYYY-MM-DD HH:MM:SS (no milliseconds)."""
    if when is None:
        when = datetime.now()
    return when.strftime("%Y-%m-%d %H:%M:%S")


def format_detection_message(
    state: str, timestamp: Optional[str] = None
) -> str:
    """
    Format a compact LoRa text event.

    Examples:
        PERSON NO_WPN 2026-08-20 11:25:31
        PERSON WPN 2026-08-20 11:25:38
    """
    if state is None:
        raise ValueError("state is required")

    normalized = str(state).strip().upper()
    if normalized in {"PERSON WPN", "PERSON_WPN"}:
        normalized = "WPN"
    elif normalized in {"PERSON NO_WPN", "PERSON_NO_WPN", "NO-WPN"}:
        normalized = "NO_WPN"

    if normalized not in VALID_STATES:
        raise ValueError(
            f"state must be one of {VALID_STATES}, got {state!r}"
        )

    if timestamp is None:
        timestamp = format_timestamp()
    else:
        timestamp = str(timestamp).strip()
        if not timestamp:
            raise ValueError("timestamp must not be empty")

    return f"PERSON {normalized} {timestamp}"
