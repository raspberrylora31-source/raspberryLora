"""Debounce detection states so LoRa is not flooded every camera frame."""

from __future__ import annotations

import time
from typing import Optional


class EventManager:
    """
    Confirm a detection across several frames, then emit compact events.

    Recommended defaults:
    - require CONFIRMATION_FRAMES consistent classifications
    - send when a confirmed state is first detected
    - do not retransmit the same state immediately
    - allow a repeat after EVENT_COOLDOWN_SECONDS, or immediately on change

    If state_change_only is True, the same confirmed state is never resent
    while it remains active (cooldown repeats are disabled).
    """

    def __init__(
        self,
        confirmation_frames: int = 3,
        cooldown_seconds: float = 30.0,
        state_change_only: bool = False,
    ):
        if confirmation_frames < 1:
            raise ValueError("confirmation_frames must be >= 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")

        self.confirmation_frames = confirmation_frames
        self.cooldown_seconds = cooldown_seconds
        self.state_change_only = state_change_only

        self._pending_state: Optional[str] = None
        self._pending_count = 0
        self._confirmed_state: Optional[str] = None
        self._last_sent_state: Optional[str] = None
        self._last_sent_at = 0.0

    def update(
        self, state: Optional[str], now: Optional[float] = None
    ) -> Optional[str]:
        """
        Ingest one classification.

        Args:
            state: "WPN", "NO_WPN", or None when no person is present.
            now: monotonic timestamp for tests; defaults to time.monotonic().

        Returns:
            The state to transmit, or None if nothing should be sent.
        """
        if now is None:
            now = time.monotonic()

        if state is not None:
            state = str(state).strip().upper()
            if state not in {"WPN", "NO_WPN"}:
                state = None

        if state != self._pending_state:
            self._pending_state = state
            self._pending_count = 1
        else:
            self._pending_count += 1

        if self._pending_count < self.confirmation_frames:
            return None

        self._confirmed_state = state

        if state is None:
            return None

        if self._last_sent_state is None:
            return self._emit(state, now)

        if state != self._last_sent_state:
            return self._emit(state, now)

        if self.state_change_only:
            return None

        if (now - self._last_sent_at) >= self.cooldown_seconds:
            return self._emit(state, now)

        return None

    def _emit(self, state: str, now: float) -> str:
        self._last_sent_state = state
        self._last_sent_at = now
        return state
