# Raspberry Pi Person Detection over Meshtastic

USB webcam detection on a Raspberry Pi. Persons are boxed locally. Confirmed
events are sent as a short UART text line to a LILYGO T-Beam running Meshtastic.
The T-Beam Serial Module (TEXTMSG) places that line on the LoRa mesh.

This Pi application does **not** implement LoRa itself.

## Project purpose

- Capture frames from a USB webcam
- Detect persons with a lightweight local model
- Draw bounding boxes on an optional local display
- Classify a confirmed person as `PERSON WPN` or `PERSON NO_WPN`
- Timestamp the event from the Pi system clock
- Send one compact ASCII line through GPIO UART to Meshtastic

Example mesh text:

```
PERSON NO_WPN 2026-08-20 11:25:31
PERSON WPN 2026-08-20 11:25:38
```

Images, video, coordinates, and JSON are never sent over LoRa.

**Weapon detection is not enabled by default.** The stock person model is
YOLOv8n (COCO). COCO has a `person` class and does not provide a reliable
weapon class. `PERSON WPN` is emitted only when a separate weapon-class model
file is supplied via `WEAPON_MODEL`. Until then, confirmed persons are
`PERSON NO_WPN`.

## System architecture

```
USB webcam
    -> camera.py          capture 640x360 (configurable), 1-frame buffer
    -> detector.py        person model once; optional weapon model on person crops
    -> event_manager.py   confirm N frames, cooldown, state-change
    -> message_formatter.py   PERSON <WPN|NO_WPN> <timestamp>
    -> uart_meshtastic.py     background UART writer
    -> Raspberry Pi GPIO UART (/dev/serial0, 38400)
    -> T-Beam Serial Module TEXTMSG
    -> Meshtastic LoRa mesh
```

`app.py` is the only process you run for the full pipeline.

## Hardware

- Raspberry Pi (this project targets **Raspberry Pi 4B**; 4GB RAM recommended)
- USB webcam
- LILYGO T-Beam with Meshtastic firmware
- Three jumper wires: TX, RX, GND
- Independent power for the T-Beam (do **not** power it from Pi 5V on the UART)

## Exact UART wiring

TX and RX are crossed. Use a common GND. Do not connect Pi 5V to the T-Beam UART.

```
Raspberry Pi                         LILYGO T-Beam

GPIO14 / TXD
Physical pin 8  ------------------>  GPIO13 / RX

GPIO15 / RXD
Physical pin 10 <------------------  GPIO14 / TX

GND
Physical pin 6  -------------------  GND
```

| Raspberry Pi | Function | T-Beam |
|---|---|---|
| Physical pin 8 / GPIO14 | TXD | GPIO13 RX |
| Physical pin 10 / GPIO15 | RXD | GPIO14 TX |
| Physical pin 6 | GND | GND |

GPIO13/GPIO14 are the recommended T-Beam UART pins for this Meshtastic serial
connection.

The visible T-Beam GPIO1/GPIO3 TX/RX pins are UART0. They are shared with USB
serial/programming, so they are **not** the preferred pins for this integration.

Pi GPIO UART is 3.3 V. The T-Beam UART is 3.3 V. Direct TX/RX/GND is correct.

## Meshtastic configuration

Flash Meshtastic onto the T-Beam, then enable the Serial Module:

| Setting | Value |
|---|---|
| Enabled | YES |
| Mode | TEXTMSG |
| TX GPIO | 14 |
| RX GPIO | 13 |
| Baud | 38400 |

CLI example (use the T-Beam USB port while configuring, not the Pi UART):

```bash
meshtastic --set serial.enabled true
meshtastic --set serial.mode TEXTMSG
meshtastic --set serial.txd 14
meshtastic --set serial.rxd 13
meshtastic --set serial.baud 38400
```

Put the T-Beam and every receiving node on the same channel and key. After
configuration, disconnect the USB serial session if it would fight the GPIO
UART, power the T-Beam on its own supply, and wire TX/RX/GND as above.

