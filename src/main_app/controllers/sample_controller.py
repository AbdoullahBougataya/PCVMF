from typing import Dict, Any, Optional
from src.main_app.base_controller import BaseMainController
from src.common.messages import VisionTelemetry, VisionStatusMessage
from src.common.logger import setup_logger

logger = setup_logger("SampleController")


class SampleRoboticsController(BaseMainController):
    """
    Sample Robotics Controller demonstrating how main code consumes
    vision telemetry from ZeroMQ IPC to drive robot logic.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.latest_telemetry: Optional[VisionTelemetry] = None
        self.target_lost_counter = 0

    def initialize(self) -> bool:
        logger.info("SampleRoboticsController initialized. Ready to receive CV telemetry.")
        return True

    def on_vision_telemetry(self, telemetry: VisionTelemetry):
        self.latest_telemetry = telemetry
        self.target_lost_counter = 0

    def on_vision_status(self, status_msg: VisionStatusMessage):
        logger.info(f"Vision Status Update: [{status_msg.status}] - {status_msg.message}")

    def tick(self, dt: float):
        """Periodic control loop calculation (e.g. 50Hz control tick)."""
        if self.latest_telemetry is None:
            self.target_lost_counter += 1
            if self.target_lost_counter % 50 == 0:  # Print periodically if waiting for telemetry
                logger.info("Waiting for vision telemetry stream...")
            return

        telemetry = self.latest_telemetry
        detections = telemetry.detections

        if not detections:
            logger.debug("No targets detected by vision pipeline. Hovering / holding position.")
            return

        # Process primary target detection
        primary = detections[0]
        cx, cy = primary.centroid
        
        # Frame center reference (assuming 640x480 frame)
        error_x = cx - 320
        error_y = cy - 240

        logger.info(
            f"CV Telemetry | Frame: #{telemetry.frame_id} | FPS: {telemetry.fps:.1f} | "
            f"Latency: {telemetry.processing_time_ms:.1f}ms | Target: {primary.label} at ({cx}, {cy}) | "
            f"Offset Error: dx={error_x:+d}, dy={error_y:+d}"
        )

    def cleanup(self):
        logger.info("SampleRoboticsController cleaned up.")
