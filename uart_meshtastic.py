"""Non-blocking UART sender for a Meshtastic Serial Module in TEXTMSG mode."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import serial
except ImportError:  # unit tests may mock the serial class
    serial = None

_ERROR_LOG_INTERVAL_SEC = 10.0


class MeshtasticUART:
    """
    Send short ASCII/UTF-8 lines to Meshtastic over GPIO UART.

    Detection code should only call send_message(); it must not touch pyserial.
    Writes run on a background thread so a stuck radio cannot stall inference.
    """

    def __init__(
        self,
        port: str = "/dev/serial0",
        baud: int = 38400,
        queue_size: int = 16,
        serial_cls=None,
    ):
        self.port = port
        self.baud = baud
        self._serial_cls = serial_cls
        self._queue: queue.Queue[str] = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._connected = False
        self._last_error_at = 0.0

    def connect(self) -> bool:
        """Open UART and start the sender thread. Never raises."""
        self._stop.clear()
        opened = self._open_serial()
        self._start_worker()
        return opened

    def _start_worker(self) -> None:
        if self._stop.is_set():
            return
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._worker,
                name="meshtastic-uart",
                daemon=True,
            )
            self._thread.start()

    def disconnect(self) -> None:
        """Stop the sender thread and close the serial port. Never raises."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._close_serial()

    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._connected and self._ser is not None and self._ser.is_open)

    def send_message(self, text: str) -> bool:
        """
        Queue a TEXTMSG line. Non-blocking. Never raises.

        If the queue is full, the oldest message is dropped so newer events
        still get through.
        """
        if text is None:
            return False
        line = str(text).strip()
        if not line:
            return False

        self._start_worker()
        try:
            self._queue.put_nowait(line)
            return True
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(line)
                return True
            except queue.Full:
                self._log_error("UART send queue full; dropping message")
                return False

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until queued messages are written or timeout. For test tools."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.empty():
                time.sleep(0.2)
                return self._queue.empty()
            time.sleep(0.05)
        return self._queue.empty()

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                message = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue

            if not self._ensure_connected():
                self._requeue(message)
                time.sleep(2.0)
                continue

            payload = (message + "\n").encode("utf-8")
            try:
                with self._lock:
                    if self._ser is None:
                        raise OSError("UART not open")
                    self._ser.write(payload)
                    self._ser.flush()
            except Exception as exc:
                self._log_error(f"UART write failed: {exc}")
                self._close_serial()
                self._requeue(message)
                time.sleep(1.0)

    def _ensure_connected(self) -> bool:
        if self.is_connected():
            return True
        return self._open_serial()

    def _open_serial(self) -> bool:
        self._close_serial()
        try:
            opener = self._serial_cls
            if opener is None:
                if serial is None:
                    raise RuntimeError("pyserial is required on the Raspberry Pi")
                opener = serial.Serial
            ser = opener(
                port=self.port,
                baudrate=self.baud,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.1,
                write_timeout=1.0,
            )
            with self._lock:
                self._ser = ser
                self._connected = True
            logger.info("UART connected %s @ %s", self.port, self.baud)
            return True
        except Exception as exc:
            self._log_error(f"UART open failed ({self.port}): {exc}")
            self._close_serial()
            return False

    def _close_serial(self) -> None:
        with self._lock:
            ser = self._ser
            self._ser = None
            self._connected = False
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def _requeue(self, message: str) -> None:
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            pass

    def _log_error(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_error_at < _ERROR_LOG_INTERVAL_SEC:
            return
        self._last_error_at = now
        logger.warning(message)
