# Wiring Guide - Detailed Instructions

## 📍 Overview
This document provides detailed wiring instructions for connecting:
1. Raspberry Pi 4B
2. LILYGO LoRa32 (ESP32 + SX1276)
3. USB Camera
4. Optional USB GPS Module

---

## 🔗 Raspberry Pi to LILYGO LoRa32 (UART)

### Pinout Reference

#### Raspberry Pi 4B GPIO Header (40-pin)
```
Looking at RPi with USB ports on right:

   [01] 3.3V         [02] 5V
   [03] GPIO2 (SDA)  [04] 5V
   [05] GPIO3 (SCL)  [06] GND
   [07] GPIO4        [08] GPIO14 (TXD0) ← TX to ESP32
   [09] GND          [10] GPIO15 (RXD0) ← RX from ESP32
   [11] GPIO17       [12] GPIO18
   ...
   [39] GND          [40] GPIO21
```

#### LILYGO LoRa32 Pin Locations
```
Looking at board with antenna on right:

ESP32 Side          Description
────────────────────────────────
USB-C Port          Serial programming
5V                  Power input
GND                 Ground
GPIO16 (RX2)        UART RX from RPi
GPIO17 (TX2)        UART TX to RPi
SPI Pins            LoRa module (SX1276)
```

### Connection Diagram

```
┌─────────────────────┐          ┌──────────────────┐
│  Raspberry Pi 4B    │          │ LILYGO LoRa32    │
└─────────────────────┘          └──────────────────┘

Pin 8 (GPIO14)      ┌─ Resistor Divider ─┐
   TX           ────┤ 1kΩ resistor       ├──→ GPIO16 (RX2)
                    │ 2kΩ to GND         │
                    └────────────────────┘

Pin 10 (GPIO15)
   RX           ─────────────────────────→ GPIO17 (TX2)

Pin 6 (GND)     ─────────────────────────→ GND

Pin 4 (5V)      ─────────────────────────→ 5V or VBUS
```

**Important Note**: The voltage divider on RX is required because:
- Raspberry Pi outputs 3.3V on GPIO14, but ESP32 input is 3.3V tolerant ✓
- But if using 5V supply reference, use divider to be safe
- Divider formula: Vout = Vin × R2/(R1+R2) = 5V × 2k/(1k+2k) ≈ 3.3V

### Component List (UART Connection)
- 1 × 1kΩ resistor (1/4W)
- 1 × 2kΩ resistor (1/4W)
- 3 × Jumper wires (male-to-male)

---

## 🎥 USB Camera

### Connection
Simply plug Logitech USB camera into any USB 3.0 port (blue ports) on Raspberry Pi.

**Supported Ports**:
- USB 3.0 (2x blue ports) - preferred
- USB 2.0 (2x black ports) - works but slower

**Device Mapping**:
```bash
# Primary camera
/dev/video0   → device ID 0 in code

# Secondary camera (if connected)
/dev/video1   → device ID 1 in code
```

**Camera Mounting**:
```
Recommended setup:
┌─────────────────────┐
│  Raspberry Pi       │
│  ┌───────────────┐  │
│  │   Heatsink    │  │
│  └───────────────┘  │
│  ┌───────────────┐  │
│  │   USB Camera  │  ← Mount with zip-tie
│  └───────────────┘  │
│  [USB] [USB][USB]   │
└─────────────────────┘
    ↑
  USB 3.0 (blue)
```

---

## 🗺️ Optional GPS Module

### USB GPS Connection
```bash
/dev/ttyUSB0  ← (if LoRa not using this)
/dev/ttyUSB1  ← (if LoRa uses ttyUSB0)
/dev/ttyUSB2  ← (if multiple modules)
```

### Setup Commands
```bash
# Find GPS device
ls -la /dev/ttyUSB*

# Test connection at 9600 baud
cat < /dev/ttyUSB1 &
stty -F /dev/ttyUSB1 9600

# See NMEA sentences: $GPGGA, $GPRMC, etc.
```

### NMEA Message Format
```
$GPGGA,141015.00,4717.113421,N,00833.915187,E,...
       └─ time   └─ lat      └─ lon
```

---

## ⚡ Power Considerations

### Raspberry Pi Power
```
Recommended: 5V 3A USB-C power supply
Minimum: 5V 2.5A

Under-voltage warning (~4.6V):
- LEDs may blink
- Performance degradation
- Potential system crashes

Safe voltage: 5.0V - 5.25V
```

### LILYGO LoRa32 Power
```
Input: 5V USB-C or 3.3V regulator pin
Typical Current: 50-100mA (idle)
Peak Current: 200mA (transmitting)

USB-C to RPi 5V is typical configuration
```

### Total System Power
```
Idle:     ~1.5A (5V)
Active:   ~2.5A (5V)
Peak TX:  ~3.0A (5V)
```

**Power Budget**:
- Raspberry Pi: ~2.0A
- LoRa Module: ~0.2A
- Camera: ~0.5A
- GPS (if used): ~0.1A
- **Total: ~2.8A peak**

