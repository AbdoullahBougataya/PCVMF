import cv2
import numpy as np
from typing import List, Tuple, Dict, Any
from src.vision.base_pipeline import BaseVisionPipeline
from src.common.messages import TargetDetection
from src.common.logger import setup_logger

logger = setup_logger("SamplePipeline")


class SampleColorTrackerPipeline(BaseVisionPipeline):
    """
    Sample CV pipeline that detects green objects/targets in HSV color space.
    Demonstrates contour detection, centroid calculation, and TargetDetection output.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.min_area = config.get("min_area", 300)
        # Default HSV bounds for green target detection
        self.lower_green = np.array([35, 100, 100])
        self.upper_green = np.array([85, 255, 255])

    def initialize(self) -> bool:
        logger.info(f"Initialized SampleColorTrackerPipeline (min_area={self.min_area})")
        return True

    def process_frame(self, frame: np.ndarray, frame_id: int) -> Tuple[List[TargetDetection], str]:
        if frame is None or frame.size == 0:
            return [], "EMPTY_FRAME"

        # Convert frame from BGR to HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower_green, self.upper_green)

        # Morphological noise removal
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: List[TargetDetection] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= self.min_area:
                x, y, w, h = cv2.boundingRect(cnt)
                cx = x + w // 2
                cy = y + h // 2

                detection = TargetDetection(
                    label="green_target",
                    confidence=1.0,
                    bbox=[int(x), int(y), int(w), int(h)],
                    centroid=[int(cx), int(cy)],
                    extra_attributes={"area": float(area)},
                )
                detections.append(detection)

        status = "OK" if len(detections) > 0 else "NO_TARGETS"
        return detections, status

    def cleanup(self):
        logger.info("Cleaned up SampleColorTrackerPipeline resources")
