import os
from dataclasses import dataclass, field
from typing import Union, Optional, Dict, Any


@dataclass
class CVPipelineConfig:
    """Configuration for the Computer Vision Pipeline process."""
    source: Union[int, str] = 0  # Camera index (0), RTSP URL, or video file path
    target_fps: float = 30.0     # Desired processing FPS limit (0 for uncapped)
    width: Optional[int] = 640   # Desired frame width (None to keep native)
    height: Optional[int] = 480  # Desired frame height (None to keep native)
    show_preview: bool = False   # Whether CV pipeline should render OpenCV imshow preview window
    device: str = "cpu"          # Target device (cpu, cuda, mps)
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MainTaskConfig:
    """Configuration for the Main Task process."""
    poll_timeout: float = 0.1         # Timeout in seconds when reading from IPC queue
    target_hz: float = 0.0            # Execution frequency limit in Hz (0.0 for uncapped/as fast as queue feeds)
    log_interval: float = 5.0         # Frequency in seconds to output performance metrics
    log_every_n_frames: int = 20      # Frame interval for logging individual packet details
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IPCConfig:
    """Configuration for Inter-Process Communication."""
    max_queue_size: int = 100    # Maximum items in IPC queue before drop or block
    drop_when_full: bool = True  # Drop oldest frame when queue is full (prevents latency build-up)


@dataclass
class AppConfig:
    """Global framework configuration."""
    app_name: str = "CV_Framework_App"
    log_level: str = "INFO"
    cv_config: CVPipelineConfig = field(default_factory=CVPipelineConfig)
    main_config: MainTaskConfig = field(default_factory=MainTaskConfig)
    ipc_config: IPCConfig = field(default_factory=IPCConfig)
