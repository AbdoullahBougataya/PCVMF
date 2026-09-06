from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Dict, Any
from src.common.messages import TargetDetection


class BaseVisionPipeline(ABC):
    """
    Abstract Base Class for Computer Vision Pipelines.
    Subclass this class to create custom vision algorithms for robotics tasks.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize models, cascade classifiers, ONNX runtimes, or color thresholds.
        Returns True if initialization succeeded.
        """
        pass

    @abstractmethod
    def process_frame(self, frame: np.ndarray, frame_id: int) -> Tuple[List[TargetDetection], str]:
        """
        Processes a single input BGR image frame.

        Parameters:
            frame (np.ndarray): BGR image frame from camera capture.
            frame_id (int): Monotonically increasing frame number.

        Returns:
            Tuple[List[TargetDetection], str]:
                - List of detected targets/objects in frame coordinates.
                - Status string ("OK", "WARNING", "NO_TARGETS", "ERROR").
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup heavy resources, CUDA allocations, or model sessions."""
        pass
