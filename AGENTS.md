# AGENTS.md

## Product overview

Single Python process on a Raspberry Pi:

USB webcam → YOLOv5n person detection → YOLOv5 weapon model on person
crops (`models/best.pt`) → debounce → compact TEXTMSG over GPIO UART →
LILYGO T-Beam Meshtastic.

Entry point is `app.py`. There is no web server, database, GPS, custom
ESP32 LoRa firmware, or Docker stack.

Weapon detection is required for full mode. `--person-only` is a camera
test that skips the weapon model and UART.

## Modes

```bash
source venv/bin/activate

# Camera + person boxes (no weapon model, no UART)
python3 app.py --person-only --display
python3 app.py --person-only --no-display

# Person + YOLOv5 weapon, no UART
python3 tools/download_weapon_model.py
python3 app.py --no-uart --display

# Still-image weapon check (no webcam)
python3 tools/verify_weapon_detection.py
python3 app.py --no-uart --no-display --image tests/fixtures/person.jpg --max-frames 3

# Production: person + weapon + UART
python3 app.py --display
python3 app.py --no-display
```

If `models/best.pt` is missing, full mode downloads the public YOLOv5s
gun+knife weights. If download/load fails it prints
`ERROR: weapon detection unavailable` and does not emit PERSON NO_WPN.

## Verify without hardware

```bash
python3 -m unittest discover -s tests -v
```
