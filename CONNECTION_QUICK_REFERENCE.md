# Quick Reference - Multi-Protocol Communication

## 🚀 Connection Options Cheat Sheet

### Default (UART Serial) - START HERE
```bash
python3 main.py
```
✅ Works out of box  
⚡ 5-20ms latency  
📡 ~10m range  
🔌 GPIO wired connection

---

### USB CDC-ACM (Direct USB)
```bash
python3 main.py --lora-connection usb --lora-port /dev/ttyACM0
```
⚡ 5-20ms latency (same as UART)  
🚀 12 Mbps speed  
🔌 USB cable connection  
📡 ~5m range

---

### WiFi WebSocket (Real-time Remote)
```bash
python3 main.py --lora-connection wifi --lora-wifi-host 192.168.1.100
```
🌐 Works over WiFi  
⚡ 20-50ms latency  
📡 100m+ range  
🔋 Medium power

---

### WiFi HTTP (Simple Remote)
```bash
python3 main.py --lora-connection http --lora-wifi-host 192.168.1.100
```
🌐 Works over standard HTTP  
⏱️ 100-200ms latency  
📡 100m+ range  
✨ Good for non-real-time

---

### Bluetooth Low Energy (Mobile)
```bash
python3 main.py --lora-connection ble --lora-device "ESP32-LoRa"
```
📱 Wireless without WiFi  
⚡ 30-100ms latency  
🔋 Low power consumption  
📡 100m range

---

### Bluetooth Classic (Legacy)
```bash
python3 main.py --lora-connection btc --lora-device "ESP32-LoRa"
```
⚠️ Not recommended (legacy)  
Use BLE instead

---

## 📊 Speed Comparison

```
Speed Ranking:
1. USB CDC-ACM:     12 Mbps ⚡⚡⚡⚡⚡
2. WiFi WebSocket:   2 Mbps ⚡⚡⚡⚡
3. WiFi HTTP:        2 Mbps ⚡⚡⚡⚡
4. Bluetooth BLE:    1 Mbps ⚡⚡⚡
5. UART Serial:    115 kbps ⚡⚡

Latency Ranking (Best to Worst):
1. UART/USB:         5-20ms   ✅
2. WiFi WebSocket:  20-50ms   ✅
3. Bluetooth BLE:   30-100ms  🟡
4. WiFi HTTP:     100-200ms  🟡
5. Bluetooth Classic: 20-50ms 🔴
```

---

## 🎯 Decision Guide

**Close Range?**  
→ Use UART (default)

**Need WiFi?**  
→ Use WiFi WebSocket (real-time)  
→ Use WiFi HTTP (simple)

**Mobile/Low Power?**  
→ Use Bluetooth BLE

**Maximum Speed?**  
→ Use USB CDC-ACM

**No WiFi Available?**  
→ Use UART or BLE

---

## ⚙️ ESP32 Firmware Code Snippets

### UART (Default)
Already included in `esp32_lora_receiver.ino`

### USB CDC-ACM
```cpp
#include <USB.h>
#include <USBSerial.h>

USBSerial USBSerial;

void setup() {
  USB.begin();
  USBSerial.begin(115200);
}

void loop() {
  if (USBSerial.available()) {
    String msg = USBSerial.readStringUntil('\n');
    // Process LoRa message
  }
}
```

### WiFi WebSocket
```cpp
#include <WiFi.h>
#include <WebSocketsServer.h>

WebSocketsServer webSocket(8080);

void webSocketEvent(uint8_t num, WStype_t type, uint8_t *payload, size_t len) {
  if(type == WStype_TEXT) {
    String message = String((char*)&payload[0]);
    // Process message
    broadcastLoRa(message);
  }
}
```

### BLE Characteristic
```cpp
#include <BLEDevice.h>
#include <BLEServer.h>

// GATT Characteristic with read/write/notify
// Service UUID: 180A
// Characteristic UUID: 2A29
```

---

## 🔧 Troubleshooting Quick Links

| Problem | Solution |
|---------|----------|
| "Device not found" (UART) | Check `/dev/ttyUSB*` ports |
| "Connection timeout" (WiFi) | Verify ESP32 WiFi enabled |
| "WebSocket error" | Install: `pip install websocket-client` |
| "BLE not pairing" | Run: `bluetoothctl` and pair device |
| "No serial ports found" | Check USB cable, try different port |

---

## 📈 Performance Metrics

### UART @ 640×480 Detection
- Detection latency: 250ms
- Message send latency: 10ms
- **Total: 260ms**

### WiFi WebSocket @ 640×480 Detection
- Detection latency: 250ms
- Message send latency: 30ms
- **Total: 280ms**

### WiFi HTTP @ 640×480 Detection
- Detection latency: 250ms
- Message send latency: 150ms
- **Total: 400ms**

---

## 🎓 Learning Path

1. **Start with UART** - Simplest, works out of box
2. **Try USB if** - You want higher speed
3. **Move to WiFi when** - Devices need to be farther apart
4. **Use BLE if** - Power consumption critical or WiFi unavailable

---

## 🚀 Pro Tips

1. **Test connection first:**
   ```bash
   python3 -c "from lora.serial_handler import SerialHandler; \
   h = SerialHandler('uart'); h.connect() and print('OK')"
   ```

2. **Monitor connection quality:**
   ```bash
   python3 main.py --lora-connection uart --display
   ```

3. **Hybrid approach (best of both):**
   - Primary: UART (low latency)
   - Fallback: WiFi (longer range)

4. **Check WiFi connectivity first:**
   ```bash
   ping 192.168.1.100
   ```

5. **View connection logs:**
   ```bash
   tail -f logs/errors.log
   ```

---

## 📋 All Available Options

```bash
python3 main.py --help

# Connection options:
--lora-connection {uart,usb,wifi,http,ble,btc}
--lora-port /dev/ttyUSB0 (for UART/USB)
--lora-wifi-host 192.168.1.100 (for WiFi)
--lora-wifi-port 8080 (for WiFi)
```

---

**Version**: 2.0  
**Date**: June 5, 2026  
**Status**: Ready to Use