The Pi never talks a custom LoRa protocol. It only writes a newline-terminated
text line. Meshtastic TEXTMSG turns that line into a normal mesh text message.

## Raspberry Pi UART configuration

Preferred device: `/dev/serial0` (override with `UART_PORT`).

1. Disable the serial login console and enable the serial hardware:

```bash
sudo raspi-config
# Interface Options -> Serial Port
#   login shell over serial: No
#   serial port hardware enabled: Yes
```

2. On Raspberry Pi 4, free the PL011 UART from Bluetooth if `/dev/serial0`
   is not on the GPIO header. In `/boot/firmware/config.txt` (Bookworm) or
   `/boot/config.txt`:

```
enable_uart=1
dtoverlay=disable-bt
```

3. Reboot, then confirm the device and permissions:

```bash
sudo reboot
ls -l /dev/serial0
sudo usermod -aG dialout "$USER"
```

Default baud is **38400** (`UART_BAUD`).

## Installation

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential \
    libgl1 libglib2.0-0 libopenjp2-7 libtiff6 libatlas-base-dev

cd /path/to/raspberryLora
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p models
```

Place `models/yolov8n.pt` on the Pi if you can (about 6 MB). If the file is
missing and `DETECTION_BACKEND=yolo`, Ultralytics may download `yolov8n.pt`
once. Do not point this project at large YOLO weights (`yolov8s/m/l/x`,
YOLOv5m+, etc.).

If the Pi restarts under YOLO (RAM), skip the neural-net extra packages and
use HOG:

```bash
pip install opencv-python numpy pyserial
python3 app.py --backend hog --display
```

## Running the program

```bash
source venv/bin/activate

# Full pipeline (GPIO UART -> T-Beam)
python3 app.py --display

# Detection only (no UART)
python3 app.py --no-uart --display --person-only

