/*
 * LILYGO LoRa32 - Multi-Protocol Firmware
 * Supports: UART, USB CDC-ACM, WiFi WebSocket, BLE
 * 
 * This sketch demonstrates how to adapt the ESP32 for different connection types.
 * Start with the original UART version, then upgrade as needed.
 */

// ============================================================================
// METHOD 1: UART SERIAL (DEFAULT - Use This First)
// ============================================================================
// Already included in esp32_lora_receiver.ino
// No changes needed!

// ============================================================================
// METHOD 2: USB CDC-ACM (Direct USB Communication)
// ============================================================================

/*
#include <USB.h>
#include <USBSerial.h>
#include <SPI.h>
#include <LoRa.h>

// LoRa pinout
#define SCK 5
#define MISO 19
#define MOSI 27
#define SS 18
#define RST 14
#define DIO0 26

USBSerial USBSerial;

void setup() {
  // Initialize USB Serial
  USB.begin();
  USBSerial.begin(115200);
  
  Serial.println("USB CDC-ACM initialized");
  
  // Initialize LoRa (same as before)
  SPI.begin(SCK, MISO, MOSI, SS);
  LoRa.setPins(SS, RST, DIO0);
  if (!LoRa.begin(915E6)) {
    USBSerial.println("LoRa init failed");
    while(1);
  }
  USBSerial.println("LoRa ready via USB CDC");
}

void loop() {
  // Read from USB Serial (instead of UART)
  if (USBSerial.available()) {
    String message = USBSerial.readStringUntil('\n');
    
    if (message.startsWith("LORA:")) {
      message = message.substring(5);
      
      // Broadcast via LoRa
      LoRa.beginPacket();
      LoRa.print(message);
      LoRa.endPacket();
      
      USBSerial.println("[LoRa TX] " + message);
    }
  }
  
  // Listen for LoRa
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    USBSerial.println("[LoRa RX] " + received);
  }
}
*/

// ============================================================================
// METHOD 3: WiFi WebSocket (Remote Real-Time Communication)
// ============================================================================

/*
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <SPI.h>
#include <LoRa.h>

// WiFi credentials
const char* ssid = "YourSSID";
const char* password = "YourPassword";

// LoRa config
#define SCK 5
#define MISO 19
#define MOSI 27
#define SS 18
#define RST 14
#define DIO0 26

// WebSocket on port 8080
WebSocketsServer webSocket = WebSocketsServer(8080);

// Callback for WebSocket events
void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  if (type == WStype_TEXT) {
    String message = String((char *)&payload[0]);
    
    if (message.startsWith("LORA:")) {
      message = message.substring(5);
      
      // Broadcast via LoRa
      LoRa.beginPacket();
      LoRa.print(message);
      LoRa.endPacket();
      
      // Acknowledge to client
      String ack = "[LoRa TX] " + message;
      webSocket.broadcastTXT(ack);
      
      Serial.println(ack);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  // Initialize WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nFailed to connect WiFi");
  }
  
  // Initialize WebSocket
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  Serial.println("WebSocket server started on port 8080");
  
  // Initialize LoRa
  SPI.begin(SCK, MISO, MOSI, SS);
  LoRa.setPins(SS, RST, DIO0);
  if (!LoRa.begin(915E6)) {
    Serial.println("LoRa init failed");
    while(1);
  }
  Serial.println("LoRa ready via WiFi WebSocket");
}

void loop() {
  // Handle WebSocket connections
  webSocket.loop();
  
  // Listen for LoRa messages
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    
    String rxMsg = "[LoRa RX] " + received;
    Serial.println(rxMsg);
    
    // Broadcast to all connected WebSocket clients
    webSocket.broadcastTXT(rxMsg);
  }
  
  delay(10);
}
*/

// ============================================================================
// METHOD 4: WiFi HTTP (Simple REST API)
// ============================================================================