---

## 🔌 USB Hub Alternative Setup

For systems with multiple USB devices:

```
┌────────────────────┐
│  5V Power Supply   │
│    (4A, USB-C)     │
└────────────────────┘
         ↓
   ┌──────────┐
   │   RPi    │
   └──────────┘
         ↓
┌──────────────────────┐
│  USB 3.0 Hub (4 port)│
├──────────────────────┤
│ Port 1: Camera       │
│ Port 2: LoRa (USB)   │
│ Port 3: GPS (USB)    │
│ Port 4: (Spare)      │
└──────────────────────┘
```

**Recommended Hub**:
- Powered USB 3.0 hub
- 4+ ports
- Separate 5V power input (important!)

---

## 📋 Connection Verification Checklist

### Before Power On
- [ ] GPIO14 connected to GPIO16 via resistor divider
- [ ] GPIO15 connected to GPIO17
- [ ] GND connected together
- [ ] 5V connections secure
- [ ] No exposed wires or shorts
- [ ] Heatsink on Raspberry Pi

### After Power On

```bash
# 1. Check serial ports
ls -la /dev/tty*

# 2. Test UART communication
python3 << 'EOF'
from lora.serial_handler import SerialHandler
handler = SerialHandler(port="/dev/ttyUSB0")
if handler.connect():
    print("✓ LoRa connection OK")
    handler.disconnect()
else:
    print("✗ LoRa connection failed")
EOF

# 3. Test camera
python3 << 'EOF'
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("✓ Camera OK")
    cap.release()
else:
    print("✗ Camera not found")
EOF

# 4. Test GPS (if connected)
python3 << 'EOF'
from utils.gps import GPSHandler
gps = GPSHandler(use_simulation=True)
lat, lon = gps.get_location()
print(f"✓ GPS OK: {lat}, {lon}")
EOF
```

---

## 🚨 Troubleshooting Connections

### No LoRa Communication

**Symptoms**: "Failed to connect to /dev/ttyUSB0"

**Solutions**:
1. Check cable connections
2. Verify ESP32 is powered on (LED on board)
3. Check baud rate (should be 115200)
4. Try different USB port
5. ESP32 may need reset (press RST button)

```bash
# Manual reset ESP32
# Hold GPIO0 button for 2 seconds while powered
```

### Camera Not Detected

**Symptoms**: "Failed to open camera 0"

**Solutions**:
1. Try different camera ID (0, 1, 2, 3)
2. Check USB cable is data cable (not power-only)
3. Use powered USB hub if low power
4. Try different USB port

```bash
# Find camera device
for i in {0..9}; do
  python3 -c "import cv2; cap=cv2.VideoCapture($i); print(f'Video{$i}: {cap.isOpened()}')"
done
```

### No Power

**Symptoms**: RPi or ESP32 doesn't turn on

**Solutions**:
1. Check 5V power supply (use multimeter)
2. Check USB cable isn't damaged
3. Check micro-USB (RPi) or USB-C (ESP32) port for debris
4. Try different power cable

---

## 📐 Alternative Configurations

### Configuration A: GPIO Serial Port (No USB Required)
```
RPi GPIO14 (TX)  → Resistor → ESP32 GPIO16 (RX)
RPi GPIO15 (RX)  → ESP32 GPIO17 (TX)
RPi GND          → ESP32 GND
```

### Configuration B: Multiple LoRa Nodes
```
                    ┌─ LoRa1 (ESP32)
RPi ─ USB Hub ──┤├─ LoRa2 (Feather)
                    └─ LoRa3 (etc.)
```

### Configuration C: Jetson Nano Upgrade Path
```
Current: Raspberry Pi 4B (ARM, CPU only)
Future:  Jetson Nano (ARM, +GPU accelerator)
```

---

## 🧪 Test Scripts

### Test All Connections

```bash
#!/bin/bash
# save as: test_connections.sh
# run with: bash test_connections.sh

echo "=== Testing All Connections ==="

# Test UART
echo -n "UART (LoRa): "
python3 -c "from lora.serial_handler import SerialHandler; h = SerialHandler(); print('OK' if h.connect() else 'FAIL'); h.disconnect()" 2>/dev/null || echo "FAIL"

# Test Camera
echo -n "Camera: "
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'FAIL'); cap.release()" 2>/dev/null || echo "FAIL"

# Test GPS
echo -n "GPS: "
python3 -c "from utils.gps import GPSHandler; gps = GPSHandler(use_simulation=True); print('OK')" 2>/dev/null || echo "FAIL"

echo "=== Tests Complete ==="
```

---

## 📞 Hardware Support

**Raspberry Pi**:
- https://www.raspberrypi.org/documentation/hardware/

**LILYGO LoRa32**:
- https://github.com/Xinyuan-LilyGO/LilyGO-LoRa-Series
- Datasheet: ESP32 + SX1276

**Camera**:
- Logitech: https://support.logi.com/

---

**Version**: 1.0
**Last Updated**: June 2026
