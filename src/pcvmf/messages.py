"""Versioned, validated JSON messages. Codecs never acquire process resources."""

import json
from dataclasses import asdict
from typing import Any

from .api import (
    ConfigurationError,
    Message,
    MessageCodec,
    TargetDetection,
    VisionStatus,
    VisionTelemetry,
)
from .plugins import load_class
from .validation import keys, mapping, number, string


def required(data: dict, fields: set[str], path: str):
    mapping(data, path)
    keys(data, fields, path)
    missing = fields - set(data)
    if missing:
        raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")


def detection(data: dict) -> TargetDetection:
    required(
        data,
        {"label", "confidence", "bbox", "centroid", "extra_attributes"},
        "detection",
    )
    string(data["label"], "label")
    if number(data["confidence"], "confidence", inclusive=True) > 1:
        raise ValueError("confidence must be between 0 and 1")
    for key, length in (("bbox", 4), ("centroid", 2)):
        values = data[key]
        if not isinstance(values, list) or len(values) != length or any(type(v) is not int for v in values):
            raise ValueError(f"{key}: expected {length} integers")
    if data["bbox"][2] < 0 or data["bbox"][3] < 0:
        raise ValueError("bbox dimensions cannot be negative")
    mapping(data["extra_attributes"], "extra_attributes")
    return TargetDetection(**data)


class VisionTelemetryCodec(MessageCodec):
    message_type = "vision.telemetry"
    payload_type = VisionTelemetry

    def encode(self, payload):
        data = asdict(payload)
        self.decode(data)
        return data

    def decode(self, payload):
        required(
            payload,
            {
                "captured_at",
                "width",
                "height",
                "frame_id",
                "capture_time_ms",
                "processing_time_ms",
                "detections",
                "status",
            },
            "vision.telemetry",
        )
        for key in ("width", "height"):
            number(payload[key], key, integer=True)
        number(payload["frame_id"], "frame_id", integer=True, inclusive=True)
        for key in ("captured_at", "capture_time_ms", "processing_time_ms"):
            number(payload[key], key, inclusive=True)
        string(payload["status"], "status")
        if not isinstance(payload["detections"], list):
            raise ValueError("detections: expected a list")
        return VisionTelemetry(**{**payload, "detections": [detection(d) for d in payload["detections"]]})


class VisionStatusCodec(MessageCodec):
    message_type = "vision.status"
    payload_type = VisionStatus

    def encode(self, payload):
        data = asdict(payload)
        self.decode(data)
        return data

    def decode(self, payload):
        required(payload, {"status", "message"}, "vision.status")
        string(payload["status"], "status")
        string(payload["message"], "message")
        return VisionStatus(**payload)


class CodecRegistry:
    def __init__(self, custom_paths=()):
        self.by_wire = {}
        self.by_type = {}
        codecs = [VisionTelemetryCodec(), VisionStatusCodec()]
        for path in custom_paths:
            try:
                codecs.append(load_class(path, MessageCodec)())
            except Exception as exc:
                raise ConfigurationError(f"codecs.{path}: {exc}") from exc
        for codec in codecs:
            try:
                string(codec.message_type, "codec.message_type")
                number(codec.schema_version, "codec.schema_version", integer=True)
                if not isinstance(codec.payload_type, type):
                    raise ValueError("payload_type must be a type")
                key = (codec.message_type, codec.schema_version)
                if key in self.by_wire or codec.payload_type in self.by_type:
                    raise ValueError("duplicate message type/version or payload type")
                self.by_wire[key] = codec
                self.by_type[codec.payload_type] = codec
            except (AttributeError, ValueError) as exc:
                raise ConfigurationError(f"invalid codec {type(codec).__name__}: {exc}") from exc

    def encode(self, source: str, sequence: int, timestamp: float, payload: Any) -> bytes:
        codec = self.by_type.get(type(payload))
        if codec is None:
            raise ValueError(f"no codec for {type(payload).__name__}")
        data = {
            "message_type": codec.message_type,
            "schema_version": codec.schema_version,
            "source": source,
            "sequence": sequence,
            "timestamp": timestamp,
            "payload": codec.encode(payload),
        }
        return json.dumps(data, allow_nan=False, separators=(",", ":")).encode()

    def decode(self, topic: str, wire: bytes) -> Message:
        data = json.loads(
            wire,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {value}")),
        )
        required(
            data,
            {
                "message_type",
                "schema_version",
                "source",
                "sequence",
                "timestamp",
                "payload",
            },
            "envelope",
        )
        string(data["message_type"], "message_type")
        string(data["source"], "source")
        number(data["schema_version"], "schema_version", integer=True)
        number(data["sequence"], "sequence", integer=True, inclusive=True)
        number(data["timestamp"], "timestamp", inclusive=True)
        mapping(data["payload"], "payload")
        key = (data["message_type"], data["schema_version"])
        if key not in self.by_wire:
            raise ValueError(f"unsupported message type/version: {key}")
        payload = self.by_wire[key].decode(data["payload"])
        return Message(topic=topic, **{**data, "payload": payload})
