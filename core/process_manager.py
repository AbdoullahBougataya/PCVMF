import time
import signal
import sys
import multiprocessing as mp
from typing import Optional
from config import AppConfig
from core.ipc import IPCChannel
from core.base_pipeline import BaseVisionPipeline
from core.base_main_task import BaseMainTask
from core.logger import setup_logger


class ProcessManager:
    """Orchestrates creation, execution, signal handling, and shutdown of framework processes."""

    def __init__(self, config: AppConfig, cv_pipeline: BaseVisionPipeline, main_task: BaseMainTask):
        self.config = config
        self.cv_pipeline = cv_pipeline
        self.main_task = main_task
        self.logger = setup_logger("Manager", config.log_level)

        self.stop_event = mp.Event()
        self.ipc_channel = IPCChannel(
            maxsize=config.ipc_config.max_queue_size,
            drop_when_full=config.ipc_config.drop_when_full
        )

        self.cv_process: Optional[mp.Process] = None
        self.main_process: Optional[mp.Process] = None

    def _setup_signal_handlers(self):
        """Register SIGINT and SIGTERM handlers for graceful exit."""
        def handler(signum, frame):
            sig_name = signal.Signals(signum).name
            self.logger.warning(f"Received signal {sig_name}. Requesting graceful shutdown...")
            self.stop_event.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def start(self):
        """Spins up the CV pipeline and Main task multiprocessing processes."""
        self.logger.info(f"Starting application '{self.config.app_name}'...")
        self._setup_signal_handlers()

        # Spawn CV Pipeline Process
        self.cv_process = mp.Process(
            name="CVPipelineProcess",
            target=self.cv_pipeline.run,
            args=(self.stop_event, self.ipc_channel)
        )

        # Spawn Main Task Process
        self.main_process = mp.Process(
            name="MainTaskProcess",
            target=self.main_task.run,
            args=(self.stop_event, self.ipc_channel)
        )

        self.cv_process.start()
        self.logger.info(f"CV Pipeline process started (PID: {self.cv_process.pid})")

        self.main_process.start()
        self.logger.info(f"Main Task process started (PID: {self.main_process.pid})")

    def run_until_complete(self, check_interval: float = 0.5):
        """Blocks and monitors running processes until stop signal or process termination."""
        self.start()

        try:
            while not self.stop_event.is_set():
                # Check if any process died unexpectedly
                if self.cv_process and not self.cv_process.is_alive():
                    self.logger.error("CV Pipeline process died unexpectedly.")
                    self.stop_event.set()
                    break

                if self.main_process and not self.main_process.is_alive():
                    self.logger.error("Main Task process died unexpectedly.")
                    self.stop_event.set()
                    break

                time.sleep(check_interval)
        except KeyboardInterrupt:
            self.logger.warning("KeyboardInterrupt detected. Stopping processes...")
            self.stop_event.set()
        finally:
            self.shutdown()

    def shutdown(self, grace_period: float = 5.0):
        """Gracefully shuts down all child processes within grace_period."""
        self.logger.info("Initiating framework shutdown sequence...")
        self.stop_event.set()

        processes = [
            ("CV Pipeline", self.cv_process),
            ("Main Task", self.main_process),
        ]

        # Attempt graceful join
        for name, proc in processes:
            if proc and proc.is_alive():
                self.logger.info(f"Waiting for {name} process (PID {proc.pid}) to exit...")
                proc.join(timeout=grace_period)

        # Force terminate if still alive
        for name, proc in processes:
            if proc and proc.is_alive():
                self.logger.warning(f"{name} process did not terminate within {grace_period}s. Terminating forcibly...")
                proc.terminate()
                proc.join(timeout=1.0)
                if proc.is_alive():
                    self.logger.error(f"Force killing {name} process...")
                    proc.kill()

        self.ipc_channel.close()
        self.logger.info("Framework shutdown complete.")
