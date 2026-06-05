# Troubleshooting Guide - Multi-Protocol Communication

## Quick Fix Checklist

Before diving deep, try these quick fixes first:

- [ ] **Restart everything:** Power cycle Raspberry Pi and ESP32
- [ ] **Check cable:** Verify USB/UART cables are firmly connected
- [ ] **Verify IP:** For WiFi methods, confirm ESP32 IP address
- [ ] **Check permissions:** `sudo usermod -aG dialout $USER` (then restart terminal)
- [ ] **Update drivers:** `sudo apt update && sudo apt upgrade`

---

## Common Error Messages & Solutions

### 1. "Device not found" / "No such file or directory"

**For UART (/dev/ttyUSB0):**
```bash
# Find correct port
ls -la /dev/tty*

# Check which device is your ESP32
dmesg | tail -20  # Look for "USB device" messages

# Try different port numbers
--lora-port /dev/ttyUSB0  # or /dev/ttyUSB1, /dev/ttyUSB2
```

**For USB (/dev/ttyACM0):**
```bash
# Check if USB device exists
ls -la /dev/ttyACM*

# If not found:
# 1. Plug in USB cable
# 2. Wait 2 seconds
# 3. Run: dmesg | grep -i acm

# Verify with:
lsusb | grep -i esp32
```

**For BLE:**
```bash
# Check Bluetooth available
hciconfig

# Scan for device
bluetoothctl
> scan on
> devices
# Look for ESP32-LoRa (or actual device name)
> quit
```

---

### 2. "Permission denied" / "Could not open port"

**Solution:**
```bash
# Add user to dialout group
sudo usermod -aG dialout $USER

# Apply without logging out
newgrp dialout

# Verify it worked
id | grep dialout

# If still fails, check permissions:
ls -la /dev/ttyUSB0
# Should show: crw-rw---- ... dialout

# Fix with:
sudo chmod 666 /dev/ttyUSB0
```

---

### 3. "Connection timeout" / "Failed to connect"

**For UART/USB:**
```bash
# Check if port is readable
cat /dev/ttyUSB0 &
# If no output, device not responding

# Try reset:
# 1. Unplug from power
# 2. Wait 5 seconds
# 3. Plug back in
# 4. Wait 2 seconds
# 5. Try again

# Check baud rate matches
# Default: 115200 bps
# Check in esp32_lora_receiver.ino:
# Serial.begin(115200);
```

**For WiFi:**
```bash
# Test network connectivity
ping 192.168.1.100  # Replace with actual IP

# If no response:
# 1. Check ESP32 WiFi is enabled
# 2. Check SSID/password in firmware
# 3. Verify router gives IP to ESP32
# 4. Check firewall:

sudo ufw allow 8080  # Allow WebSocket port
sudo ufw allow 8080/udp

# From ESP32, test with:
curl -X POST http://192.168.1.100:8080/send?message=TEST
```

**For BLE:**
```bash
# Test Bluetooth works
bluetoothctl
> devices
# If ESP32-LoRa not listed, firmware not running BLE code

# Try pairing first:
> pair ESP32-LoRa
> trust ESP32-LoRa
> quit

# Then try main.py
```

---

### 4. "Module not found" / "ImportError"

**For WiFi modules:**
```bash
# Install websocket client
pip3 install websocket-client

# Install requests
pip3 install requests

# Verify install:
python3 -c "import websocket; print('OK')"
python3 -c "import requests; print('OK')"
```

**For Bluetooth modules:**
```bash
# Install pybluez (for Classic)
pip3 install pybluez

# Install bleak (for BLE) - RECOMMENDED
pip3 install bleak

# Verify:
python3 -c "import bleak; print('OK')"
```

**For core modules:**
```bash
# Install requirements
pip3 install -r requirements.txt

# Or individual packages
pip3 install torch torchvision yolov5 ultralytics opencv-python
```

---

### 5. "No module named 'serial_handler'" or similar

**Solution:**
```bash
# Make sure you're in project directory
cd /home/lora/raspberryLora

# Check file exists
ls -la lora/serial_handler.py

# Check Python path includes project
export PYTHONPATH=$PYTHONPATH:/home/lora/raspberryLora

# Try again:
python3 main.py
```

---

### 6. "Timeout reading from LoRa"

**Meaning:** Device connected but not receiving messages.

**Solutions:**
1. **Check baud rate:**
   ```bash
   # In esp32_lora_receiver.ino, verify:
   Serial.begin(115200);  // or correct rate
   ```

