#!/usr/bin/env python3
"""
Optional receiver for a Meshtastic node with Serial Module TEXTMSG enabled.

This is not required on the mesh. Any Meshtastic client on the same channel
already shows the text. Use this only when a computer is attached to a
receiving node's serial port.

Prints:
    RECEIVED:
    PERSON NO_WPN 2026-08-20 11:25:31
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Print Meshtastic TEXTMSG serial lines")
    parser.add_argument("--port", default=None, help="Serial device of the receiving node")
    parser.add_argument("--baud", type=int, default=None)
    args = parser.parse_args()

    cfg = Config.from_env()
    port = args.port or cfg.uart_port
    baud = args.baud or cfg.uart_baud

    print(f"Listening on {port} @ {baud} (Ctrl+C to stop)")
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=0.5)
    except Exception as exc:
        print(f"Could not open {port}: {exc}", file=sys.stderr)
        return 1

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue
            print("RECEIVED:")
            print(line)
            print()
    except KeyboardInterrupt:
        print("\nStopped")
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
