import unittest

try:
    import numpy as np
    import torch

    from detector.detect import ObjectDetector
except ImportError as exc:
    np = None
    torch = None
    ObjectDetector = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class _FakeBoxes:
    def __init__(self, data):
        self.data = data


class _FakeYoloV8Result:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeYoloV8Model:
    def __call__(self, frame):
        return [
            _FakeYoloV8Result(
                _FakeBoxes(
                    torch.tensor(
                        [
                            [10, 20, 30, 40, 0.90, ObjectDetector.PERSON_CLASS],
                            [50, 60, 70, 80, 0.95, 2],
                        ]
                    )
                )
            )
        ]


@unittest.skipIf(ObjectDetector is None, f"runtime dependencies unavailable: {IMPORT_ERROR}")
class DetectorResultTests(unittest.TestCase):
    def test_detect_combined_handles_yolov8_results(self):
        detector = ObjectDetector(
            model=_FakeYoloV8Model(),
            confidence_threshold=0.25,
            skip_frames=1,
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        entity_type, details = detector.detect_combined(frame)

        self.assertEqual(entity_type, "Person without weapon")
        self.assertEqual(len(details["persons"]), 1)
        self.assertAlmostEqual(details["persons"][0]["confidence"], 0.9, places=5)


if __name__ == "__main__":
    unittest.main()
