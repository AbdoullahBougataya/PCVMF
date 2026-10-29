"""CCSDS space packet encoding shared by the exporter and the XTCE generator.

Layout (big-endian): 6-byte CCSDS primary header, 8-byte generation time in Unix
milliseconds, 4-byte packet sequence number, then each parameter in declaration order.
"""

import math
import struct
from dataclasses import dataclass
from typing import Any

from .mapping import INT_RANGES, PacketSpec, ParameterSpec

HEADER_BYTES = 6
TIME_BYTES = 8
SEQUENCE_BYTES = 4
DATA_OFFSET = HEADER_BYTES + TIME_BYTES + SEQUENCE_BYTES
FORMATS = {"float32": "f", "float64": "d", "int32": "i", "uint32": "I", "bool": "B", "enum": "I"}
SEQUENCE_MASK = 0x3FFF


class ExtractionError(ValueError):
    """A payload does not provide a value for a mapped parameter."""


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    bit_offset: int
    size_bits: int


def layout(packet: PacketSpec) -> tuple[Field, ...]:
    offset = DATA_OFFSET * 8
    fields = []
    for param in packet.parameters:
        size = struct.calcsize(">" + FORMATS[param.type]) * 8
        fields.append(Field(param.name, param.type, offset, size))
        offset += size
    return tuple(fields)


def _walk(payload: Any, path: str) -> Any:
    value = payload
    for part in path.split("."):
        if part.isdigit():
            if not isinstance(value, (list, tuple)):
                raise ExtractionError(f"{path}: {part} indexes a non-sequence")
            index = int(part)
            if index >= len(value):
                raise IndexError(index)
            value = value[index]
        elif isinstance(value, dict):
            if part not in value:
                raise ExtractionError(f"{path}: missing key {part!r}")
            value = value[part]
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            raise ExtractionError(f"{path}: missing attribute {part!r}")
    return value


def _convert(param: ParameterSpec, value: Any) -> int | float:
    if param.type == "enum":
        labels = dict(param.values)
        if value not in labels:
            raise ExtractionError(f"{param.field}: unknown enumeration label {value!r}")
        return labels[value]
    if param.type == "bool":
        if not isinstance(value, bool):
            raise ExtractionError(f"{param.field}: expected a boolean; received {type(value).__name__}")
        return int(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtractionError(f"{param.field}: expected a number; received {type(value).__name__}")
    if param.type in INT_RANGES:
        low, high = INT_RANGES[param.type]
        if not float(value).is_integer() or not low <= value <= high:
            raise ExtractionError(f"{param.field}: {value!r} is not a valid {param.type}")
        return int(value)
    if not math.isfinite(value):
        raise ExtractionError(f"{param.field}: expected a finite number")
    return float(value)


def extract(packet: PacketSpec, payload: Any) -> tuple[int | float, ...]:
    """Read every mapped parameter from a typed payload, applying defaults for missing indexes."""
    values = []
    for param in packet.parameters:
        try:
            value = _walk(payload, param.field)
        except IndexError:
            if param.default is None:
                raise ExtractionError(f"{param.field}: index out of range and no default") from None
            value = param.default
        if param.reduce == "count":
            if not isinstance(value, (list, tuple)):
                raise ExtractionError(f"{param.field}: count requires a sequence")
            value = len(value)
        values.append(_convert(param, value))
    return tuple(values)


def encode(packet: PacketSpec, sequence: int, timestamp: float, values: tuple[int | float, ...]) -> bytes:
    body = struct.pack(">" + "".join(FORMATS[p.type] for p in packet.parameters), *values)
    data_length = TIME_BYTES + SEQUENCE_BYTES + len(body)
    header = struct.pack(
        ">HHH",
        (1 << 11) | packet.apid,  # version 0, telemetry, secondary header present
        (0b11 << 14) | (sequence & SEQUENCE_MASK),  # unsegmented
        data_length - 1,
    )
    return header + struct.pack(">QI", round(timestamp * 1000), sequence & 0xFFFFFFFF) + body
