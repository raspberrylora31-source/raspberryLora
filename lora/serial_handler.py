"""
Communication Handler - Multi-protocol support for LILYGO LoRa32
Supports: UART Serial, USB CDC-ACM, WiFi, Bluetooth
"""

import serial
import logging
import time
import socket
from pathlib import Path
from typing import Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """Supported connection types."""
    UART_SERIAL = "uart"      # UART serial connection (default)
    USB_CDC = "usb"           # USB CDC-ACM connection
    WIFI_WEBSOCKET = "wifi"   # WiFi WebSocket connection
    WIFI_HTTP = "http"        # WiFi HTTP connection
    BLUETOOTH_BLE = "ble"     # Bluetooth Low Energy
    BLUETOOTH_CLASSIC = "btc" # Bluetooth Classic


class SerialHandler:
    """
    Manages communication with ESP32 LoRa module.
    Supports multiple connection types: UART, USB, WiFi, Bluetooth.
    Optimized for lightweight communication on Raspberry Pi.
    """

    # Default serial settings for ESP32
    DEFAULT_BAUDRATE = 115200
    DEFAULT_TIMEOUT = 2.0
    DEFAULT_PORT = "/dev/ttyUSB0"  # Common for USB serial on RPi
    DEFAULT_CONNECTION = ConnectionType.UART_SERIAL

    def __init__(
        self,
        connection_type: str = "uart",
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        wifi_host: str = "192.168.1.100",
        wifi_port: int = 8080,
        ble_device: str = None,
    ):
        """
        Initialize communication handler.

        Args:
            connection_type: "uart", "usb", "wifi", "http", "ble", "btc"
            port: Serial port for UART/USB (e.g., /dev/ttyUSB0, /dev/ttyAMA0)
            baudrate: Baud rate (default 115200 for ESP32)
            timeout: Read timeout in seconds
            wifi_host: IP address for WiFi connection
            wifi_port: Port for WiFi connection (8080 for WebSocket)
            ble_device: Bluetooth device MAC address or name
        """
        self.connection_type = ConnectionType(connection_type)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.wifi_host = wifi_host
        self.wifi_port = wifi_port
        self.ble_device = ble_device

        # Connection objects
        self.serial_conn = None
        self.socket_conn = None
        self.is_connected = False

        logger.info(
            f"Communication handler initialized for {self.connection_type.value.upper()}"
        )

    def connect(self, max_retries: int = 3) -> bool:
        """
        Establish connection to ESP32 (routing to appropriate method).

        Args:
            max_retries: Number of connection attempts

        Returns:
            True if successful, False otherwise
        """
        if self.connection_type == ConnectionType.UART_SERIAL:
            return self._connect_uart(max_retries)
        elif self.connection_type == ConnectionType.USB_CDC:
            return self._connect_uart(max_retries)  # USB CDC-ACM uses same serial API
        elif self.connection_type == ConnectionType.WIFI_WEBSOCKET:
            return self._connect_wifi_websocket(max_retries)
        elif self.connection_type == ConnectionType.WIFI_HTTP:
            return self._connect_wifi_http(max_retries)
        elif self.connection_type == ConnectionType.BLUETOOTH_BLE:
            return self._connect_ble(max_retries)
        elif self.connection_type == ConnectionType.BLUETOOTH_CLASSIC:
            return self._connect_bt_classic(max_retries)
        else:
            logger.error(f"Unknown connection type: {self.connection_type}")
            return False

    def _connect_uart(self, max_retries: int = 3) -> bool:
        """Connect via UART/Serial (including USB CDC-ACM)."""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting UART/USB connection to {self.port} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                self.serial_conn = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    writeTimeout=self.timeout,
                )

                # Give ESP32 time to initialize
                time.sleep(2)

                self.is_connected = True
                logger.info(f"✓ Connected via {self.connection_type.value.upper()}")
                return True

            except serial.SerialException as e:
                logger.warning(f"Connection failed (attempt {attempt + 1}): {e}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error during connection: {e}")
                time.sleep(1)

        logger.error(f"Failed to connect after {max_retries} attempts")
        return False

    def _connect_wifi_websocket(self, max_retries: int = 3) -> bool:
        """Connect via WiFi WebSocket."""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting WiFi WebSocket connection to "
                    f"{self.wifi_host}:{self.wifi_port} (attempt {attempt + 1}/{max_retries})"
                )

                try:
                    import websocket
                except ImportError:
                    logger.error("websocket-client not installed. Install with: pip install websocket-client")
                    return False

                ws = websocket.WebSocketApp(f"ws://{self.wifi_host}:{self.wifi_port}")
                ws.on_open = lambda ws: logger.info("✓ WebSocket connected")

                self.socket_conn = ws
                self.is_connected = True
                logger.info("✓ Connected via WiFi WebSocket")
                return True

            except Exception as e:
                logger.warning(f"WebSocket connection failed: {e}")
                time.sleep(2)

        logger.error(f"Failed to connect via WiFi after {max_retries} attempts")
        return False

    def _connect_wifi_http(self, max_retries: int = 3) -> bool:
        """Connect via WiFi HTTP."""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting WiFi HTTP connection to "
                    f"{self.wifi_host}:{self.wifi_port} (attempt {attempt + 1}/{max_retries})"
                )

                try:
                    import requests
                except ImportError:
                    logger.error("requests not installed. Install with: pip install requests")
                    return False

                # Test connection with GET request
                response = requests.get(
                    f"http://{self.wifi_host}:{self.wifi_port}/ping",
                    timeout=self.timeout
                )
                if response.status_code == 200:
                    self.socket_conn = requests.Session()
                    self.is_connected = True
                    logger.info("✓ Connected via WiFi HTTP")
                    return True

            except Exception as e:
                logger.warning(f"HTTP connection failed: {e}")
                time.sleep(2)

        logger.error(f"Failed to connect via HTTP after {max_retries} attempts")
        return False

    def _connect_ble(self, max_retries: int = 3) -> bool:
        """Connect via Bluetooth Low Energy."""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting BLE connection (attempt {attempt + 1}/{max_retries})"
                )

                try:
                    from bleak import BleakClient
                except ImportError:
                    logger.error("bleak not installed. Install with: pip install bleak")
                    return False

                # This would require async code
                # For now, return placeholder
                logger.warning("BLE support requires async implementation")
                return False

            except Exception as e:
                logger.warning(f"BLE connection failed: {e}")
                time.sleep(2)

        return False

    def _connect_bt_classic(self, max_retries: int = 3) -> bool:
        """Connect via Bluetooth Classic."""
        logger.warning("Bluetooth Classic is legacy. Consider BLE instead.")
        
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting Bluetooth Classic connection (attempt {attempt + 1}/{max_retries})"
                )

                try:
                    import bluetooth
                except ImportError:
                    logger.error("pybluez not installed. Install with: pip install pybluez")
                    return False

                # Scan for ESP32 device
                nearby_devices = bluetooth.discover_devices(lookup_names=True)
                
                esp32_found = False
                for addr, name in nearby_devices:
                    if "lora" in name.lower() or "esp32" in name.lower():
                        logger.info(f"Found ESP32: {name} ({addr})")
                        esp32_found = True
                        break

                if not esp32_found:
                    logger.warning("ESP32 Bluetooth device not found in scan")
                    time.sleep(2)
                    continue

                # Create socket
                sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
                sock.connect((addr, 1))  # Channel 1
                self.socket_conn = sock
                self.is_connected = True
                logger.info("✓ Connected via Bluetooth Classic")
                return True

            except Exception as e:
                logger.warning(f"Bluetooth connection failed: {e}")
                time.sleep(2)

        return False

    def disconnect(self) -> None:
        """Safely disconnect from ESP32."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
                self.is_connected = False
                logger.info(f"Disconnected from {self.port}")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
        elif self.socket_conn:
            try:
                if hasattr(self.socket_conn, 'close'):
                    self.socket_conn.close()
                self.is_connected = False
                logger.info("Disconnected from socket connection")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")

    def send_data(self, data: str, max_retries: int = 2) -> bool:
        """
        Send data to ESP32 via current connection type.

        Args:
            data: String data to send
            max_retries: Number of retry attempts

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            logger.error("Connection not established")
            return False

        # Route to appropriate send method
        if self.connection_type in [ConnectionType.UART_SERIAL, ConnectionType.USB_CDC]:
            return self._send_uart(data, max_retries)
        elif self.connection_type == ConnectionType.WIFI_WEBSOCKET:
            return self._send_websocket(data, max_retries)
        elif self.connection_type == ConnectionType.WIFI_HTTP:
            return self._send_http(data, max_retries)
        elif self.connection_type in [ConnectionType.BLUETOOTH_BLE, ConnectionType.BLUETOOTH_CLASSIC]:
            return self._send_bluetooth(data, max_retries)
        else:
            logger.error(f"Unknown connection type: {self.connection_type}")
            return False

    def _send_uart(self, data: str, max_retries: int = 2) -> bool:
        """Send data via UART/Serial."""
        if not data.endswith("\n"):
            data += "\n"

        for attempt in range(max_retries):
            try:
                self.serial_conn.write(data.encode("utf-8"))
                logger.debug(f"Sent via {self.connection_type.value.upper()}: {data.strip()}")
                return True

            except serial.SerialTimeoutException:
                logger.warning(f"Send timeout (attempt {attempt + 1}/{max_retries})")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Send error: {e}")
                time.sleep(0.5)

        logger.error(f"Failed to send after {max_retries} attempts")
        return False

    def _send_websocket(self, data: str, max_retries: int = 2) -> bool:
        """Send data via WiFi WebSocket."""
        for attempt in range(max_retries):
            try:
                self.socket_conn.send(data)
                logger.debug(f"Sent via WebSocket: {data}")
                return True
            except Exception as e:
                logger.warning(f"WebSocket send failed (attempt {attempt + 1}): {e}")
                time.sleep(0.5)

        return False

    def _send_http(self, data: str, max_retries: int = 2) -> bool:
        """Send data via WiFi HTTP POST."""
        for attempt in range(max_retries):
            try:
                response = self.socket_conn.post(
                    f"http://{self.wifi_host}:{self.wifi_port}/send",
                    data={"message": data},
                    timeout=self.timeout
                )
                if response.status_code == 200:
                    logger.debug(f"Sent via HTTP: {data}")
                    return True
                else:
                    logger.warning(f"HTTP error {response.status_code}")
            except Exception as e:
                logger.warning(f"HTTP send failed (attempt {attempt + 1}): {e}")
                time.sleep(0.5)

        return False

    def _send_bluetooth(self, data: str, max_retries: int = 2) -> bool:
        """Send data via Bluetooth."""
        if not data.endswith("\n"):
            data += "\n"

        for attempt in range(max_retries):
            try:
                self.socket_conn.send(data.encode("utf-8"))
                logger.debug(f"Sent via Bluetooth: {data.strip()}")
                return True
            except Exception as e:
                logger.warning(f"Bluetooth send failed (attempt {attempt + 1}): {e}")
                time.sleep(0.5)

        return False

    def read_data(self, wait_time: float = 0.5) -> Optional[str]:
        """
        Read data from ESP32 via current connection type.

        Args:
            wait_time: Time to wait for data

        Returns:
            Received data as string, or None if nothing received
        """
        if not self.is_connected:
            return None

        try:
            if self.connection_type in [ConnectionType.UART_SERIAL, ConnectionType.USB_CDC]:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.readline().decode("utf-8").strip()
                    logger.debug(f"Received via {self.connection_type.value.upper()}: {data}")
                    return data

            elif self.connection_type == ConnectionType.WIFI_WEBSOCKET:
                # WebSocket receive is async, returns None for simplicity
                logger.debug("WebSocket read not implemented (async required)")
                return None

            elif self.connection_type == ConnectionType.WIFI_HTTP:
                # HTTP polling would be inefficient
                logger.debug("HTTP polling not recommended")
                return None

            elif self.connection_type in [ConnectionType.BLUETOOTH_BLE, ConnectionType.BLUETOOTH_CLASSIC]:
                try:
                    data = self.socket_conn.recv(1024).decode("utf-8").strip()
                    logger.debug(f"Received via Bluetooth: {data}")
                    return data
                except:
                    return None

        except Exception as e:
            logger.error(f"Read error: {e}")

        return None

    def send_lora_message(self, message: str) -> bool:
        """
        Send LoRa message through ESP32.
        Message format: "LORA:<message>"

        Args:
            message: Message content to broadcast

        Returns:
            True if sent successfully
        """
        # Format message for ESP32 LoRa
        formatted_msg = f"LORA:{message}"

        # Ensure message doesn't exceed LoRa payload limit (typically 64-256 bytes)
        if len(formatted_msg) > 240:
            logger.warning(
                f"Message too long ({len(formatted_msg)} bytes), truncating"
            )
            formatted_msg = formatted_msg[:240]

        return self.send_data(formatted_msg)

    @staticmethod
    def find_serial_ports() -> List[str]:
        """
        Find available serial ports on system.

        Returns:
            List of available serial port paths
        """
        import glob

        # Check common Linux serial port patterns
        patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*"]
        ports = []

        for pattern in patterns:
            ports.extend(glob.glob(pattern))

        return sorted(ports)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
