# AGENTS.md

## Product overview

Single Python process: USB-webcam person detection on a Raspberry Pi, optional
local preview, compact TEXTMSG events over GPIO UART to a LILYGO T-Beam running
Meshtastic. Entry point is `app.py`. There is no web server, database, GPS,
custom ESP32 LoRa firmware, or Docker stack.

## Environment (Cloud VM vs Raspberry Pi)

- **Cloud VM / x86:** Python 3.12 is typical. Install `pip install -r requirements.txt`.
  There is no USB camera or T-Beam; use `--video-file` and `--no-uart`, or a
  virtual serial port for UART tests.
- **Raspberry Pi (target):** Raspberry Pi 4B, Python 3.9+, GPIO UART
  `/dev/serial0` @ 38400 to a T-Beam Serial Module in TEXTMSG mode.

System packages on Ubuntu/Debian VMs:

```bash
sudo apt-get install -y python3-venv python3-dev build-essential libgl1 libglib2.0-0
```

## Activate and run

```bash
source venv/bin/activate

# Raspberry Pi with USB camera + T-Beam on GPIO UART
python3 app.py --display

# Person detection only (no UART, no weapon model)
python3 app.py --no-uart --person-only --display

# Cloud VM / no camera
python3 app.py --no-uart --person-only --video-file /tmp/test_feed.mp4
```

## Verify without hardware

Formatter, debounce, and person/weapon association tests (no model download):

```bash
source venv/bin/activate
python3 -m unittest tests.test_message_formatter tests.test_event_manager tests.test_detector -v
```

UART smoke test (requires a serial device):

```bash
python3 tools/test_uart.py "TEST MESHTASTIC UART"
```

## Lint / tests

- No project linter config.
- Unit tests live in `tests/test_*.py`.
- Stock YOLOv8n is person-only. Do not claim `PERSON WPN` works unless
  `WEAPON_MODEL` is a real weapon-class weight file.
