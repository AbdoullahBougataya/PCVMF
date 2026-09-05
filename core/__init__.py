"""Core components for the Computer Vision Multiprocessing Framework."""

from core.ipc import DataPacket, IPCChannel
from core.base_pipeline import BaseVisionPipeline
from core.base_main_task import BaseMainTask
from core.process_manager import ProcessManager
from core.logger import setup_logger

__all__ = [
    "DataPacket",
    "IPCChannel",
    "BaseVisionPipeline",
    "BaseMainTask",
    "ProcessManager",
    "setup_logger",
]
