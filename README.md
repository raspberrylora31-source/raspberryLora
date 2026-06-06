# Real-Time Object Detection with LoRa and IP Geolocation

Lightweight Raspberry Pi 4B system for detecting people from a USB camera,
printing an event with approximate latitude/longitude, and broadcasting the
event through a LILYGO LoRa32/ESP32 module.

## What it does

- Captures frames from a USB camera with OpenCV.
- Runs YOLO person detection on CPU.
- Classifies events as `Person without weapon` or `Person with weapon`.
- Fetches approximate location from public IP geolocation.
- Caches coordinates and refreshes only on a cooldown.
- Logs detections locally and sends LoRa messages with throttling.

IP geolocation is approximate, not true GPS. Accuracy depends on the public
network, ISP routing, VPNs, mobile hotspots, and carrier NAT. It is commonly
city-level or region-level, not device-level.

## Hardware

- Raspberry Pi 4B with 4 GB RAM.
- 16 GB or larger microSD card.
- 5V 3A USB-C power supply.
- USB webcam compatible with OpenCV.
- LILYGO LoRa32 or ESP32 with SX1276 LoRa module.

## Wiring

UART wiring from Raspberry Pi to ESP32:

```text
Raspberry Pi 4B            LILYGO LoRa32 / ESP32
Pin 8  GPIO14 TX  ------>  RX GPIO16
Pin 10 GPIO15 RX  <------  TX GPIO17
Pin 6  GND        -------  GND
Pin 4  5V         -------  5V
```

Use a voltage divider on Raspberry Pi TX if your ESP32 board is not 5V tolerant.
The USB camera connects to any available USB port.

## Install

```bash
cd ~/raspberryLora
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Enable UART on Raspberry Pi if you use direct GPIO UART:

```text
enable_uart=1
```

Add it to `/boot/firmware/config.txt` or `/boot/config.txt`, then reboot.

## Run

Default run:

```bash
python main.py
```

Run with camera display:

```bash
python main.py --display
```

Pi-tested run command:

```bash
python main.py --model yolov5n --skip-frames 1 --confidence 0.45 --display
```

Run with explicit serial port and IP location settings:

```bash
python main.py \
  --camera 0 \
  --width 640 \
  --height 480 \
  --confidence 0.45 \
  --skip-frames 2 \
  --lora-port /dev/ttyUSB0 \
  --lora-cooldown 30 \
  --location-update-interval 25 \
  --location-timeout 3 \
  --location-retries 2
```

Use `ip-api.com` instead of the default API:

```bash
python main.py --location-api-url http://ip-api.com/json/
```

## Output

```text
Entity: Person without weapon
Date and Time: 2026-06-06 14:20:11
Location: 12.9716,77.5946
```

Example debug output:

```text
IP geolocation enabled
Note: IP geolocation is approximate, not true GPS
Fetching IP location (attempt 1/2) from https://ipinfo.io/json
Updated IP location: 12.9716,77.5946
Using cached IP location: 12.9716,77.5946
```

## Location behavior

- Location lookup happens only when a person detection is processed.
- The default API is `https://ipinfo.io/json`.
- The handler caches the latest successful coordinates in memory.
- The default refresh cooldown is 25 seconds.
- Failed requests retry, then fall back to the last known coordinates.
- If no request has ever succeeded, fallback is `0.0000,0.0000`.

## Command-line options

```text
--model {yolov5n,yolov8n}          Detection model.
--camera CAMERA_ID                 Camera device ID.
--width WIDTH                      Camera frame width.
--height HEIGHT                    Camera frame height.
--confidence THRESHOLD             Detection confidence threshold.
--skip-frames N                    Process every Nth frame.
--lora-connection TYPE             uart, usb, wifi, http, ble, or btc.
--lora-port PORT                   Serial port for UART/USB LoRa.
--lora-wifi-host HOST              ESP32 WiFi host.
--lora-wifi-port PORT              ESP32 WiFi port.
--lora-cooldown SECONDS            LoRa duplicate-message cooldown.
--location-update-interval SECONDS Seconds between IP geolocation refreshes.
--location-timeout SECONDS         IP geolocation request timeout.
--location-retries N               IP geolocation retry attempts.
--location-api-url URL             IP geolocation endpoint.
--display                          Show camera feed with annotations.
```

## Project structure

```text
main.py                    Main detection loop and CLI.
detector/model_loader.py   YOLO model loading.
detector/detect.py         Person detection and frame annotation.
lora/serial_handler.py     UART, USB, WiFi, and Bluetooth transport helpers.
lora/send_lora.py          LoRa message formatting and cooldown.
utils/gps.py               Lightweight IP geolocation cache.
utils/logger.py            Local detection and error logging.
requirements.txt           Python dependencies.
install.sh                 Optional Raspberry Pi setup helper.
esp32_lora_receiver.ino    ESP32 LoRa receiver firmware.
```

## Minimal dependencies

Core Python dependencies are in `requirements.txt`.

- `opencv-python` for camera capture.
- `torch`, `torchvision`, `ultralytics`, and `yolov5` for detection.
- `requests` for lightweight IP geolocation.
- `pyserial` for UART/USB LoRa.
- `numpy`, `Pillow`, and `scipy` for image/model support.

No cloud SDK is required for location.

## Testing commands

Check camera:

```bash
python - <<'PY'
import cv2
cap = cv2.VideoCapture(0)
print("camera opened:", cap.isOpened())
if cap.isOpened():
    ok, frame = cap.read()
    print("frame captured:", ok, None if not ok else frame.shape)
cap.release()
PY
```

Check IP geolocation:

```bash
python - <<'PY'
from utils.gps import GPSHandler
gps = GPSHandler(update_interval_seconds=25, timeout_seconds=5, max_retries=2)
print("Location:", ",".join(gps.get_current_location()))
PY
```

Check serial ports:

```bash
python - <<'PY'
from lora.serial_handler import SerialHandler
print("Available serial ports:", SerialHandler.find_serial_ports())
PY
```

Compile Python sources:

```bash
python -m compileall main.py detector lora utils
```

## Troubleshooting

Camera does not open:

- Check `ls /dev/video*`.
- Try another camera index: `python main.py --camera 1`.
- Confirm the camera works outside Python.

LoRa cannot connect:

- Check `ls /dev/ttyUSB* /dev/ttyAMA*`.
- Verify UART is enabled and permissions allow access.
- Confirm the ESP32 firmware is running at 115200 baud.

Location is wrong:

- IP geolocation is approximate by design.
- VPNs, mobile hotspots, and ISP routing can place the device in another city.
- Try `--location-api-url http://ip-api.com/json/`.

Model download fails:

```bash
rm -rf ~/.cache/torch/hub/
python main.py
```

Out of memory:

- Lower resolution with `--width 320 --height 240`.
- Increase `--skip-frames`.
- Run without `--display`.

## Logs

Runtime logs are written under `logs/`:

```text
logs/detections.log
logs/errors.log
```

These files are runtime artifacts and should not be used as documentation.
