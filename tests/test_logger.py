import logging
import tempfile
import unittest

from utils.logger import LocalLogger


class LocalLoggerTests(unittest.TestCase):
    def test_setup_logging_is_idempotent(self):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        root_logger.handlers = []

        try:
            with tempfile.TemporaryDirectory() as log_dir:
                LocalLogger(log_dir=log_dir, enable_file_logging=True)
                LocalLogger(log_dir=log_dir, enable_file_logging=True)

                handler_names = [handler.name for handler in root_logger.handlers]

                self.assertEqual(handler_names.count("raspberry_lora_console"), 1)
                self.assertEqual(
                    len(
                        [
                            name
                            for name in handler_names
                            if name.startswith("raspberry_lora_detection:")
                        ]
                    ),
                    1,
                )
                self.assertEqual(
                    len(
                        [
                            name
                            for name in handler_names
                            if name.startswith("raspberry_lora_error:")
                        ]
                    ),
                    1,
                )
        finally:
            for handler in root_logger.handlers:
                handler.close()
            root_logger.handlers = original_handlers


if __name__ == "__main__":
    unittest.main()
