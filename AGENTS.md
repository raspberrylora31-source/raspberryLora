# AGENTS.md

## Cursor Cloud specific instructions

### Product overview

Single Python application: real-time YOLO person detection on Raspberry Pi with optional LoRa (ESP32) and GPS. Entry point is `main.py`. There is no web server, database, or Docker stack.

### Environment (Cloud VM vs Raspberry Pi)

- **Cloud VM / x86 dev:** Python 3.12 is typical. Pinned versions in `requirements.txt` (`torch==2.0.1`, `numpy==1.24.3`) do **not** install on Python 3.12. The VM update script installs Python-3.12-compatible packages instead (newer `torch`, `numpy>=1.26,<2`, `opencv-python>=4.10`, upgraded `ultralytics`).
- **Raspberry Pi (target hardware):** Follow `README.md` / `install.sh` with Python 3.9+ and `pip install -r requirements.txt`. `install.sh` assumes project path `/home/lora/raspberryLora` and is interactive (UART config, systemd prompts).

System packages needed on Ubuntu/Debian dev VMs:

```bash
sudo apt-get install -y python3-venv python3-dev build-essential libgl1 libglib2.0-0
```

### Activate and run

```bash
source venv/bin/activate
python3 main.py --help
python3 main.py --gps-simulation          # needs USB camera + optional ESP32 serial
```

### Known issue: `utils` package name collision

The project top-level package `utils/` shadows YOLOv5's internal `utils` module during `torch.hub.load`, so **`main.py` fails at model load** with:

`ImportError: cannot import name 'TryExcept' from 'utils'`

Workaround for manual/integration testing (load model before importing project `utils`, then clear cached `utils*` modules):

```python
import sys
WORKSPACE = "/workspace"  # repo root
sys.path.insert(0, WORKSPACE)
from detector.model_loader import YOLOModelLoader
sys.path = [p for p in sys.path if p != WORKSPACE]
model = YOLOModelLoader("yolov5n").load_model()
for key in list(sys.modules):
    if key == "utils" or key.startswith("utils."):
        del sys.modules[key]
sys.path.insert(0, WORKSPACE)
from utils import GPSHandler, LocalLogger  # now safe
```

First YOLO load also requires network access; newer PyTorch hub prompts for repo trust unless the repo is already cached/trusted.

### Services

| Service | Required for | Notes |
|---------|----------------|-------|
| Python venv + deps | All dev work | `source venv/bin/activate` |
| `main.py` | Full app loop | USB camera (`/dev/video0`); LoRa optional (`/dev/ttyUSB0`) |
| ESP32 firmware | LoRa E2E | Flash `esp32_lora_receiver.ino` on device (Arduino IDE) |

### Verify without hardware (Cloud VM)

Run the README integration flow (model + GPS + logger + inference on a sample image):

```bash
source venv/bin/activate
python3 - <<'PY'
import sys
WORKSPACE = "/workspace"
sys.path.insert(0, WORKSPACE)
from detector.model_loader import YOLOModelLoader
sys.path = [p for p in sys.path if p != WORKSPACE]
model = YOLOModelLoader("yolov5n").load_model()
for k in list(sys.modules):
    if k == "utils" or k.startswith("utils."):
        del sys.modules[k]
sys.path.insert(0, WORKSPACE)
from detector.detect import ObjectDetector
from utils import GPSHandler, LocalLogger
import cv2, urllib.request
gps = GPSHandler(use_simulation=True)
lat, lon = gps.get_location()
LocalLogger().log_detection("Test", lat, lon)
detector = ObjectDetector(model=model, skip_frames=1)
urllib.request.urlretrieve("https://ultralytics.com/images/bus.jpg", "/tmp/bus.jpg")
entity, _ = detector.detect_combined(cv2.imread("/tmp/bus.jpg"))
print(entity, lat, lon)
PY
```

Expected: `Person without weapon` and entries in `logs/detections.log`.

### Lint / tests

- No project linter config (no `ruff.toml`, `flake8`, etc.).
- README references `tests/test_*.py` but **no `tests/` directory exists**; use the integration snippet above instead.
- `pybluez` in `requirements.txt` is optional (Classic Bluetooth) and often fails to build on Python 3.12; skip unless testing `--lora-connection btc`.

### Optional deps

- `bleak` — BLE LoRa connection mode
- `requests`, `websocket-client` — WiFi/HTTP ESP32 modes
