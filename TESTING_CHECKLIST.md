# Testing Checklist - Multi-Protocol Communication

## Purpose
Validate each connection method before deploying to production. Run in order from simplest to most complex.

---

## Phase 1: Prerequisites ✓

### Check System
- [ ] Raspberry Pi 4B running
- [ ] Camera connected and working: `python3 -c "import cv2; c=cv2.VideoCapture(0); print('Camera OK' if c.isOpened() else 'Camera FAIL')"`
- [ ] ESP32 LoRa module plugged in
- [ ] Python 3.7+ installed: `python3 --version`
- [ ] Required packages installed: `pip3 list | grep -E "torch|opencv|pyserial"`

### Check Dependencies
```bash
# Test core imports
python3 -c "
from lora.serial_handler import SerialHandler, ConnectionType
from detector.detect import ObjectDetector
from detector.model_loader import YOLOModelLoader
print('✓ All core imports successful')
"
```

---

## Phase 2: Default (UART) Testing ✓

### 2.1 Connection Test
```bash
python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('uart', port='/dev/ttyUSB0')
if handler.connect():
    print('✓ UART connection successful')
    handler.disconnect()
else:
    print('✗ UART connection failed')
"
```

### 2.2 Message Send Test
```bash
python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('uart', port='/dev/ttyUSB0')
handler.connect()
if handler.send_data('TEST:UART:MESSAGE'):
    print('✓ UART message sent')
else:
    print('✗ UART send failed')
handler.disconnect()
"
```

### 2.3 Full Detection Loop Test
```bash
python3 main.py --lora-connection uart 2>&1 | head -20
# Should show:
# - Model loaded
# - Camera initialized  
# - Connection established
# - Frame processing starting
```

**Expected Output:**
```
Model: YOLOv5n
Camera: OK
Connection: UART @ /dev/ttyUSB0
Waiting for detections...
```

---

## Phase 3: USB CDC-ACM Testing

### 3.1 Check USB Connection
```bash
# Verify USB device exists
ls -la /dev/ttyACM0

# Should output: crw-rw---- 1 root dialout ... /dev/ttyACM0
# If not found, check:
# - USB cable connection
# - Device drivers (dmesg | tail)
# - Try different port: /dev/ttyACM1, /dev/ttyACM2
```

### 3.2 USB Connection Test
```bash
python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('usb', port='/dev/ttyACM0')
if handler.connect():
    print('✓ USB CDC-ACM connection successful')
    handler.disconnect()
else:
    print('✗ USB connection failed - check port')
"
```

### 3.3 USB Message Send Test
```bash
python3 main.py --lora-connection usb --lora-port /dev/ttyACM0 2>&1 | head -20
# Should show USB connected instead of UART
```

**Common Issues:**
- Port mismatch: Try `dmesg | grep ttyACM` to find actual port
- Permissions: `sudo usermod -aG dialout $USER` then restart terminal
- Wrong device: Unplug all USB serials, identify correct one

---

## Phase 4: WiFi WebSocket Testing

### 4.1 Prerequisites
- [ ] Raspberry Pi connected to WiFi
- [ ] ESP32 WiFi configured (SSID/password set)
- [ ] Both devices on same network
- [ ] IP address of ESP32 known: `arp -a` or check router

### 4.2 Check Network Connectivity
```bash
# Find ESP32 IP
arp -a | grep -i esp32
# Or check router admin panel

# Test ping
ping 192.168.1.100  # Replace with actual IP
# Should get replies
```

### 4.3 WiFi WebSocket Connection Test
```bash
# First install websocket client if needed
pip3 install websocket-client

# Test connection
python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('wifi', wifi_host='192.168.1.100', wifi_port=8080)
if handler.connect():
    print('✓ WiFi WebSocket connected')
    handler.disconnect()
else:
    print('✗ WiFi WebSocket failed')
    print('Check: IP address, WiFi enabled on ESP32, firewall')
"
```

### 4.4 WiFi WebSocket Message Test
```bash
python3 main.py \
  --lora-connection wifi \
  --lora-wifi-host 192.168.1.100 \
  --lora-wifi-port 8080 \
  2>&1 | head -20
```

**Expected Output:**
```
Connection: WiFi WebSocket @ 192.168.1.100:8080
Status: Connected
Waiting for detections...
```

**Common Issues:**
- Connection timeout: Check firewall (`sudo ufw allow 8080`)
- Device not found: Verify IP address with `arp -a`
- Port refused: ESP32 not running WebSocket server firmware

---

## Phase 5: WiFi HTTP Testing

### 5.1 WiFi HTTP Connection Test
```bash
# Install requests if needed
pip3 install requests

python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('http', wifi_host='192.168.1.100', wifi_port=8080)
if handler.connect():
    print('✓ WiFi HTTP connected')
    handler.disconnect()
else:
    print('✗ WiFi HTTP failed')
"
```

### 5.2 WiFi HTTP Message Test
```bash
python3 main.py \
  --lora-connection http \
  --lora-wifi-host 192.168.1.100 \
  2>&1 | head -20
```

**Expected Output:**
```
Connection: WiFi HTTP @ 192.168.1.100
Status: Connected
Waiting for detections...
```

**Common Issues:**
- Slower latency (100-200ms) vs WebSocket
- Verify ESP32 running HTTP endpoint (`/send`)
- Check requests library: `pip3 install requests`

---

## Phase 6: Bluetooth Low Energy (BLE) Testing

### 6.1 Prerequisites
- [ ] Bluetooth enabled on Raspberry Pi: `hciconfig`
- [ ] ESP32 BLE firmware uploaded
- [ ] Devices not paired yet (start fresh)

