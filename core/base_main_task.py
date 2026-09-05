import time
import abc
import multiprocessing as mp
from config import MainTaskConfig
from core.ipc import IPCChannel, DataPacket
from core.logger import setup_logger


class BaseMainTask(abc.ABC):
    """Abstract Base Class for Main Application Logic running in a dedicated process."""

    def __init__(self, config: MainTaskConfig):
        self.config = config
        self.logger = setup_logger("Main-Task", getattr(config, "log_level", "INFO"))
        self.packets_received = 0
        self._last_log_time = time.time()

    @abc.abstractmethod
    def setup(self) -> None:
        """Initialize main task state, external connectors, DB, UI, or robotics.
        Must be implemented by child classes.
        """
        pass

    @abc.abstractmethod
    def handle_packet(self, packet: DataPacket) -> None:
        """Process incoming data packet sent from the CV pipeline.

        Args:
            packet: DataPacket containing detections, frames, or metadata.
        """
        pass

    @abc.abstractmethod
    def teardown(self) -> None:
        """Cleanup main task resources, save stats, close database/network sockets.
        Must be implemented by child classes.
        """
        pass

    def run(self, stop_event: mp.Event, ipc_channel: IPCChannel) -> None:
        """Main execution loop listening for incoming CV packets.

        Args:
            stop_event: Event trigger used to signal shutdown.
            ipc_channel: IPC queue channel to receive DataPackets from CV Pipeline.
        """
        # Re-initialize logger within the spawned process context
        self.logger = setup_logger("Main-Task", getattr(self.config, "log_level", "INFO"), force_reinit=True)
        self.logger.info("Initializing Main Task process...")
        try:
            self.setup()
            self.logger.info("Main Task setup complete. Listening for incoming CV packets.")
        except Exception as e:
            self.logger.error(f"Failed during Main Task setup: {e}", exc_info=True)
            return

        task_interval = 1.0 / self.config.target_hz if self.config.target_hz > 0 else 0

        while not stop_event.is_set():
            start_time = time.time()
            packet = ipc_channel.receive(block=True, timeout=self.config.poll_timeout)

            if packet is not None:
                if packet.is_sentinel:
                    self.logger.info("Sentinel packet received. Stopping Main Task loop.")
                    break

                self.packets_received += 1
                try:
                    self.handle_packet(packet)
                except Exception as e:
                    self.logger.error(f"Error handling packet #{packet.frame_id}: {e}", exc_info=True)

            # Target HZ rate-limiting sleep if configured
            if task_interval > 0:
                elapsed = time.time() - start_time
                sleep_time = task_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Periodic stats logging
            now = time.time()
            if now - self._last_log_time >= self.config.log_interval:
                dropped = ipc_channel.dropped_count
                qsize = ipc_channel.qsize()
                self.logger.info(
                    f"Stats: Processed {self.packets_received} packets | Queue depth: {qsize} | Total dropped: {dropped}"
                )
                self._last_log_time = now

        self.logger.info("Termination signal received. Running Main Task teardown...")
        try:
            self.teardown()
            self.logger.info("Main Task teardown complete.")
        except Exception as e:
            self.logger.error(f"Error during Main Task teardown: {e}", exc_info=True)
