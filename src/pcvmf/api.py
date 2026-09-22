"""Stable contracts for application plugins. Resource acquisition belongs in initialize/open."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

import numpy as np

T = TypeVar("T")


class ConfigurationError(ValueError):
    """Configuration or plugin options are invalid."""


class Plugin(ABC):
    def __init__(self, options: dict[str, Any]):
        self.options = options

    @classmethod
    @abstractmethod
    def validate_options(cls, options: dict[str, Any]) -> None:
        """Validate without acquiring resources; raise ConfigurationError on failure."""


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    source: str
    sequence: int
    captured_at: float
    width: int
    height: int


class ReadStatus(Enum):
    FRAME = "frame"
    UNAVAILABLE = "unavailable"
    END = "end"


@dataclass(frozen=True)
class FrameRead:
    status: ReadStatus
    frame: Frame | None = None


@dataclass(frozen=True)
class TargetDetection:
    label: str
    confidence: float
    bbox: list[int]
    centroid: list[int]
    extra_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineResult:
    detections: list[TargetDetection]
    status: str = "OK"


@dataclass(frozen=True)
class VisionTelemetry:
    captured_at: float
    width: int
    height: int
    frame_id: int
    capture_time_ms: float
    processing_time_ms: float
    detections: list[TargetDetection]
    status: str = "OK"


@dataclass(frozen=True)
class VisionStatus:
    status: str
    message: str


@dataclass(frozen=True)
class Message(Generic[T]):
    topic: str
    message_type: str
    schema_version: int
    source: str
    sequence: int
    timestamp: float
    payload: T


class MessageCodec(ABC):
    message_type: str
    schema_version: int = 1
    payload_type: type

    @abstractmethod
    def encode(self, payload: Any) -> dict[str, Any]:
        """Validate a typed payload and return a JSON-compatible object."""

    @abstractmethod
    def decode(self, payload: dict[str, Any]) -> Any:
        """Validate an object and return the typed payload, or raise ValueError."""


class Publisher(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: Any) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class Subscriber(ABC):
    @abstractmethod
    def receive(self, timeout_ms: int = 0) -> Message[Any] | None: ...

    @abstractmethod
    def close(self) -> None: ...


@dataclass(frozen=True)
class WorkerContext:
    name: str
    rate_hz: float
    publisher: Publisher | None = None
    subscriber: Subscriber | None = None
    monotonic: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float] = time.time


class Worker(Plugin):
    @abstractmethod
    def initialize(self, context: WorkerContext) -> None: ...

    @abstractmethod
    def step(self) -> bool | None:
        """Perform bounded work. Return False for normal application completion."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources; must be safe after partial initialization."""


class FrameSource(Plugin):
    @abstractmethod
    def open(self, source_id: str, rate_hz: float) -> None: ...

    @abstractmethod
    def read(self) -> FrameRead: ...

    @abstractmethod
    def close(self) -> None: ...


class VisionPipeline(Plugin):
    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def process(self, frame: Frame) -> PipelineResult: ...

    @abstractmethod
    def cleanup(self) -> None: ...


class Controller(Plugin):
    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def on_message(self, message: Message[Any]) -> None: ...

    @abstractmethod
    def tick(self, dt: float) -> bool | None:
        """Return False for normal application completion."""

    @abstractmethod
    def cleanup(self) -> None: ...


class Visualizer(Plugin):
    @abstractmethod
    def render(self, frame: Frame, result: PipelineResult) -> bool:
        """Return False when the user requests normal completion."""

    @abstractmethod
    def close(self) -> None: ...
