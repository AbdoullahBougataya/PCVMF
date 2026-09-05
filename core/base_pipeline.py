import time
import abc
import multiprocessing as mp
from typing import Optional
from config import CVPipelineConfig
from core.ipc import IPCChannel, DataPacket
from core.logger import setup_logger


class BaseVisionPipeline(abc.ABC):
    """Abstract Base Class for Computer Vision Pipelines running in a dedicated process."""

    def __init__(self, config: CVPipelineConfig):
        self.config = config
        self.logger = setup_logger("CV-Pipeline", getattr(config, "log_level", "INFO"))
        self.frame_counter = 0
        self._fps_time = time.time()
        self._fps_counter = 0
        self.actual_fps = 0.0

    @abc.abstractmethod
    def setup(self) -> None:
        """Initialize models, camera stream, hardware, or video assets.
        Must be implemented by child classes.
        """
        pass

    @abc.abstractmethod
    def process_frame(self, frame_id: int) -> Optional[DataPacket]:
        """Capture and process a single frame.

        Args:
            frame_id: Monotonically increasing frame index.

        Returns:
            DataPacket containing processed results/frames to queue, or None if skipped/failed.
        """
        pass

    @abc.abstractmethod
    def teardown(self) -> None:
        """Cleanup resources, release capture hardware, and close windows.
        Must be implemented by child classes.
        """
        pass

    def run(self, stop_event: mp.Event, ipc_channel: IPCChannel) -> None:
        """Main execution loop for the CV process.

        Args:
            stop_event: Event trigger used to signal shutdown.
            ipc_channel: IPC queue channel to send DataPackets to Main Task.
        """
        # Re-initialize logger within the spawned process context
        self.logger = setup_logger("CV-Pipeline", getattr(self.config, "log_level", "INFO"), force_reinit=True)
        self.logger.info("Initializing CV Pipeline process...")
        try:
            self.setup()
            self.logger.info("CV Pipeline setup complete. Entering processing loop.")
        except Exception as e:
            self.logger.error(f"Failed during CV Pipeline setup: {e}", exc_info=True)
            return

        frame_interval = 1.0 / self.config.target_fps if self.config.target_fps > 0 else 0

        while not stop_event.is_set():
            start_time = time.time()
            self.frame_counter += 1

            try:
                packet = self.process_frame(self.frame_counter)
                if packet is not None:
                    # Inject pipeline performance metrics into metadata
                    packet.metadata["pipeline_fps"] = round(self.actual_fps, 1)
                    packet.metadata["pipeline_frame_count"] = self.frame_counter

                    sent = ipc_channel.send(packet)
                    if not sent:
                        self.logger.warning(f"Frame #{self.frame_counter} dropped due to queue backpressure.")
            except Exception as e:
                self.logger.error(f"Error processing frame #{self.frame_counter}: {e}", exc_info=True)

            # Update FPS tracking
            self._fps_counter += 1
            elapsed_fps = time.time() - self._fps_time
            if elapsed_fps >= 1.0:
                self.actual_fps = self._fps_counter / elapsed_fps
                self._fps_counter = 0
                self._fps_time = time.time()

            # Target FPS rate-limiting sleep
            if frame_interval > 0:
                processing_time = time.time() - start_time
                sleep_time = frame_interval - processing_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

        self.logger.info("Termination signal received. Running CV Pipeline teardown...")
        try:
            # Send sentinel packet to signal main task to finish up
            ipc_channel.send(DataPacket(frame_id=-1, is_sentinel=True))
            self.teardown()
            self.logger.info("CV Pipeline teardown complete.")
        except Exception as e:
            self.logger.error(f"Error during CV Pipeline teardown: {e}", exc_info=True)
