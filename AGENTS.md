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
python3 app.py --no-uart --display

# Production: person + weapon + UART
python3 app.py --display
python3 app.py --no-display
```

Full mode exits if `models/best.pt` is missing. It does not emit
PERSON NO_WPN in that case.

## Verify without hardware

```bash
python3 -m unittest discover -s tests -v
```
