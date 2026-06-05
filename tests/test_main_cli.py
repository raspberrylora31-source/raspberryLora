import unittest

import main


class MainCliTests(unittest.TestCase):
    def test_parser_defaults_do_not_require_runtime_dependencies(self):
        parser = main.build_parser()

        args = parser.parse_args([])

        self.assertEqual(args.model, "yolov5n")
        self.assertEqual(args.camera, 0)
        self.assertEqual(args.lora_connection, "uart")
        self.assertTrue(args.gps_simulation)

    def test_parser_accepts_runtime_options(self):
        parser = main.build_parser()

        args = parser.parse_args(
            [
                "--model",
                "yolov8n",
                "--camera",
                "2",
                "--lora-connection",
                "http",
                "--no-gps-simulation",
            ]
        )

        self.assertEqual(args.model, "yolov8n")
        self.assertEqual(args.camera, 2)
        self.assertEqual(args.lora_connection, "http")
        self.assertFalse(args.gps_simulation)


if __name__ == "__main__":
    unittest.main()
