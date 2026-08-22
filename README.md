# 1. What the project does

This Raspberry Pi application watches a USB webcam, detects people, then
runs a **trained YOLOv5 weapon model** on each person crop. Confirmed
results are sent as a short UART text line to a LILYGO T-Beam running
Meshtastic. Other Meshtastic nodes receive the text on the LoRa mesh.

```
PERSON WPN 2026-08-22 09:15:31
PERSON NO_WPN 2026-08-22 09:16:04
```

The Pi does all computer vision. The T-Beam only runs Meshtastic.
Images, video, boxes, and JSON are never sent over LoRa.

Weapon detection is a required feature of the production pipeline.
`PERSON NO_WPN` means: a person was confirmed **and** `models/best.pt`
ran on that person crop and found no configured weapon class. A missing
weapon model is an error, not a NO_WPN event.

`--person-only` is a camera/person test. It does not load the weapon
model and does not talk to the T-Beam.

# 2. Hardware

- Raspberry Pi (Pi 4B, 4GB RAM recommended)
- USB webcam
- LILYGO T-Beam with Meshtastic firmware
- LoRa antenna on the T-Beam
- Independent power for the Pi and for the T-Beam (USB or supported T-Beam power)
- Three jumper wires: TX, RX, GND

Do not power the T-Beam UART from Raspberry Pi 5V.

# 3. Architecture

```
USB camera
→ person detector (YOLOv5n)
→ person bounding box
→ YOLOv5 weapon detector (models/best.pt) on each person crop
→ event manager (confirmation + cooldown)
→ timestamp (Pi clock)
→ compact text
→ GPIO UART /dev/serial0 @ 38400
→ Meshtastic Serial TEXTMSG
→ LoRa mesh
```

`app.py` is the only process you run for detection.

# 4. UART wiring

## Raspberry Pi                         LILYGO T-Beam

Physical pin 8
GPIO14 / TXD  --------------------> GPIO13 / RX

Physical pin 10
GPIO15 / RXD  <-------------------- GPIO14 / TX

Physical pin 6
GND          ---------------------- GND

Important:

Pi TX → T-Beam RX
Pi RX ← T-Beam TX
GND → GND

Do NOT connect Raspberry Pi 5V to the T-Beam UART.

Power the T-Beam appropriately through its own supported power/USB arrangement.

The T-Beam serial pins used by this application are:

GPIO13 = RX
GPIO14 = TX

Do not use GPIO1/GPIO3 for this application because those are associated with the ESP32 UART0/USB serial path.

# 5. Meshtastic configuration

Flash Meshtastic onto the T-Beam. Configure the Serial Module:

| Setting | Value |
|---|---|
| Serial enabled | YES |
| Serial mode | TEXTMSG |
| Serial RX | GPIO13 |
| Serial TX | GPIO14 |
| Baud | 38400 |

```bash
meshtastic --set serial.enabled true
meshtastic --set serial.mode TEXTMSG
meshtastic --set serial.rxd 13
meshtastic --set serial.txd 14
meshtastic --set serial.baud 38400
```

The Pi writes newline-terminated ASCII. Meshtastic TEXTMSG places that
line on the mesh. Other nodes on the same channel receive it as a normal
text message. This project does not implement a custom LoRa protocol and
does not use custom ESP32 firmware.

# 6. Raspberry Pi UART setup

1. Enable hardware serial and disable the serial login console:

```bash
sudo raspi-config
# Interface Options -> Serial Port
#   login shell over serial: No
#   serial port hardware enabled: Yes
```

2. On Raspberry Pi 4, put this in `/boot/firmware/config.txt` (Bookworm)
   or `/boot/config.txt`:

```
enable_uart=1
dtoverlay=disable-bt
```

3. Reboot, then verify:

```bash
sudo reboot
ls -l /dev/serial0
groups
sudo usermod -aG dialout "$USER"
```

Log out and back in so `groups` shows `dialout`. Default device is
`/dev/serial0` at **38400** baud.

# 7. Python environment

CPU only. The Pi does not need CUDA.

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential \
    libgl1 libglib2.0-0 libopenjp2-7 libatlas-base-dev

cd /path/to/raspberryLora
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p models
wget -O models/yolov5n.pt \
  https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5n.pt
