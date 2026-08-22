import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uart_meshtastic import MeshtasticUART


class _FailingSerial:
    def __init__(self, *args, **kwargs):
        raise OSError("T-Beam disconnected")


class _FakePort:
    def __init__(self, *args, **kwargs):
        self.is_open = True
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def flush(self):
        return None

    def close(self):
        self.is_open = False


class UARTFailureTests(unittest.TestCase):
    def test_connect_failure_does_not_raise(self):
        uart = MeshtasticUART(port="/dev/null", baud=38400, serial_cls=_FailingSerial)
        self.assertFalse(uart.connect())
        self.assertFalse(uart.is_connected())
        uart.disconnect()

    def test_send_queues_when_disconnected(self):
        uart = MeshtasticUART(port="/dev/null", baud=38400, serial_cls=_FailingSerial)
        uart.connect()
        self.assertTrue(uart.send_message("PERSON WPN 2026-08-22 09:16:04"))
        self.assertFalse(uart._queue.empty())
        uart.disconnect()

    def test_empty_message_rejected(self):
        uart = MeshtasticUART(port="/dev/null", baud=38400, serial_cls=_FailingSerial)
        self.assertFalse(uart.send_message("   "))
        self.assertFalse(uart.send_message(None))

    def test_write_success_with_fake_port(self):
        uart = MeshtasticUART(port="/dev/serial0", baud=38400, serial_cls=_FakePort)
        self.assertTrue(uart.connect())
        self.assertTrue(uart.is_connected())
        self.assertTrue(uart.send_message("TEST MESHTASTIC UART"))
        self.assertTrue(uart.flush(timeout=2.0))
        uart.disconnect()
        self.assertFalse(uart.is_connected())


if __name__ == "__main__":
    unittest.main()
