# System Optimization & Deployment Guide

## 🎯 Performance Targets

### Hardware: Raspberry Pi 4B (4GB RAM)
- **Target FPS**: 5-10 fps at 640x480
- **Target Memory**: <600 MB
- **Target CPU**: <60%
- **Target Latency**: 200-400ms

---

## 🚀 Optimization Strategies

### 1. Resolution Optimization

**Impact**: Frame resolution directly affects CPU load

```bash
# Maximum quality (default)
python3 main.py --width 640 --height 480
# Expected: 5 fps, 600MB RAM, 55% CPU

# Balanced (recommended)
python3 main.py --width 480 --height 360
# Expected: 8 fps, 500MB RAM, 45% CPU

# Minimal resources
python3 main.py --width 320 --height 240
# Expected: 12 fps, 400MB RAM, 35% CPU
```

### 2. Frame Skipping

**Impact**: Process fewer frames per second

```bash
# Default: process every frame
python3 main.py --skip-frames 1
# FPS: 15

# Skip every other frame
python3 main.py --skip-frames 2
# FPS: ~7-8 (process every 2nd frame)

# Skip 2 out of 3
python3 main.py --skip-frames 3
# FPS: ~5 (process every 3rd frame)

# Extreme: skip 4 out of 5
python3 main.py --skip-frames 5
# FPS: ~3 (minimal CPU usage)
```

### 3. Confidence Threshold

**Impact**: Lower threshold = longer inference time

```bash
# More selective (faster)
python3 main.py --confidence 0.6
# Fewer detections, faster inference

# Balanced (default)
python3 main.py --confidence 0.45
# Trade-off: accuracy vs speed

# More sensitive (slower)
python3 main.py --confidence 0.3
# More detections, longer processing
```

### 4. Model Selection

**Impact**: Model size and complexity

```bash
# Lightweight (recommended)
python3 main.py --model yolov5n
# Size: 7.5 MB
# Params: 2M
# Speed: ~200ms/frame

# Slightly larger
python3 main.py --model yolov8n
# Size: 6.3 MB
# Params: 3.2M
# Speed: ~180ms/frame (better accuracy)
```

### 5. Camera Settings

In code: `main.py` line ~230-235

```python
# Current settings
self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
self.camera.set(cv2.CAP_PROP_FPS, 15)  # ← Reduce this
self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# Optimized for extreme performance
self.camera.set(cv2.CAP_PROP_FPS, 10)  # Reduce from 15
self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)  # Reduce
self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)  # Reduce
```

---

## 📊 Performance Benchmarks

### Test Configuration 1: Balanced (Recommended)

```bash
python3 main.py \
    --model yolov5n \
    --width 480 --height 360 \
    --confidence 0.45 \
    --skip-frames 2
```

**Expected Results**:
- FPS: 8-10
- Memory: 480 MB
- CPU: 45%
- Latency: 250ms

### Test Configuration 2: High Performance

```bash
python3 main.py \
    --model yolov5n \
    --width 320 --height 240 \
    --confidence 0.5 \
    --skip-frames 3
```

**Expected Results**:
- FPS: 5-6
- Memory: 380 MB
- CPU: 30%
- Latency: 400ms

### Test Configuration 3: Maximum Quality

```bash
python3 main.py \
    --model yolov8n \
    --width 640 --height 480 \
    --confidence 0.4 \
    --skip-frames 1
```

**Expected Results**:
- FPS: 5 fps
- Memory: 600 MB
- CPU: 60%
- Latency: 300ms

---

## 🔧 System Tuning

### 1. Disable Unnecessary Services

```bash
# Disable desktop environment if running headless
sudo systemctl set-default multi-user.target

# Disable Bluetooth (frees resources)
sudo systemctl disable bluetooth

# Disable WiFi power saving (optional)
sudo iwconfig wlan0 power off

# Check running processes
ps aux | grep -E 'python|java|node' | grep -v grep
```

### 2. Increase Swap (Temporary Solution)