```

`requirements.txt` installs OpenCV, NumPy, pandas, pyserial, PyTorch,
torchvision, and `ultralytics` (the current YOLOv5 runtime needs these
to load `yolov5n.pt` and `best.pt`).

A generic `pip install torch` or `pip install ultralytics` on the Pi
often pulls `torch==2.13.0+cu130` plus `nvidia-*` packages. The Pi 4
has no NVIDIA GPU. That wheel, and current official CPU wheels from
2.10 onward, use ARMv8.1 LSE atomics. Pi 4 Cortex-A72 is ARMv8.0, so
the first real tensor op dies with:

```
Illegal instruction
```

That is a CPU/ISA crash, not a camera or YOLO-weights problem. Skipping
`fuse()` is not enough. Install the known-good **CPU** pair:

```
torch==2.3.1
torchvision==0.18.1
```

```bash
source venv/bin/activate
bash tools/fix_pi_torch.sh
# or:
pip uninstall -y torch torchvision torchaudio
pip freeze | grep -E '^(nvidia-|cuda-)' | cut -d= -f1 | xargs -r pip uninstall -y
pip install torch==2.3.1 torchvision==0.18.1
python3 -c "import torch; print(torch.__version__); print(torch.zeros(1)+1)"
```

`requirements.txt` already pins those versions on `aarch64`. Do **not**
install the latest CPU wheel from `download.pytorch.org/whl/cpu` on a
Pi 4; 2.13+cpu can still SIGILL.

YOLOv5 will not start on an unsafe wheel. It prints an error instead of
opening the camera and dying. To prove the USB camera without YOLO:

```bash
python3 app.py --person-only --display --backend hog
```

# 8. Model installation

Place these files in `models/`:

| File | Role |
|---|---|
| `models/yolov5n.pt` | Lightweight YOLOv5n person detector |
| `models/best.pt` | **Required** trained YOLOv5 weapon model |

`models/best.pt` must be **your** trained YOLOv5 weapon-detection
weights. Do not use stock COCO YOLOv5 and pretend it detects weapons.
Do not use a YOLOv8 weapon export.

If `models/yolov5n.pt` is missing, the person detector may download
official YOLOv5n through torch.hub (needs network). Copying
`models/yolov5n.pt` onto the Pi is the reliable offline method.

If `models/best.pt` is missing, full detection **refuses to start**:

```
ERROR: Weapon detection is required but models/best.pt was not found.

Please place the trained YOLOv5 weapon model at:

models/best.pt
```

It will not emit `PERSON NO_WPN` in that situation.

At startup the app prints the model's real class names. Set
`WEAPON_CLASSES` to names that exist in **that** model.

```bash
# Empty = every non-person class in best.pt
export WEAPON_CLASSES=

# Single-class model {0: weapon}
export WEAPON_CLASSES=weapon

# Multi-class model {0: person, 1: pistol, 2: rifle}
export WEAPON_CLASSES=pistol,rifle
```

Never list `person` as a weapon class. If the configured names are not
in the model, full detection exits with an error.

# 9. CAMERA TEST

Prove the USB webcam and person boxes **before** loading the weapon
model. This mode does not need UART, the T-Beam, or `models/best.pt`.

These files must exist in the project directory (`app.py` or `main.py`).
If `python3` reports `can't open file .../app.py`, this tree is not on
the Pi yet — update the checkout, then run from that directory.

```bash
cd ~/raspberryLora
ls app.py main.py
source venv/bin/activate
python3 app.py --person-only --display
# same program:
python3 main.py --person-only --display
```

Success looks like:

- a live camera window
- green `PERSON` boxes on people
- `FPS` on the overlay
- every ~10 seconds in the terminal:

```
FPS: 5.2
RAM: 620 MB
CPU: 72%
```

Headless (no X/desktop):

```bash
python3 app.py --person-only --no-display
```

If the webcam is missing:

```
ERROR: USB camera could not be opened.
```

# 10. WEAPON DETECTION TEST

After the camera test works, and after `models/best.pt` is in place:

```bash
python3 app.py --no-uart --display
```

This verifies:

- USB camera
- person detection
- YOLOv5 weapon detection on person crops
- `PERSON WPN` / `PERSON NO_WPN` boxes
- no LoRa / UART

This is the main pre-production acceptance test.

# 11. UART TEST

Test the radio **before** debugging computer vision.

