from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.common.messages import VisionTelemetry, VisionStatusMessage


class BaseMainController(ABC):
    """
    Abstract Base Class for Main Application Logic / Robotics Controllers.
    Subclass this class to implement custom state machines, PID controllers,
    path planners, or robot control loops using vision telemetry.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize robot hardware interfaces, state machine variables, etc."""
        pass

    @abstractmethod
    def on_vision_telemetry(self, telemetry: VisionTelemetry):
        """
        Callback triggered whenever new vision telemetry arrives from ZeroMQ IPC.
        
        Parameters:
            telemetry (VisionTelemetry): Telemetry data containing target detections & FPS.
        """
        pass

    @abstractmethod
    def on_vision_status(self, status_msg: VisionStatusMessage):
        """Callback triggered when CV pipeline status updates occur."""
        pass

    @abstractmethod
    def tick(self, dt: float):
        """
        Periodic control tick loop running at configured loop frequency.
        
        Parameters:
            dt (float): Time delta in seconds since last tick.
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Safely stop motors, park actuators, or release controller resources."""
        pass
