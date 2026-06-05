/*
 * LILYGO LoRa32 (ESP32 + SX1276) - LoRa Receiver/Transmitter
 * Receives detection messages from Raspberry Pi via UART
 * Broadcasts messages via LoRa to neighboring nodes
 * 
 * Board: LILYGO T3 LoRa32 (or equivalent)
 * MCU: ESP32
 * LoRa Module: SX1276
 */

#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include "SPIFFS.h"
#include <HardwareSerial.h>

// LoRa pinout for LILYGO LoRa32
#define SCK 5
#define MISO 19
#define MOSI 27
#define SS 18
#define RST 14
#define DIO0 26

// UART configuration for communication with Raspberry Pi
#define RXD2 16  // RX pin connected to RPi TX
#define TXD2 17  // TX pin connected to RPi RX
HardwareSerial SerialPi(2);

// LoRa configuration
#define BAND 915E6  // LoRa frequency (433E6, 866E6, 915E6, etc.)
#define TX_POWER 20 // TX power in dBm (max 20)
#define SPREADING_FACTOR 12 // SF7-SF12 (higher = longer range, lower speed)
#define BANDWIDTH 125000 // Bandwidth in Hz (125000, 250000, 500000)
#define CODING_RATE 8 // 5-8

// Message handling
#define MAX_MESSAGE_LENGTH 256
char rxBuffer[MAX_MESSAGE_LENGTH];
uint8_t rxIndex = 0;
bool messageReady = false;

// Statistics
uint32_t messagesSent = 0;
uint32_t messagesReceived = 0;
uint32_t lastStatusTime = 0;

void setup() {
  Serial.begin(115200);  // USB serial for debugging
  SerialPi.begin(115200, SERIAL_8N1, RXD2, TXD2);  // UART for RPi communication
  
  delay(1000);
  
  Serial.println("\n\n=== LILYGO LoRa32 - Detection System ===");
  Serial.println("Initializing...");
  
  // Initialize SPIFFS for logging
  if (!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
  }
  
  // Initialize SPI
  SPI.begin(SCK, MISO, MOSI, SS);
  
  // Initialize LoRa
  LoRa.setPins(SS, RST, DIO0);
  if (!LoRa.begin(BAND)) {
    Serial.println("LoRa init failed. Check your connection.");
    while (1);
  }
  
  // LoRa configuration
  LoRa.setSpreadingFactor(SPREADING_FACTOR);
  LoRa.setSignalBandwidth(BANDWIDTH);
  LoRa.setCodingRate4(CODING_RATE);
  LoRa.setTxPower(TX_POWER, PA_OUTPUT_PA_BOOST);
  LoRa.setFrequency(BAND);
  
  // Enable CRC
  LoRa.enableCrc();
  
  Serial.println("✓ LoRa initialized");
  Serial.println("✓ Waiting for messages from Raspberry Pi...");
  Serial.print("\nLoRa Settings:");
  Serial.print("\n  Frequency: "); Serial.print(BAND); Serial.println(" Hz");
  Serial.print("  Spreading Factor: "); Serial.println(SPREADING_FACTOR);
  Serial.print("  Bandwidth: "); Serial.println(BANDWIDTH);
  Serial.print("  TX Power: "); Serial.println(TX_POWER);
  Serial.println();
}

void loop() {
  // Read from Raspberry Pi UART
  readFromRaspberryPi();
  
  // Send message if ready
  if (messageReady) {
    sendLoRaMessage();
    messageReady = false;
    rxIndex = 0;
  }
  
  // Listen for incoming LoRa messages
  receiveLoRaMessage();
  
  // Print status periodically
  printStatus();
  
  delay(100);  // Small delay to prevent CPU overload
}

/**
 * Read UART data from Raspberry Pi
 * Message format: "LORA:<message>"
 */
void readFromRaspberryPi() {
  while (SerialPi.available()) {
    char c = SerialPi.read();
    
    // Handle newline as message terminator
    if (c == '\n' || c == '\r') {
      if (rxIndex > 0) {
        rxBuffer[rxIndex] = '\0';
        messageReady = true;
      }
      rxIndex = 0;
      return;
    }
    
    // Add character to buffer
    if (rxIndex < MAX_MESSAGE_LENGTH - 1) {
      rxBuffer[rxIndex++] = c;
    }
  }
}

/**
 * Send message via LoRa
 */
void sendLoRaMessage() {
  // Parse message
  String message(rxBuffer);
  
  // Extract actual message (remove "LORA:" prefix if present)
  if (message.startsWith("LORA:")) {
    message = message.substring(5);
  }
  
  // Send via LoRa
  LoRa.beginPacket();
  LoRa.print(message);
  LoRa.endPacket();
  
  messagesSent++;
  
  // Log to console
  Serial.print("[LORA TX] ");
  Serial.println(message);
  
  // Log to file
  logMessage("TX", message);
  
  // Send acknowledgment back to RPi
  SerialPi.println("OK:MESSAGE_SENT");
}

/**
 * Receive LoRa messages from other nodes
 */
void receiveLoRaMessage() {
  int packetSize = LoRa.parsePacket();
  
  if (packetSize > 0) {
    String receivedMessage = "";
    
    while (LoRa.available()) {
      receivedMessage += (char)LoRa.read();
    }
    
    messagesReceived++;
    
    // Get signal strength
    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();
    
    // Log to console
    Serial.print("[LORA RX] ");
    Serial.print(receivedMessage);
    Serial.print(" (RSSI: ");
    Serial.print(rssi);
    Serial.print(", SNR: ");
    Serial.print(snr);
    Serial.println(")");
    
    // Relay to RPi for logging
    SerialPi.print("RX:");
    SerialPi.println(receivedMessage);
    
    // Log to file
    logMessage("RX", receivedMessage);
  }
}

/**
 * Print system status periodically
 */
void printStatus() {
  if (millis() - lastStatusTime > 30000) {  // Print every 30 seconds
    lastStatusTime = millis();
    
    Serial.print("\n--- System Status ---");
    Serial.print("\nMessages Sent: ");
    Serial.println(messagesSent);
    Serial.print("Messages Received: ");
    Serial.println(messagesReceived);
    Serial.print("Uptime (ms): ");
    Serial.println(millis());
    Serial.println();
  }
}

/**
 * Log message to SPIFFS
 */
void logMessage(const char* type, String message) {
  // Open log file in append mode
  File file = SPIFFS.open("/lora_log.txt", FILE_APPEND);
  
  if (!file) {
    Serial.println("Failed to open log file");
    return;
  }
  
  // Format: [timestamp] [type] message
  file.print("[");
  file.print(millis() / 1000);  // Simple timestamp in seconds
  file.print("] [");
  file.print(type);
  file.print("] ");
  file.println(message);
  
  file.close();
}

/**
 * Optional: Print log file contents (for debugging)
 */
void printLogFile() {
  File file = SPIFFS.open("/lora_log.txt", FILE_READ);
  
  if (!file) {
    Serial.println("No log file found");
    return;
  }
  
  Serial.println("\n--- LoRa Log File ---");
  while (file.available()) {
    Serial.write(file.read());
  }
  file.close();
  Serial.println("\n---------------------\n");
}