```bash
python3 tools/test_uart.py "TEST MESHTASTIC UART"
python3 tools/test_uart.py "PERSON NO_WPN 2026-08-22 09:15:31"
```

Another Meshtastic node on the same channel should show those exact
lines. If this fails, fix wiring and Serial TEXTMSG first.

# 12. FULL PRODUCTION RUN

```bash
source venv/bin/activate
python3 app.py --display
```

Headless:

```bash
source venv/bin/activate
python3 app.py --no-display
```

This runs person detection, YOLOv5 weapon detection, confirmation,
Pi timestamp, and UART → T-Beam → Meshtastic. A receiving node should
show:

```
PERSON NO_WPN 2026-08-22 09:15:31
PERSON WPN 2026-08-22 09:16:04
```

# 13. Environment variables/configuration

| Variable | Default | Meaning |
|---|---|---|
| `UART_PORT` | `/dev/serial0` | GPIO UART device |
| `UART_BAUD` | `38400` | Meshtastic serial baud |
| `PERSON_CONFIDENCE_THRESHOLD` | `0.45` | Person score |
| `WEAPON_CONFIDENCE_THRESHOLD` | `0.40` | Weapon score |
| `WEAPON_CLASSES` | empty (auto) | Names from `best.pt` |
| `CONFIRMATION_FRAMES` | `3` | Frames before an event |
| `EVENT_COOLDOWN_SECONDS` | `10` | Repeat of the same state |
| `TARGET_INFERENCE_FPS` | `5` | Inference cap (try 7 if stable) |
| `CAMERA_WIDTH` | `640` | Capture width |
| `CAMERA_HEIGHT` | `360` | Capture height |
| `PERSON_INFER_SIZE` | `320` | YOLOv5n input size |
| `WEAPON_INFER_SIZE` | `256` | Weapon crop input size |
| `WEAPON_MODEL` | `models/best.pt` | Trained YOLOv5 weapon weights |
| `PERSON_MODEL` | `models/yolov5n.pt` | YOLOv5n person weights |

# 14. Performance troubleshooting

The Pi has restarted under a heavy vision load. Keep weapon detection
**enabled**. Reduce work in this order:

1. Display — use `--no-display`
2. Inference FPS — `TARGET_INFERENCE_FPS=5` (do not chase 30 FPS)
3. Inference resolution — `PERSON_INFER_SIZE=256`, `WEAPON_INFER_SIZE=192`
4. Camera resolution — `CAMERA_WIDTH=640`, `CAMERA_HEIGHT=360`

Do not disable the weapon detector to save CPU.

Monitor on the Pi:

```bash
free -h
top
htop
vcgencmd measure_temp
vcgencmd get_throttled
```

The app also prints `FPS` / `RAM` / `CPU` about every 10 seconds.

# 15. Troubleshooting

**`can't open file '.../app.py'`**
The Pi still has the old tree (it had `main.py` only). Get the updated
files, `cd` into that directory, and run `ls app.py`. `main.py` is a
wrapper for the same program.

**Camera not detected**
`ls /dev/video*` then `python3 app.py --person-only --display`.
If it fails: `ERROR: USB camera could not be opened.`

**Model missing**
Full mode without `models/best.pt` exits with the required-model error.
Copy the trained YOLOv5 weapon weights to `models/best.pt`.

**Weapon class missing**
Startup prints the model's classes. Set `WEAPON_CLASSES` to those names.
A mismatch is an error, not a silent NO_WPN.

**RAM too high**
Lower infer sizes and FPS. Confirm with `free -h` and the 10-second RAM line.

**CPU too high**
`--no-display`, `TARGET_INFERENCE_FPS=5`, smaller infer sizes. Use `top`.

**Pi overheating**
`vcgencmd measure_temp` and `vcgencmd get_throttled`. Add a heatsink/fan.

**UART missing**
`ls -l /dev/serial0`. Enable hardware serial, disable serial console, reboot.

**Meshtastic not receiving**
Pass `tools/test_uart.py` first. Confirm TEXTMSG, GPIO13 RX, GPIO14 TX, 38400.

**TX/RX reversed**
Pi GPIO14 TX must go to T-Beam GPIO13 RX.

**No common GND**
Pi physical pin 6 must connect to T-Beam GND.

**Serial console still enabled**
Login-shell-over-serial must be No or `/dev/serial0` is not free.