```bash
# Check current swap
free -h

# Edit swap config
sudo nano /etc/dphys-swapfile
# Change: CONF_SWAPSIZE=100 to CONF_SWAPSIZE=512

# Apply changes
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Verify
free -h
```

### 3. Enable GPU (if available)

```bash
# Check if using Bullseye with 64-bit OS
uname -m

# GPU acceleration (limited on RPi 4)
# Not recommended for CPU models, use only if available
```

### 4. Disable GUI/Desktop

```bash
# If running Raspberry Pi OS desktop
sudo apt-get purge xserver-xorg-* raspberrypi-ui-* lightdm -y
sudo apt-get autoremove -y

# Free up ~500 MB RAM
```

### 5. IO Optimization

```bash
# Reduce log verbosity
# In code: change logging.DEBUG to logging.WARNING

# Move logs to RAM disk (faster, temporary)
sudo mount -t tmpfs -o size=100m tmpfs /tmp/logs
# Then: PYTHONUNBUFFERED=1 python3 main.py
```

---

## 📈 Monitoring Tools

### Real-time Monitoring

```bash
# Install monitoring tools
sudo apt-get install htop iotop nethogs

# Monitor CPU/Memory
htop

# Monitor disk I/O
sudo iotop

# Monitor network
sudo nethogs
```

### Custom Python Monitor

```python
#!/usr/bin/env python3
import psutil
import time

def monitor_system():
    """Monitor system resources in real-time."""
    while True:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        print(f"\rCPU: {cpu_percent:5.1f}% | "
              f"RAM: {memory.used/1024**2:6.1f}/{memory.total/1024**2:6.1f} MB | "
              f"Available: {memory.available/1024**2:6.1f} MB", end="")
        
        time.sleep(2)

if __name__ == "__main__":
    monitor_system()
```

---

## 🔍 Profiling & Analysis

### Memory Profiling

```bash
# Install memory profiler
pip install memory-profiler

# Run with profiling
python3 -m memory_profiler main.py --gps-simulation

# Output shows memory usage line-by-line
```

### CPU Profiling

```bash
# Install cProfile
pip install line-profiler

# Run with profiling
python3 -m cProfile -s cumulative main.py --gps-simulation

# Shows time spent in each function
```

### Production Monitoring Script

```python
#!/usr/bin/env python3
"""Monitor detection system performance."""
import psutil
import time
import json
from datetime import datetime

class SystemMonitor:
    def __init__(self, log_file="system_metrics.json"):
        self.log_file = log_file
        self.metrics = []
    
    def capture(self):
        """Capture system metrics."""
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        temp = self.get_cpu_temp()
        
        metric = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": cpu,
            "memory_percent": memory.percent,
            "memory_mb": memory.used / 1024 / 1024,
            "cpu_temp_c": temp,
        }
        
        self.metrics.append(metric)
        
        # Log to file every 60 seconds
        if len(self.metrics) % 120 == 0:  # 120 * 0.5s = 60s
            self.save_metrics()
    
    def get_cpu_temp(self):
        """Read CPU temperature."""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read()) / 1000
        except:
            return 0
    
    def save_metrics(self):
        """Save metrics to file."""
        with open(self.log_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)
    
    def get_summary(self):
        """Get summary statistics."""
        if not self.metrics:
            return {}
        
        cpus = [m['cpu_percent'] for m in self.metrics]
        mems = [m['memory_mb'] for m in self.metrics]
        temps = [m['cpu_temp_c'] for m in self.metrics]
        
        return {
            "avg_cpu": sum(cpus) / len(cpus),
            "max_cpu": max(cpus),
            "avg_memory_mb": sum(mems) / len(mems),
            "max_memory_mb": max(mems),
            "avg_temp_c": sum(temps) / len(temps),
            "max_temp_c": max(temps),
        }
```

---

## 🌡️ Thermal Management

### Monitor Temperature

```bash
# Check CPU temperature
vcgencmd measure_temp

# Continuous monitoring
watch -n 1 'vcgencmd measure_temp'
```

### Temperature Thresholds