2. **Check LoRa initialization:**
   ```cpp
   // In ESP32 code, should see in logs:
   // "LoRa init ok"
   ```

3. **Test LoRa connectivity:**
   ```bash
   # Send test message
   python3 -c "
   from lora.serial_handler import SerialHandler
   h = SerialHandler('uart', port='/dev/ttyUSB0')
   h.connect()
   h.send_data('TEST')  # Should work
   "
   ```

---

### 7. "WebSocket connection refused"

**Problem:** WiFi WebSocket can't connect to ESP32.

**Solutions:**
```bash
# 1. Check ESP32 IP
ping 192.168.1.100

# 2. Check firewall
sudo ufw status
sudo ufw allow 8080

# 3. Check ESP32 has WebSocket server running
# Look at esp32_firmware_options.ino WiFi WebSocket section
# Verify code has: WebSocketsServer webSocket(8080);

# 4. Test with curl
curl http://192.168.1.100:8080

# Should connect (or at least respond, not timeout)

# 5. Check router isolation
# Some routers isolate WiFi devices from each other
# Try connecting both to same WiFi band (2.4GHz vs 5GHz)

# 6. Restart both devices
```

---

### 8. "Memory usage too high" / "Out of memory"

**Meaning:** System running slow or crashing.

**Solutions:**
```bash
# Monitor memory during run:
watch -n 1 'free -h'

# In another terminal:
python3 main.py --lora-connection uart

# If memory keeps growing:
# 1. Check for memory leaks in detection loop
# 2. Reduce frame size (640x480 → 480x360)
# 3. Use lighter model (YOLOv5n → YOLOv5s)
# 4. Check logs for repeated error messages

# Edit main.py and check:
# self.frame_size = (640, 480)  # Try smaller
# model = "yolov5n"  # Already smallest
```

---

### 9. "Detection latency too high"

**Expected latency:**
- UART/USB: 5-20ms network, 250ms detection = 255-270ms total
- WiFi: 20-200ms network, 250ms detection = 270-450ms total
- BLE: 30-100ms network, 250ms detection = 280-350ms total

**If slower than expected:**

1. **Check frame resolution:**
   ```bash
   # In main.py, check:
   cap = cv2.VideoCapture(0)
   cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)   # Try 480
   cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # Try 360
   ```

2. **Check model:**
   ```bash
   # YOLOv5n is fastest
   # If using larger model, switch to:
   model = "yolov5n"
   ```

3. **Monitor CPU:**
   ```bash
   # In another terminal during test:
   watch -n 1 'ps aux | grep main.py | grep -v grep'
   
   # Should show 40-70% CPU
   # If 95-100%, system overloaded
   ```

4. **Check WiFi latency:**
   ```bash
   # Ping test
   ping -c 10 192.168.1.100
   
   # Look at "min/avg/max/stddev"
   # If avg > 50ms, WiFi issue
   ```

---

### 10. "Connection drops frequently"

**Solutions:**

1. **Check cable/connection stability:**
   ```bash
   # For serial connections, test:
   cat < /dev/ttyUSB0 &
   # Should get continuous data flow with no errors
   ```

2. **Check WiFi signal:**
   ```bash
   # From Raspberry Pi
   iwconfig
   # Look for Signal level (should be > -80 dBm)
   ```

3. **Add reconnection logic:**
   ```python
   # In main.py, wrap connection in retry:
   max_retries = 5
   handler.connect(max_retries=max_retries)
   ```

4. **Monitor connection health:**
   ```bash
   # Check logs
   tail -f logs/errors.log
   
   # Should not show repeated "Connection lost" messages
   ```

---

## Connection-Specific Troubleshooting

### UART Serial Issues

| Problem | Solution |
|---------|----------|
| "Bad file descriptor" | Check port exists: `ls /dev/ttyUSB*` |
| Garbled data | Check baud rate: should be 115200 |
| No data received | Check GPIO pins (TX/RX) connected properly |
| Very slow | Baud rate 115200 is maximum for RPi serial |

### USB CDC-ACM Issues

| Problem | Solution |
|---------|----------|
| Not recognized | Install USB drivers or restart system |
| Port keeps changing | Use by-id: `/dev/serial/by-id/...` |
| "ttyACM0 not found" | Check `lsusb`, may be ttyACM1 |
| Speed same as UART | Correct, RPi serial hardware limited |

### WiFi Issues

