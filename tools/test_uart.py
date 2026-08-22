#!/usr/bin/env python3
"""Send one TEXTMSG line to the Meshtastic UART. No computer vision."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from uart_meshtastic import MeshtasticUART  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a short ASCII line to Meshtastic Serial TEXTMSG"
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="TEST MESHTASTIC UART",
        help='Text to send (default: "TEST MESHTASTIC UART")',
    )
    parser.add_argument("--port", default=None, help="UART device (default UART_PORT)")
    parser.add_argument("--baud", type=int, default=None, help="Baud rate")
    args = parser.parse_args()

    cfg = Config.from_env()
    port = args.port or cfg.uart_port
    baud = args.baud or cfg.uart_baud
    text = args.message.strip()
    if not text:
        print("Message is empty", file=sys.stderr)
        return 1

    uart = MeshtasticUART(port=port, baud=baud)
    print(f"Opening {port} @ {baud}")
    if not uart.connect():
        print(
            f"Could not open {port}. Check wiring, enable_uart, and that "
            "the T-Beam is powered. Will still attempt a queued send/retry.",
            file=sys.stderr,
        )

    if not uart.send_message(text):
        print("Failed to queue message", file=sys.stderr)
        uart.disconnect()
        return 1

    flushed = uart.flush(timeout=5.0)
    uart.disconnect()
    if not flushed:
        print("Timed out waiting for UART write", file=sys.stderr)
        return 1

    print(f"Sent: {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
