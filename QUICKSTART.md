# Quick Start Guide

## ⚡ 5-Minute Setup

### Prerequisites
- Raspberry Pi 4B with Raspberry Pi OS
- USB Camera connected
- LILYGO LoRa32 connected via UART

### Step 1: Clone Project (2 min)
```bash
cd /home/lora
git clone <repository-url> raspberryLora
cd raspberryLora
```

### Step 2: Install Dependencies (3 min)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Run (1 min)
```bash
python3 main.py --gps-simulation
```

## 🎯 Test Detection
1. Hold object in front of camera
2. Check terminal for detection output
3. Verify LoRa message sent to ESP32
4. Check logs in `logs/` directory

## 🔧 Troubleshooting Quick Links
- Camera issue? → See README.md "Camera Not Found"
- LoRa issue? → See README.md "LoRa Connection Failed"
- Out of memory? → See README.md "Out of Memory"

## 📊 Common Commands

```bash
# Run with minimal resources
python3 main.py --skip-frames 3 --width 320 --height 240

# Run with visual display
python3 main.py --display

# Use different model
python3 main.py --model yolov8n

# Adjust detection sensitivity
python3 main.py --confidence 0.5

# Use real GPS module
python3 main.py --no-gps-simulation
```

## 📁 Key Files
- `main.py` - Entry point
- `logs/detections.log` - All detections
- `logs/errors.log` - Error messages
- `.env` - Configuration (create as needed)

---

For detailed setup, see **README.md**