### 6.2 Check Bluetooth
```bash
# Check if Bluetooth available
hciconfig
# Should show: hci0: Type: Primary  Bus: UART

# Start scanning
bluetoothctl
# In bluetoothctl prompt:
# > scan on
# > devices
# Find ESP32-LoRa in list
# > quit
```

### 6.3 BLE Connection Test
```bash
# Install bleak if needed
pip3 install bleak

python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('ble', device_name='ESP32-LoRa')
if handler.connect():
    print('✓ BLE connection successful')
    handler.disconnect()
else:
    print('✗ BLE failed - check device name')
"
```

### 6.4 BLE Message Test
```bash
python3 main.py \
  --lora-connection ble \
  --lora-device "ESP32-LoRa" \
  2>&1 | head -20
```

**Expected Output:**
```
Connection: Bluetooth BLE (ESP32-LoRa)
Status: Connected
Waiting for detections...
```

**Common Issues:**
- Device not found: Check `bluetoothctl scan on`
- Name mismatch: Find correct name in `devices` list
- Not installed: `pip3 install bleak`
- Requires async refactor: See COMMUNICATION_GUIDE.md

---

## Phase 7: Bluetooth Classic Testing

### 7.1 Check Bluetooth Availability
```bash
# Same as BLE
hciconfig
bluetoothctl
```

### 7.2 Bluetooth Classic Connection Test
```bash
# Install pybluez if needed
pip3 install pybluez

python3 -c "
from lora.serial_handler import SerialHandler
handler = SerialHandler('btc', device_name='ESP32-LoRa')
if handler.connect():
    print('✓ Bluetooth Classic connected')
    handler.disconnect()
else:
    print('✗ Bluetooth Classic failed')
"
```

### 7.3 Bluetooth Classic Test Run
```bash
python3 main.py \
  --lora-connection btc \
  --lora-device "ESP32-LoRa" \
  2>&1 | head -20
```

**Note:** Bluetooth Classic is legacy - use BLE if possible.

---

## Phase 8: Performance Benchmarking

Once all connections work, measure performance:

### 8.1 Latency Test
```bash
# Add timing to detect.py, measure total latency per frame
python3 -c "
import time
from lora.serial_handler import SerialHandler

methods = ['uart', 'usb', 'wifi', 'http', 'ble']
for method in methods:
    handler = SerialHandler(method)
    if handler.connect():
        start = time.time()
        for _ in range(10):
            handler.send_data('TEST')
        elapsed = time.time() - start
        print(f'{method}: {elapsed/10*1000:.1f}ms average')
        handler.disconnect()
"
```

### 8.2 Memory Usage
```bash
# Run with top in separate terminal
python3 main.py --lora-connection uart

# In another terminal:
# top -p $(pgrep -f "main.py")
# Check RSS (memory) and CPU columns
```

### 8.3 Detection Rate
```bash
# Count detections per minute
python3 main.py --lora-connection uart 2>&1 | \
  grep "Detection" | \
  wc -l
# Should be 5-10 per second at 640x480
```

---

## Phase 9: Production Readiness Checklist

### Connection Method
- [ ] Selected primary connection (UART / USB / WiFi / BLE)
- [ ] Selected fallback connection (if using hybrid)
- [ ] Tested on real deployment hardware
- [ ] All dependencies installed

### Performance
- [ ] Detection latency acceptable (<500ms)
- [ ] Memory usage stable (<600MB)
- [ ] CPU usage acceptable (<70%)
- [ ] Frame rate acceptable (5-10 fps)

### Reliability
- [ ] Connection drops handled gracefully
- [ ] Reconnection working
- [ ] No memory leaks after 1+ hour run
- [ ] Logs showing successful sends

### Documentation
- [ ] Correct command line options recorded
- [ ] Hardware setup documented
- [ ] IP addresses/ports documented
- [ ] Troubleshooting steps recorded

---

## Quick Test Command Reference

```bash
# Test UART (default)
python3 main.py

# Test USB
python3 main.py --lora-connection usb --lora-port /dev/ttyACM0

# Test WiFi WebSocket
python3 main.py --lora-connection wifi --lora-wifi-host 192.168.1.100

# Test WiFi HTTP
python3 main.py --lora-connection http --lora-wifi-host 192.168.1.100

# Test BLE
python3 main.py --lora-connection ble --lora-device "ESP32-LoRa"

# Test Bluetooth Classic
python3 main.py --lora-connection btc --lora-device "ESP32-LoRa"

# Monitor logs
tail -f logs/detections.log logs/errors.log

# Check connection in real-time
watch -n 1 "grep 'Connection\|Status' logs/errors.log | tail -5"
```

---

## Testing Results Log

Use this section to record your testing:

| Method | Date | Status | Latency | Notes |
|--------|------|--------|---------|-------|
| UART | | ✓/✗ | | |
| USB | | ✓/✗ | | |
| WiFi WS | | ✓/✗ | | |
| WiFi HTTP | | ✓/✗ | | |
| BLE | | ✓/✗ | | |
| Bluetooth | | ✓/✗ | | |

---

## Support Resources

- **Full Guide:** COMMUNICATION_GUIDE.md
- **Quick Reference:** CONNECTION_QUICK_REFERENCE.md
- **Firmware Examples:** esp32_firmware_options.ino
- **Main Code:** main.py
- **Handler Code:** lora/serial_handler.py

---

**Last Updated:** June 5, 2026  
**Version:** 2.0  
**Difficulty:** Intermediate

