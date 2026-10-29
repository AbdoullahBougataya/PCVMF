"""Resource-free parsing of exporter options into packet and parameter definitions."""

import re
from dataclasses import dataclass
from typing import Any

from ..api import ConfigurationError
from ..validation import keys, mapping, number, string

TYPES = ("float32", "float64", "int32", "uint32", "bool", "enum")
INT_RANGES = {"int32": (-(2**31), 2**31 - 1), "uint32": (0, 2**32 - 1)}
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
FIELD = re.compile(r"[A-Za-z_]\w*(?:\.(?:[A-Za-z_]\w*|\d+))*")
MAX_APID = 2046  # 2047 is reserved for CCSDS idle packets


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    field: str
    type: str
    units: str | None = None
    default: Any = None
    reduce: str | None = None
    values: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class PacketSpec:
    name: str
    apid: int
    source: str
    topic: str
    parameters: tuple[ParameterSpec, ...]


@dataclass(frozen=True)
class ExportSpec:
    space_system: str
    packets: tuple[PacketSpec, ...]

    def route(self, source: str, topic: str) -> PacketSpec | None:
        return next((p for p in self.packets if p.source == source and p.topic == topic), None)


def _name(value: Any, path: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ConfigurationError(f"{path}: expected a name matching {NAME.pattern}")
    return value


def _check_value(value: Any, kind: str, path: str) -> None:
    if kind == "bool":
        if not isinstance(value, bool):
            raise ConfigurationError(f"{path}: expected a boolean")
    elif kind == "enum":
        if not isinstance(value, str):
            raise ConfigurationError(f"{path}: expected an enumeration label")
    elif kind in INT_RANGES:
        low, high = INT_RANGES[kind]
        number(value, path, minimum=low, integer=True, inclusive=True)
        if value > high:
            raise ConfigurationError(f"{path}: exceeds {kind} range")
    else:
        number(value, path, minimum=float("-inf"))


def _parameter(raw: Any, path: str) -> ParameterSpec:
    raw = mapping(raw, path)
    keys(raw, {"name", "field", "type", "units", "default", "reduce", "values"}, path)
    name = _name(raw.get("name"), path + ".name")
    field = raw.get("field", name)
    if not isinstance(field, str) or not FIELD.fullmatch(field):
        raise ConfigurationError(f"{path}.field: expected a dotted attribute/index path; received {field!r}")
    kind = raw.get("type")
    if kind not in TYPES:
        raise ConfigurationError(f"{path}.type: expected one of {', '.join(TYPES)}")
    units = string(raw["units"], path + ".units") if "units" in raw else None
    reduce = raw.get("reduce")
    if reduce not in (None, "count"):
        raise ConfigurationError(f"{path}.reduce: expected count")
    if reduce == "count" and kind not in INT_RANGES:
        raise ConfigurationError(f"{path}.reduce: count requires an int32 or uint32 type")
    values = ()
    if kind == "enum":
        labels = mapping(raw.get("values"), path + ".values")
        if not labels:
            raise ConfigurationError(f"{path}.values: expected at least one label")
        for label, raw_value in labels.items():
            number(raw_value, f"{path}.values.{label}", integer=True, inclusive=True)
            if raw_value > INT_RANGES["uint32"][1]:
                raise ConfigurationError(f"{path}.values.{label}: exceeds uint32 range")
        if len(set(labels.values())) != len(labels):
            raise ConfigurationError(f"{path}.values: duplicate enumeration values")
        values = tuple(labels.items())
    elif "values" in raw:
        raise ConfigurationError(f"{path}.values: only valid for enum parameters")
    default = raw.get("default")
    if default is not None:
        _check_value(default, kind, path + ".default")
        if kind == "enum" and default not in dict(values):
            raise ConfigurationError(f"{path}.default: unknown enumeration label {default!r}")
    return ParameterSpec(name, field, kind, units, default, reduce, values)


def parse_export_options(options: dict) -> ExportSpec:
    space_system = _name(options.get("space_system", "PCVMF"), "space_system")
    packets_raw = options.get("packets")
    if not isinstance(packets_raw, list) or not packets_raw:
        raise ConfigurationError("packets: expected a nonempty list")
    packets = []
    for i, raw in enumerate(packets_raw):
        path = f"packets[{i}]"
        raw = mapping(raw, path)
        keys(raw, {"name", "apid", "source", "topic", "parameters"}, path)
        name = _name(raw.get("name"), path + ".name")
        apid = number(raw.get("apid"), path + ".apid", integer=True, inclusive=True)
        if apid > MAX_APID:
            raise ConfigurationError(f"{path}.apid: expected at most {MAX_APID}")
        source = string(raw.get("source"), path + ".source")
        topic = string(raw.get("topic"), path + ".topic")
        params_raw = raw.get("parameters")
        if not isinstance(params_raw, list) or not params_raw:
            raise ConfigurationError(f"{path}.parameters: expected a nonempty list")
        params = tuple(_parameter(p, f"{path}.parameters[{j}]") for j, p in enumerate(params_raw))
        if len({p.name for p in params}) != len(params):
            raise ConfigurationError(f"{path}.parameters: duplicate parameter names")
        for other in packets:
            if other.name == name:
                raise ConfigurationError(f"{path}.name: duplicate packet name {name!r}")
            if other.apid == apid:
                raise ConfigurationError(f"{path}.apid: duplicate APID {apid}")
            if (other.source, other.topic) == (source, topic):
                raise ConfigurationError(f"{path}: duplicate route {source}/{topic}")
        packets.append(PacketSpec(name, apid, source, topic, params))
    return ExportSpec(space_system, tuple(packets))


def unsubscribed_routes(spec: ExportSpec, subscriptions) -> list[str]:
    """Return packet routes that the exporter worker does not subscribe to."""
    subscribed = {(s.source, s.topic) for s in subscriptions}
    return [f"{p.source}/{p.topic}" for p in spec.packets if (p.source, p.topic) not in subscribed]
