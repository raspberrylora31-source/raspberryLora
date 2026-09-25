"""CLI radio smoke test for a Meshtastic serial device.

Examples (Windows, user-tested T-Beam on COM5):

    python tools/test_radio.py --list
    python tools/test_radio.py --port COM5
    python tools/test_radio.py --port COM5 --listen 30

This tool never flashes or reconfigures the radio. It only opens
SerialInterface, prints info, and optionally listens for packets.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def list_ports() -> None:
    from serial.tools import list_ports
    import meshtastic.util

    likely = set(meshtastic.util.findPorts(True))
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports detected.")
        return
    print("Serial ports:")
    for p in ports:
        mark = "  [likely Meshtastic]" if p.device in likely else ""
        print(f"  {p.device:12}  {p.description}  {p.hwid}{mark}")


def connect_and_show(port: str, listen: float) -> int:
    import meshtastic.serial_interface
    from pubsub import pub

    packets = {"count": 0}

    def on_receive(packet, interface):  # noqa: ARG001
        packets["count"] += 1
        decoded = (packet or {}).get("decoded") or {}
        print(
            f"PACKET id={packet.get('id')} from={packet.get('fromId')} "
            f"to={packet.get('toId')} portnum={decoded.get('portnum')}"
        )
        if decoded.get("text"):
            print(f"  TEXT: {decoded.get('text')}")
        if decoded.get("position"):
            pos = decoded["position"]
            print(
                f"  POSITION lat={pos.get('latitude')} lon={pos.get('longitude')} "
                f"alt={pos.get('altitude')} speed={pos.get('groundSpeed')}"
            )
        if decoded.get("user"):
            user = decoded["user"]
            print(f"  USER {user.get('id')} {user.get('longName')} ({user.get('shortName')})")

    def on_lost(interface=None, **_kwargs):  # noqa: ARG001
        print("Connection lost")

    pub.subscribe(on_receive, "meshtastic.receive")
    pub.subscribe(on_lost, "meshtastic.connection.lost")

    print(f"Connecting SerialInterface(devPath={port!r}) ...")
    iface = None
    try:
        iface = meshtastic.serial_interface.SerialInterface(devPath=port)
    except Exception as exc:
        print(f"Failed to open {port}: {exc}")
        return 2

    try:
        print("--- radio info ---")
        try:
            print(iface.showInfo())
        except Exception as exc:
            print(f"showInfo failed: {exc}")
        user = iface.getMyUser() if hasattr(iface, "getMyUser") else None
        info = iface.getMyNodeInfo() if hasattr(iface, "getMyNodeInfo") else None
        print("getMyUser:", user)
        print("getMyNodeInfo keys:", list(info.keys()) if isinstance(info, dict) else info)
        metadata = getattr(iface, "metadata", None)
        if metadata is not None:
            print("firmware_version:", getattr(metadata, "firmware_version", None))
            print("hw_model:", getattr(metadata, "hw_model", None))
        nodes = getattr(iface, "nodes", None) or {}
        print(f"--- nodes ({len(nodes)}) ---")
        for node_id, node in nodes.items():
            user = (node or {}).get("user") or {}
            pos = (node or {}).get("position") or {}
            print(
                f"  {node_id} {user.get('longName')} ({user.get('shortName')}) "
                f"lat={pos.get('latitude')} lon={pos.get('longitude')}"
            )
        if listen > 0:
            print(f"Listening {listen}s for packets/positions (Ctrl+C to stop)...")
            end = time.time() + listen
            try:
                while time.time() < end:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                print("Interrupted")
            print(f"Heard {packets['count']} packet(s)")
        return 0
    finally:
        print("Disconnecting...")
        try:
            if iface is not None:
                iface.close()
        except Exception as exc:
            print(f"close() warning: {exc}")
        print("Disconnected.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test a Meshtastic serial radio without changing firmware.")
    parser.add_argument("--list", action="store_true", help="List COM / serial ports")
    parser.add_argument("--port", default="COM5", help="Serial device (default COM5)")
    parser.add_argument("--listen", type=float, default=0, help="Seconds to listen for packets after connect")
    args = parser.parse_args()
    if args.list:
        list_ports()
        return 0
    return connect_and_show(args.port, args.listen)


if __name__ == "__main__":
    raise SystemExit(main())