/*
#include <WiFi.h>
#include <WebServer.h>
#include <SPI.h>
#include <LoRa.h>

const char* ssid = "YourSSID";
const char* password = "YourPassword";

#define SCK 5
#define MISO 19
#define MOSI 27
#define SS 18
#define RST 14
#define DIO0 26

WebServer server(80);

void handleSend() {
  if (server.hasArg("message")) {
    String message = server.arg("message");
    
    // Broadcast via LoRa
    LoRa.beginPacket();
    LoRa.print(message);
    LoRa.endPacket();
    
    server.send(200, "application/json", 
                "{\"status\":\"ok\",\"sent\":\"" + message + "\"}");
    
    Serial.println("[LoRa TX] " + message);
  } else {
    server.send(400, "application/json", "{\"error\":\"No message\"}");
  }
}

void handlePing() {
  server.send(200, "text/plain", "pong");
}

void setup() {
  Serial.begin(115200);
  
  // WiFi setup
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  
  Serial.println("WiFi connected");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
  
  // HTTP endpoints
  server.on("/send", HTTP_POST, handleSend);
  server.on("/ping", HTTP_GET, handlePing);
  server.begin();
  
  // LoRa setup
  SPI.begin(SCK, MISO, MOSI, SS);
  LoRa.setPins(SS, RST, DIO0);
  LoRa.begin(915E6);
  Serial.println("Ready via HTTP");
}

void loop() {
  server.handleClient();
  
  // Listen for LoRa
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    Serial.println("[LoRa RX] " + received);
  }
}
*/

// ============================================================================
// METHOD 5: Bluetooth Low Energy (BLE)
// ============================================================================

/*
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <SPI.h>
#include <LoRa.h>

#define SERVICE_UUID "180A"
#define CHAR_UUID "2A29"

#define SCK 5
#define MISO 19
#define MOSI 27
#define SS 18
#define RST 14
#define DIO0 26

BLECharacteristic *pCharacteristic;

class CharacteristicCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    std::string value = pCharacteristic->getValue();
    String message = String(value.c_str());
    
    if (message.startsWith("LORA:")) {
      message = message.substring(5);
      
      // Broadcast via LoRa
      LoRa.beginPacket();
      LoRa.print(message);
      LoRa.endPacket();
      
      // Notify BLE clients
      pCharacteristic->setValue("[TX] " + message);
      pCharacteristic->notify();
      
      Serial.println("[LoRa TX] " + message);
    }
  }
};

void setup() {
  Serial.begin(115200);
  
  // BLE setup
  BLEDevice::init("ESP32-LoRa");
  BLEServer *pServer = BLEDevice::createServer();
  
  BLEService *pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    CHAR_UUID,
    BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_WRITE |
    BLECharacteristic::PROPERTY_NOTIFY
  );
  
  pCharacteristic->addDescriptor(new BLE2902());
  pCharacteristic->setCallbacks(new CharacteristicCallbacks());
  
  pService->start();
  pServer->getAdvertising()->start();
  
  Serial.println("BLE started: ESP32-LoRa");
  
  // LoRa setup
  SPI.begin(SCK, MISO, MOSI, SS);
  LoRa.setPins(SS, RST, DIO0);
  LoRa.begin(915E6);
  Serial.println("Ready via BLE");
}

void loop() {
  // Listen for LoRa
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    
    String rxMsg = "[RX] " + received;
    pCharacteristic->setValue(rxMsg);
    pCharacteristic->notify();
    
    Serial.println("[LoRa RX] " + received);
  }
  
  delay(100);
}
*/

// ============================================================================
// INSTALLATION INSTRUCTIONS
// ============================================================================

/*
Method 1: UART Serial (Default)
  - Use original esp32_lora_receiver.ino
  - No changes needed

Method 2: USB CDC-ACM
  - Board: LILYGO T3 LoRa32
  - Install: Arduino > Preferences > Additional Boards URL
  - URL: https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_dev_index.json
  - Board: esp32:esp32:esp32
  - Replace USB code above

Method 3: WiFi WebSocket
  - Install: Arduino Library Manager > WebSocketsServer by Markus Sattler
  - Update WiFi credentials (ssid, password)
  - Upload code above

Method 4: WiFi HTTP
  - No additional libraries needed (WebServer included)
  - Update WiFi credentials
  - Upload code above

Method 5: BLE
  - Built-in to ESP32 Arduino core
  - Upload code above
  - Pair on Raspberry Pi: bluetoothctl

For more info, see: COMMUNICATION_GUIDE.md
*/

void setup() {
  Serial.println("Choose a method above, uncomment it, and upload!");
  Serial.println("See COMMUNICATION_GUIDE.md for full instructions");
}

void loop() {
  delay(1000);
}
