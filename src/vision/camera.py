import time
import math
import numpy as np
import cv2
from typing import Tuple, Union, Optional
from src.common.logger import setup_logger

logger = setup_logger("CameraDevice")


class CameraDevice:
    """
    Modular Camera capture abstraction.
    Supports physical hardware devices (OpenCV capture index), video files,
    or synthetic mock frames for hardware-independent development.
    """

    def __init__(self, source: Union[int, str] = "mock", width: int = 640, height: int = 480, target_fps: int = 30):
        self.source = source
        self.width = width
        self.height = height
        self.target_fps = target_fps
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_mock = str(source).lower() == "mock"
        self.start_time = time.time()
        self.frame_counter = 0

    def open(self) -> bool:
        """Opens camera capture or initializes synthetic frame generator."""
        if self.is_mock:
            logger.info(f"Initialized Synthetic Mock Camera ({self.width}x{self.height} @ {self.target_fps} FPS)")
            return True

        # Open real OpenCV video source
        try:
            src_index = int(self.source) if str(self.source).isdigit() else self.source
            self.cap = cv2.VideoCapture(src_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            if not self.cap.isOpened():
                logger.error(f"Failed to open OpenCV camera source: {self.source}")
                return False

            logger.info(f"Opened physical OpenCV camera source: {self.source}")
            return True
        except Exception as e:
            logger.error(f"Error opening camera source {self.source}: {e}")
            return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Captures next frame. Returns (success_flag, numpy_frame_bgr)."""
        self.frame_counter += 1

        if self.is_mock:
            # Generate synthetic test frame with a moving target object
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            # Render background grid lines
            for x in range(0, self.width, 40):
                cv2.line(frame, (x, 0), (x, self.height), (40, 40, 40), 1)
            for y in range(0, self.height, 40):
                cv2.line(frame, (0, y), (self.width, y), (40, 40, 40), 1)

            # Draw smooth Lissajous trajectory for simulated target
            t = time.time() - self.start_time
            cx = int((self.width / 2) + (self.width / 3) * math.sin(t * 1.5))
            cy = int((self.height / 2) + (self.height / 3) * math.cos(t * 2.1))
            radius = 25

            # Draw green synthetic target circle
            cv2.circle(frame, (cx, cy), radius, (0, 255, 0), -1)
            cv2.putText(
                frame,
                f"MOCK CAM | Frame #{self.frame_counter}",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
            )

            # Throttle mock loop to match target FPS
            time.sleep(1.0 / self.target_fps)
            return True, frame

        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("Camera read returned empty frame")
                return False, None
            return True, frame

        return False, None

    def release(self):
        """Releases camera resources."""
        if self.cap is not None:
            self.cap.release()
            logger.info("Released OpenCV camera device")