| Temp (°C) | Status | Action |
|-----------|--------|--------|
| < 60 | Excellent | No action needed |
| 60-70 | Good | Monitor |
| 70-80 | Warm | Add cooling |
| > 80 | Critical | Reduce load or shutdown |

### Cooling Solutions

1. **Passive Heatsink**
   - Copper heatsinks on CPU/RAM
   - Cost: $5-10
   - Improvement: 5-10°C

2. **Active Cooling (Fan)**
   - USB fan or GPIO-controlled fan
   - Cost: $10-20
   - Improvement: 15-20°C

3. **Case with Airflow**
   - Ventilated case
   - Cost: $15-25
   - Improvement: 8-12°C

4. **Combined Solution**
   - Heatsink + Fan in case
   - Cost: $25-35
   - Improvement: 25-30°C

---

## 📋 Deployment Checklist

### Pre-Deployment Testing

- [ ] Camera tested and working
- [ ] LoRa module tested and communicating
- [ ] GPS (real or simulated) working
- [ ] Detection model downloading correctly
- [ ] All dependencies installed
- [ ] Logs directory created and writable
- [ ] System runs for 1 hour without crashes
- [ ] Memory usage stable (not growing)
- [ ] CPU temperature acceptable
- [ ] LoRa messages received on ESP32

### Deployment Configuration

```bash
# 1. Optimal settings for production
nano config_production.sh
```

```bash
#!/bin/bash
# Production configuration
export CAMERA_ID=0
export MODEL=yolov5n
export WIDTH=480
export HEIGHT=360
export CONFIDENCE=0.45
export SKIP_FRAMES=2
export LORA_COOLDOWN=30
export LOG_LEVEL=INFO
```

```bash
# 2. Create systemd service
sudo nano /etc/systemd/system/detection.service
```

```ini
[Unit]
Description=Real-time Detection System
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=pi
WorkingDirectory=/home/lora/raspberryLora
ExecStart=/usr/bin/python3 /home/lora/raspberryLora/main.py --gps-simulation
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 3. Enable service
sudo systemctl daemon-reload
sudo systemctl enable detection.service
sudo systemctl start detection.service

# 4. Monitor service
sudo systemctl status detection.service
sudo journalctl -u detection.service -f
```

### Post-Deployment

- [ ] Service starts on boot
- [ ] Check logs after 24 hours
- [ ] Verify detections are being recorded
- [ ] Verify LoRa messages are being sent
- [ ] Monitor CPU/Memory/Temperature

---

## 🔄 Update & Maintenance

### Weekly
```bash
# Check log file size
du -sh logs/

# Archive old logs
tar -czf logs/archive_week_$(date +%Y%m%d).tar.gz logs/*.log
rm logs/*.log

# Restart detection service
sudo systemctl restart detection.service
```

### Monthly
```bash
# Update packages
pip list --outdated

# Update if needed
pip install --upgrade torch opencv-python

# Check system health
free -h
df -h
vcgencmd measure_temp
```

### Quarterly
```bash
# Full system update
sudo apt-get update
sudo apt-get upgrade

# Clear package cache
sudo apt-get clean
sudo apt-get autoremove

# Reboot
sudo reboot
```

---

## 🆘 Emergency Recovery

### System Freeze/Crash

```bash
# Remote SSH check if frozen
ssh pi@raspberrypi.local

# Check logs
tail -f /var/log/syslog

# Force restart service
sudo systemctl restart detection.service

# If still stuck, hard reset
# Hold power for 10 seconds
```

### Memory Leak

```bash
# Monitor memory over time
for i in {1..60}; do
  free -h | grep Mem
  sleep 60
done

# If memory grows continuously, restart service
sudo systemctl restart detection.service

# Add to cron for daily restart
0 6 * * * sudo systemctl restart detection.service
```

### High CPU Usage

```bash
# Check what's using CPU
top -b -n 1 | head -20

# Reduce load:
python3 main.py --skip-frames 5 --width 320 --height 240

# Or reduce LoRa cooldown
python3 main.py --lora-cooldown 60
```

---

**Version**: 1.0
**Last Updated**: June 2026