# HOG backend (lightest, no PyTorch)
python3 app.py --backend hog --display
```

Useful environment variables:

```bash
export UART_PORT=/dev/serial0
export UART_BAUD=38400
export FRAME_WIDTH=640
export FRAME_HEIGHT=360
export INFER_SIZE=320
export TARGET_INFERENCE_FPS=7
export PERSON_CONFIDENCE_THRESHOLD=0.45
export WEAPON_CONFIDENCE_THRESHOLD=0.40
export CONFIRMATION_FRAMES=3
export EVENT_COOLDOWN_SECONDS=30
```

## Detection configuration

| Variable / flag | Default | Meaning |
|---|---|---|
| `DETECTION_BACKEND` / `--backend` | `yolo` | `yolo` (YOLOv8n) or `hog` |
| `PERSON_MODEL` / `--person-model` | `models/yolov8n.pt` | Person weights |
| `WEAPON_MODEL` / `--weapon-model` | empty | Optional weapon-class model |
| `PERSON_CONFIDENCE_THRESHOLD` | `0.45` | Person score |
| `WEAPON_CONFIDENCE_THRESHOLD` | `0.40` | Weapon score |
| `INFER_SIZE` | `320` | YOLO input size |
| `FRAME_WIDTH` x `FRAME_HEIGHT` | `640x360` | Capture size |
| `TARGET_INFERENCE_FPS` | `7` | Cap inference rate (5–10 target) |
| `CONFIRMATION_FRAMES` | `3` | Consistent frames before an event |
| `EVENT_COOLDOWN_SECONDS` | `30` | Repeat of the same state |
| `STATE_CHANGE_ONLY` | `false` | If true, never resend the same state |
| `--person-only` | off | Do not load a weapon model |
| `--display` | off | Local OpenCV preview with boxes |
| `--no-uart` | off | Run vision without the radio |

Person detection and weapon classification are separate. Flow:

1. Detect persons on the frame
2. If a weapon model is enabled, run it on each expanded person crop
3. A weapon counts only when it overlaps that person region
4. No person in the frame → no `PERSON WPN` event
5. A weapon outside every person region is drawn as `WPN` locally but does
   not generate a mesh event

## Message format

Built only by `format_detection_message()` in `message_formatter.py`:

```
PERSON NO_WPN YYYY-MM-DD HH:MM:SS
PERSON WPN YYYY-MM-DD HH:MM:SS
```

Timestamp is the Pi local clock, without milliseconds.

## Receiver setup

Receivers do **not** run this Raspberry Pi application.

Any Meshtastic node (phone app, another T-Beam, a T-Echo, etc.) on the same
channel already shows the text as a normal chat message.

Optional: if a computer is attached to a receiving node that also has Serial
TEXTMSG enabled, print incoming lines:

```bash
python3 tools/receive_meshtastic.py --port /dev/ttyUSB0 --baud 38400
```

Output:

```
RECEIVED:
PERSON NO_WPN 2026-08-20 11:25:31
```

## Bring-up sequence

Do not debug camera inference and UART at the same time.

**STEP 1 — UART only**

```bash
python3 tools/test_uart.py "hello"
```

**STEP 2 — Mesh text**

```bash
python3 tools/test_uart.py "TEST MESHTASTIC UART"
```

Confirm `TEST MESHTASTIC UART` on another Meshtastic node.

**STEP 3 — Message formatter**

```bash
python3 -m unittest tests.test_message_formatter -v
```

**STEP 4 — Person detection only**

```bash
python3 app.py --no-uart --person-only --display
```

**STEP 5 — Weapon classification**

Only after a real weapon-class model file exists:

```bash
export WEAPON_MODEL=/path/to/weapon.pt
python3 app.py --no-uart --display
```

**STEP 6 — Detection events to UART**

```bash
python3 tools/test_uart.py "PERSON NO_WPN 2026-08-20 11:25:31"
python3 app.py --display
```

**STEP 7 — Complete application**

```bash
python3 app.py --display
```

## Troubleshooting

**No `/dev/serial0`**
Enable UART as above and reboot. On Pi 4 also disable Bluetooth overlay if
the GPIO header is still attached to Mini-UART incorrectly.

**UART opens, mesh hears nothing**
Confirm Serial Module TEXTMSG, TX=14, RX=13, baud 38400. Confirm TX/RX are
crossed (Pi TX → T-Beam RX). Confirm common GND. Confirm the T-Beam is
powered independently. Confirm channel/key match.

**Permission denied on the serial device**

```bash
sudo usermod -aG dialout "$USER"
# log out and back in
```

**Camera missing**

```bash
ls /dev/video*
python3 -c "import cv2; c=cv2.VideoCapture(0); print(c.isOpened()); c.release()"
```

**Pi reboots while detecting**
The process is too heavy. Use `--backend hog`, lower `--infer-size 256`,
`--width 640 --height 360`, leave `--display` off, and do not load a second
weapon model until person-only is stable.

**Always `PERSON NO_WPN` even with a visible weapon**
Expected unless `WEAPON_MODEL` points at a file whose classes include your
`WEAPON_CLASSES`. Stock `yolov8n.pt` is not a weapon detector.

## Performance tuning / CPU / RAM

Target **5–10 inference FPS**, not full camera FPS.

| Knob | Lighter setting |
|---|---|
| Backend | `hog` then `yolo` |
| Capture | `640x360` (or `640x480`) |
| `INFER_SIZE` | `320` or `256` |
| Display | off |
| Weapon model | unset until needed |
| Frame rate cap | `TARGET_INFERENCE_FPS=5` |

YOLOv8n + PyTorch is the main RAM user (often several hundred MB). OpenCV HOG
avoids PyTorch. Never queue camera frames; the capture buffer is size 1.
The UART writer is a background thread so a blocked serial port cannot stall
inference. Models are loaded once.

CTRL+C and SIGTERM stop the camera, close OpenCV windows, and close UART.

## Project layout

```
app.py
camera.py
detector.py
event_manager.py
message_formatter.py
uart_meshtastic.py
config.py
requirements.txt
README.md
tests/test_message_formatter.py
tests/test_event_manager.py
tests/test_detector.py
tools/test_uart.py
tools/receive_meshtastic.py
```
