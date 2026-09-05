import time
from typing import List, Dict, Any
from config import MainTaskConfig
from core.base_main_task import BaseMainTask
from core.ipc import DataPacket


class SampleMainTask(BaseMainTask):
    """Example Main Application Task consuming CV detection packets."""

    def __init__(self, config: MainTaskConfig):
        super().__init__(config)
        self.detection_history: List[Dict[str, Any]] = []
        self.total_objects_detected = 0
        self.latency_sum = 0.0

    def setup(self) -> None:
        """Initialize main application state."""
        self.logger.info("SampleMainTask state initialized.")

    def handle_packet(self, packet: DataPacket) -> None:
        """Processes incoming data packet from CV pipeline."""
        now = time.time()
        latency = (now - packet.timestamp) * 1000  # Latency in ms
        self.latency_sum += latency

        detections = packet.data.get("detections", [])
        object_count = packet.data.get("object_count", 0)
        self.total_objects_detected += object_count

        fps = packet.metadata.get("pipeline_fps", 0.0)

        # Log detailed info at specified frame interval or on object detection
        log_interval_frames = getattr(self.config, "log_every_n_frames", 20)
        if log_interval_frames > 0 and packet.frame_id % log_interval_frames == 0:
            self.logger.info(
                f"[Frame #{packet.frame_id:04d}] Latency: {latency:.2f}ms | "
                f"CV FPS: {fps} | Objects: {object_count}"
            )
            for det in detections:
                self.logger.debug(f"  -> Detected: {det.get('label')} at center {det.get('center')}")

        # Execute business logic rules (e.g., trigger alert, control hardware, send API payload)
        if object_count > 0 and packet.frame_id % 50 == 0:
            self.logger.info(f"⚡ Business Rule Triggered: Detected {object_count} targets at Frame #{packet.frame_id}")

    def teardown(self) -> None:
        """Print summary statistics upon task completion."""
        avg_latency = (self.latency_sum / self.packets_received) if self.packets_received > 0 else 0.0
        self.logger.info("=" * 50)
        self.logger.info("         MAIN TASK EXECUTION SUMMARY          ")
        self.logger.info("=" * 50)
        self.logger.info(f"Total Packets Processed: {self.packets_received}")
        self.logger.info(f"Total Objects Detected:  {self.total_objects_detected}")
        self.logger.info(f"Average IPC Latency:     {avg_latency:.2f} ms")
        self.logger.info("=" * 50)
