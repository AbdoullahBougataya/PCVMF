import cv2
import numpy as np

from pcvmf.api import PipelineResult, TargetDetection, VisionPipeline
from pcvmf.validation import keys, number


class ColorTracker(VisionPipeline):
    @classmethod
    def validate_options(cls, options):
        keys(options, {"min_area", "lower_hsv", "upper_hsv"}, "pipeline.options")
        number(options.get("min_area", 300), "min_area", inclusive=True)
        for key, default in (
            ("lower_hsv", [35, 100, 100]),
            ("upper_hsv", [85, 255, 255]),
        ):
            values = options.get(key, default)
            if not isinstance(values, list) or len(values) != 3:
                raise ValueError(f"{key}: expected three integers")
            for i, value in enumerate(values):
                number(value, key, integer=True, inclusive=True)
                if value > (179 if i == 0 else 255):
                    raise ValueError(f"{key}: HSV value out of range")
        if any(
            a > b
            for a, b in zip(
                options.get("lower_hsv", [35, 100, 100]),
                options.get("upper_hsv", [85, 255, 255]),
            )
        ):
            raise ValueError("lower_hsv must not exceed upper_hsv")

    def initialize(self):
        self.lower = np.array(self.options.get("lower_hsv", [35, 100, 100]), dtype=np.uint8)
        self.upper = np.array(self.options.get("upper_hsv", [85, 255, 255]), dtype=np.uint8)
        self.kernel = np.ones((5, 5), dtype=np.uint8)

    def process(self, frame):
        hsv = cv2.cvtColor(frame.image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower, self.upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.options.get("min_area", 300):
                x, y, w, h = cv2.boundingRect(contour)
                detections.append(
                    TargetDetection(
                        "color_target",
                        1.0,
                        [x, y, w, h],
                        [x + w // 2, y + h // 2],
                        {"area": area},
                    )
                )
        return PipelineResult(detections, "OK" if detections else "NO_TARGETS")

    def cleanup(self):
        pass