| Problem | Solution |
|---------|----------|
| Slow connection | Check router signal, try moving closer |
| Frequent drops | Check WiFi channel interference (iwconfig) |
| Can't find server | Wrong IP, use `arp -a` to find ESP32 |
| Timeout errors | Check firewall: `sudo ufw allow 8080` |
| High latency (>100ms) | Normal for WiFi, consider using WebSocket |

### BLE Issues

| Problem | Solution |
|---------|----------|
| "Device not found" | Run: `bluetoothctl scan on` |
| "Connection refused" | ESP32 BLE not started, check firmware |
| "Timeout" | BLE range ~100m, try moving closer |
| Slow data rate | BLE limited to 1 Mbps, use WiFi for speed |
| Async errors | BLE requires async refactor, see docs |

### Bluetooth Classic Issues

| Problem | Solution |
|---------|----------|
| Legacy, use BLE instead | Better performance and lower power |
| "Device not paired" | Run: `bluetoothctl pair <device>` |
| Very slow | Classic is 2Mbps max, consider alternatives |

---

## Advanced Debugging

### Enable verbose logging

```python
# In main.py, add:
import logging
logging.basicConfig(level=logging.DEBUG)

# Or use:
python3 -u main.py 2>&1 | tee debug.log
```

### Check all open ports

```bash
# See what ports/devices are being used
netstat -tuln | grep LISTEN

# Check serial ports
dmesg | tail -50 | grep -i serial
```

### Test each component separately

```bash
# Test camera
python3 -c "import cv2; print('Camera:', 'OK' if cv2.VideoCapture(0).isOpened() else 'FAIL')"

# Test model
python3 -c "from detector.model_loader import YOLOModelLoader; m = YOLOModelLoader(); print('Model:', 'OK')"

# Test connection
python3 -c "from lora.serial_handler import SerialHandler; print('Handler:', 'OK')"
```

### Check system resources

```bash
# Memory
free -h
ps aux --sort=-%mem | head

# CPU
top -n 1
htop

# Disk
df -h

# Processes
ps aux | grep python
```

---

## Getting Help

If you still have issues:

1. **Check logs:**
   ```bash
   tail -100 logs/errors.log
   tail -100 logs/detections.log
   ```

2. **Collect debug info:**
   ```bash
   # Create debug package
   echo "=== System ===" > debug.txt
   uname -a >> debug.txt
   echo "=== Python ===" >> debug.txt
   python3 --version >> debug.txt
   echo "=== Ports ===" >> debug.txt
   ls /dev/tty* >> debug.txt
   echo "=== Packages ===" >> debug.txt
   pip3 list >> debug.txt
   echo "=== Recent errors ===" >> debug.txt
   tail -50 logs/errors.log >> debug.txt
   ```

3. **Include in bug report:**
   - Output of `debug.txt`
   - Command you ran
   - Expected behavior
   - Actual behavior
   - Full error message/log

---

## Performance Tuning

### For Slow Detection

```python
# Reduce resolution
cv2.CAP_PROP_FRAME_WIDTH = 480
cv2.CAP_PROP_FRAME_HEIGHT = 360

# Skip frames
if frame_count % 2 == 0:  # Process every 2nd frame
    # Run detection
```

### For High Memory Usage

```python
# Reduce model size
model_name = "yolov5n"  # Already smallest

# Limit detections
conf = 0.5  # Raise confidence threshold
```

### For Dropped Connections

```python
# Add retry logic
handler = SerialHandler(...)
max_retries = 3
handler.connect(max_retries=max_retries)

# Add heartbeat
if time.time() - last_heartbeat > 5:
    handler.send_data("PING")
    last_heartbeat = time.time()
```

---

## Quick Command Reference

```bash
# System checks
uname -a              # OS info
python3 --version    # Python version
pip3 list            # Installed packages

# Serial/USB
ls /dev/tty*         # List ports
dmesg | tail -20     # Recent device messages
lsusb                # List USB devices

# WiFi
ping 192.168.1.100   # Test connectivity
iwconfig             # WiFi signal strength
arp -a              # Find device IP

# Bluetooth
hciconfig           # Bluetooth status
bluetoothctl        # Bluetooth control
scan on             # Scan for devices

# Process monitoring
ps aux | grep main.py
top -p $(pgrep -f main.py)
watch -n 1 'free -h'

# Logs
tail -f logs/detections.log
tail -f logs/errors.log
grep -i error logs/errors.log
```

---

**Last Updated:** June 5, 2026  
**Version:** 2.0  
**Difficulty:** Advanced

