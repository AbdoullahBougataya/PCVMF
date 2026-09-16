import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TargetDetection:
    """Represents a single detected object/target in frame coordinates."""

    label: str
    confidence: float
    bbox: list[int]  # [x, y, width, height]
    centroid: list[int]  # [x, y]
    extra_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class VisionTelemetry:
    """Full telemetry message sent from CV pipeline to Main Application."""

    timestamp: float
    frame_id: int
    fps: float
    processing_time_ms: float
    detections: list[TargetDetection]
    status: str = "OK"

    def to_json(self) -> str:
        """Serializes message object to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> "VisionTelemetry":
        """Deserializes JSON string to VisionTelemetry object."""
        data = json.loads(json_str)
        detections = [TargetDetection(**d) for d in data.get("detections", [])]
        data["detections"] = detections
        return cls(**data)


@dataclass
class VisionStatusMessage:
    """Pipeline state / error status notification message."""

    timestamp: float
    status: str
    message: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> "VisionStatusMessage":
        return cls(**json.loads(json_str))
