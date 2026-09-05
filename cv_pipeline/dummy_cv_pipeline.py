import time
import math
import numpy as np
import cv2
from typing import Optional
from config import CVPipelineConfig
from core.base_pipeline import BaseVisionPipeline
from core.ipc import DataPacket


class DummyVisionPipeline(BaseVisionPipeline):
    """Example Computer Vision pipeline generating synthetic video frames and object detections."""

    def __init__(self, config: CVPipelineConfig):
        super().__init__(config)
        self.cap: Optional[cv2.VideoCapture] = None
        self.use_synthetic = False

    def setup(self) -> None:
        """Sets up camera video capture or falls back to synthetic frame generator."""
        if isinstance(self.config.source, int) or str(self.config.source).isdigit():
            cam_idx = int(self.config.source)
            self.cap = cv2.VideoCapture(cam_idx)
            if not self.cap.isOpened():
                self.logger.warning(f"Could not open camera {cam_idx}. Falling back to synthetic frame generator.")
                self.use_synthetic = True
        elif isinstance(self.config.source, str) and self.config.source.endswith(('.mp4', '.avi', '.mkv')):
            self.cap = cv2.VideoCapture(self.config.source)
            if not self.cap.isOpened():
                self.logger.warning(f"Could not open video file '{self.config.source}'. Falling back to synthetic generator.")
                self.use_synthetic = True
        else:
            self.use_synthetic = True

        if self.use_synthetic:
            self.logger.info("Running in Synthetic Mode (generating artificial motion frames).")

    def _generate_synthetic_frame(self, frame_id: int) -> tuple[np.ndarray, dict]:
        """Generates an animated frame with a moving circle and metadata."""
        w = self.config.width or 640
        h = self.config.height or 480
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Draw dynamic background grid
        grid_size = 40
        for x in range(0, w, grid_size):
            cv2.line(frame, (x, 0), (x, h), (30, 30, 30), 1)
        for y in range(0, h, grid_size):
            cv2.line(frame, (0, y), (w, y), (30, 30, 30), 1)

        # Calculate moving target trajectory
        t = frame_id * 0.05
        cx = int(w / 2 + math.cos(t) * (w / 3))
        cy = int(h / 2 + math.sin(t * 1.5) * (h / 3))
        radius = 35

        # Draw detected object bounding box and target
        cv2.circle(frame, (cx, cy), radius, (0, 255, 128), -1)
        cv2.rectangle(frame, (cx - radius, cy - radius), (cx + radius, cy + radius), (0, 200, 255), 2)

        # Overlay frame header
        cv2.putText(
            frame,
            f"Frame #{frame_id} | FPS: {self.actual_fps:.1f}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        detections = [
            {
                "label": "moving_target",
                "confidence": 0.96,
                "bbox": [cx - radius, cy - radius, cx + radius, cy + radius],
                "center": (cx, cy)
            }
        ]

        return frame, {"detections": detections, "object_count": len(detections)}

    def process_frame(self, frame_id: int) -> Optional[DataPacket]:
        """Captures frame, runs CV logic, and packages DataPacket."""
        if self.use_synthetic:
            frame, detection_data = self._generate_synthetic_frame(frame_id)
        else:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                # Reset video loop or handle camera drop
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    return None

            if self.config.width and self.config.height:
                frame = cv2.resize(frame, (self.config.width, self.config.height))

            # Simple demo detection (OpenCV motion / color filtering)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (0, 120, 70), (10, 255, 255))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            detections = []
            for c in contours:
                if cv2.contourArea(c) > 500:
                    x, y, w, h = cv2.boundingRect(c)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    detections.append({"label": "object", "bbox": [x, y, x + w, y + h]})

            detection_data = {"detections": detections, "object_count": len(detections)}

        if self.config.show_preview:
            cv2.imshow("CV Pipeline Preview", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.logger.info("'q' pressed in preview window.")

        # Construct data packet to send over IPC
        packet = DataPacket(
            frame_id=frame_id,
            timestamp=time.time(),
            data=detection_data,
            frame=frame if self.config.extra_params.get("send_frame", True) else None,
            metadata={"source": str(self.config.source)}
        )

        return packet

    def teardown(self) -> None:
        """Release camera and windows."""
        if self.cap and self.cap.isOpened():
            self.cap.release()
        if self.config.show_preview:
            cv2.destroyAllWindows()
