# Message and codec reference

[Documentation home](../README.md) · [Reference](README.md)

Implementations: [message contracts](../../src/pcvmf/api.py), [codec registry](../../src/pcvmf/messages.py), and [transport](../../src/pcvmf/transport.py).

## Received Message

`Message[T]` is a frozen dataclass with `topic`, `message_type`, `schema_version`, `source`, `sequence`, `timestamp`, and typed `payload: T`.

The `topic` is a routing label such as `vision/telemetry`. `message_type` is the codec identifier such as `vision.telemetry`; these are distinct concepts. Renaming a topic does not change the payload codec.

## Wire representation

ZeroMQ sends two multipart frames: a UTF-8 topic and a UTF-8 JSON envelope. Example envelope:

```json
{
  "message_type": "sensor.temperature",
  "schema_version": 1,
  "source": "temperature",
  "sequence": 42,
  "timestamp": 1700000000.0,
  "payload": {"celsius": 21.5}
}
```

| Envelope field | Validation |
|---|---|
| `message_type` | Nonempty string; registered together with its version |
| `schema_version` | Positive integer |
| `source` | Nonempty string; matched with the topic against configured routes |
| `sequence` | Nonnegative integer; assigned per publisher across topics |
| `timestamp` | Finite nonnegative number; publication wall-clock seconds |
| `payload` | String-keyed JSON object; interpreted by the selected codec |

All six fields are required; extra envelope fields are rejected. JSON NaN and infinity are rejected. Sequences start at zero for each new publisher process. They are metadata, not acknowledgements, deduplication, or replay support.

The subscriber checks exact `(source, topic)` routes after receipt, despite ZeroMQ's prefix subscription mechanism. Malformed envelopes, unsupported types/versions, and payload decoder exceptions increment `decode_errors`, log a warning, and return no application message. A nonmatching route is filtered out. Controller callback errors occur later and fail the worker.

## Built-in payloads

### TargetDetection

| Field | Python type | Validation in the built-in telemetry codec |
|---|---|---|
| `label` | `str` | Nonempty |
| `confidence` | `float` annotation | Finite number from 0 to 1; integer values also pass validation |
| `bbox` | `list[int]` | Exactly `[x, y, width, height]`; width/height nonnegative |
| `centroid` | `list[int]` | Exactly `[x, y]` |
| `extra_attributes` | `dict[str, Any]` | Mapping; defaults to `{}` in Python |

Coordinates are image pixels. The codec does not enforce that coordinates lie inside image bounds. Extras must be serializable to JSON when publishing. The wire representation requires all fields, including `extra_attributes`.

### VisionTelemetry

Message type `vision.telemetry`, schema version `1`.

| Field | Python type | Meaning and constraint |
|---|---|---|
| `captured_at` | `float` | Finite nonnegative capture wall-clock seconds |
| `width`, `height` | `int` | Positive actual image dimensions |
| `frame_id` | `int` | Nonnegative frame sequence |
| `capture_time_ms` | `float` | Finite nonnegative duration of source read |
| `processing_time_ms` | `float` | Finite nonnegative duration of pipeline processing |
| `detections` | `list[TargetDetection]` | May be empty |
| `status` | `str` | Nonempty; Python default `OK` |

Every field is required on the wire. Timings exclude serialization, transport, visualization, and queue residence. `frame_id` comes from the source; envelope `sequence` comes from the publisher. They can differ if the worker publishes other topics.

### VisionStatus

Message type `vision.status`, schema version `1`. Contains required nonempty strings `status` and `message`.

Status payloads are available to application plugins. The runtime does not automatically publish lifecycle events as `VisionStatus`; lifecycle reporting uses the separate control channel.

## Custom MessageCodec contract

Subclass `pcvmf.api.MessageCodec` and provide:

| Member | Requirement |
|---|---|
| `message_type` | Nonempty string |
| `schema_version` | Positive integer; inherited default `1` |
| `payload_type` | Python type identifying the payload |
| `encode(payload)` | Validate and return a JSON-compatible dictionary |
| `decode(payload_dict)` | Validate and return the typed payload; raise on invalid data |

Codec construction takes no arguments and must be resource-free. Register the import path in top-level `codecs`. Every worker builds the same registry; built-in codecs are always present.

The registry rejects duplicate `(message_type, schema_version)` pairs and duplicate `payload_type` registrations. Publishing selects a codec by the payload's **exact Python type**, not subclass matching. Use separate payload classes if supporting multiple versions at once. There is no automatic schema migration.

An encoding failure propagates into the publishing worker and causes application failure. A decoding failure discards the incoming message and is logged. This asymmetry keeps invalid locally produced data visible while preventing one malformed incoming message from directly terminating a consumer.

See [add a sensor and message type](../how-to/add-sensor.md) for a complete existing implementation to adapt.
