"""Configuration is validated fully before process creation."""

import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

from .api import ConfigurationError, Worker
from .plugins import plugin_spec
from .validation import keys, mapping, number, string


@dataclass(frozen=True)
class Subscription:
    source: str
    topic: str
    delivery: str = "ordered"


@dataclass(frozen=True)
class WorkerConfig:
    name: str
    plugin: dict
    publications: tuple[str, ...] = ()
    subscriptions: tuple[Subscription, ...] = ()
    endpoint: str | None = None
    rate_hz: float = 30
    startup_timeout: float = 30
    progress_timeout: float = 10
    shutdown_timeout: float = 3


@dataclass(frozen=True)
class AppConfig:
    workers: tuple[WorkerConfig, ...]
    codecs: tuple[str, ...] = ()
    logging: dict = field(default_factory=lambda: {"level": "INFO"})
    hwm: int = 100


def parse_config(raw: dict) -> AppConfig:
    raw = mapping(raw, "config")
    keys(raw, {"workers", "codecs", "logging", "hwm"}, "config")
    entries = raw.get("workers")
    if not isinstance(entries, list) or not entries:
        raise ConfigurationError("workers: expected a nonempty list")
    workers = []
    names = set()
    endpoints = set()
    for i, item in enumerate(entries):
        path = f"workers[{i}]"
        item = mapping(item, path)
        keys(
            item,
            {
                "name",
                "plugin",
                "publications",
                "subscriptions",
                "endpoint",
                "rate_hz",
                "startup_timeout",
                "progress_timeout",
                "shutdown_timeout",
            },
            path,
        )
        name = string(item.get("name"), f"{path}.name")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", name) or name in names:
            raise ConfigurationError(f"{path}.name: invalid or duplicate worker name {name!r}")
        names.add(name)
        plugin_spec(item.get("plugin"), Worker, f"{path}.plugin")
        publications = item.get("publications", [])
        if not isinstance(publications, list):
            raise ConfigurationError(f"{path}.publications: expected a list")
        for topic in publications:
            string(topic, f"{path}.publications")
        if len(set(publications)) != len(publications):
            raise ConfigurationError(f"{path}.publications: duplicate topics")
        endpoint = item.get("endpoint")
        if endpoint is not None:
            string(endpoint, f"{path}.endpoint")
            if not publications:
                raise ConfigurationError(f"{path}.endpoint: requires publications")
            if endpoint.startswith("ipc://"):
                ipc_path = endpoint[6:]
                if not Path(ipc_path).is_absolute() or len(ipc_path.encode()) > 100:
                    raise ConfigurationError(f"{path}.endpoint: IPC path must be absolute and at most 100 bytes")
                endpoint = "ipc://" + str(Path(ipc_path).resolve())
            elif not re.fullmatch(r"tcp://(?:127\.0\.0\.1|localhost):[0-9]+", endpoint):
                raise ConfigurationError(f"{path}.endpoint: use ipc:///absolute/path or tcp://127.0.0.1:PORT")
            else:
                port = int(endpoint.rsplit(":", 1)[1])
                if not 1 <= port <= 65535:
                    raise ConfigurationError(f"{path}.endpoint: invalid port")
                endpoint = f"tcp://127.0.0.1:{port}"
            if endpoint in endpoints:
                raise ConfigurationError(f"{path}.endpoint: duplicate endpoint")
            endpoints.add(endpoint)
        subscriptions = item.get("subscriptions", [])
        if not isinstance(subscriptions, list):
            raise ConfigurationError(f"{path}.subscriptions: expected a list")
        subs = []
        for j, sub in enumerate(subscriptions):
            sp = f"{path}.subscriptions[{j}]"
            sub = mapping(sub, sp)
            keys(sub, {"source", "topic", "delivery"}, sp)
            source = string(sub.get("source"), sp + ".source")
            topic = string(sub.get("topic"), sp + ".topic")
            delivery = sub.get("delivery", "latest" if topic == "vision/telemetry" else "ordered")
            if delivery not in ("latest", "ordered"):
                raise ConfigurationError(f"{sp}.delivery: expected latest or ordered")
            if any(s.source == source and s.topic == topic for s in subs):
                raise ConfigurationError(f"{sp}: duplicate subscription")
            subs.append(Subscription(source, topic, delivery))
        rates = {
            k: number(item.get(k, default), path + "." + k)
            for k, default in (
                ("rate_hz", 30),
                ("startup_timeout", 30),
                ("progress_timeout", 10),
                ("shutdown_timeout", 3),
            )
        }
        if 1 / rates["rate_hz"] >= rates["progress_timeout"]:
            raise ConfigurationError(f"{path}.progress_timeout: must exceed the worker scheduling period")
        workers.append(
            WorkerConfig(
                name,
                item["plugin"],
                tuple(publications),
                tuple(subs),
                endpoint,
                **rates,
            )
        )
    by_name = {w.name: w for w in workers}
    for w in workers:
        for sub in w.subscriptions:
            if sub.source not in by_name or sub.topic not in by_name[sub.source].publications:
                raise ConfigurationError(
                    f"workers.{w.name}.subscriptions: unknown publication {sub.source}/{sub.topic}"
                )
    codecs = raw.get("codecs", [])
    if not isinstance(codecs, list):
        raise ConfigurationError("codecs: expected a list of import paths")
    from .messages import CodecRegistry

    CodecRegistry(codecs)
    logging_cfg = dict(mapping(raw.get("logging", {}), "logging"))
    keys(logging_cfg, {"level", "format", "mcap"}, "logging")
    if logging_cfg.get("level", "INFO") not in (
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ):
        raise ConfigurationError("logging.level: invalid level")
    if "format" in logging_cfg:
        import logging

        try:
            logging.Formatter(string(logging_cfg["format"], "logging.format"))
        except ValueError as exc:
            raise ConfigurationError(f"logging.format: {exc}") from exc
    if "mcap" in logging_cfg:
        mcap_cfg = mapping(logging_cfg["mcap"], "logging.mcap")
        keys(mcap_cfg, {"directory", "compression", "queue_size"}, "logging.mcap")
        directory = string(mcap_cfg.get("directory", "recordings"), "logging.mcap.directory")
        if "\0" in directory:
            raise ConfigurationError("logging.mcap.directory: must not contain NUL characters")
        compression = mcap_cfg.get("compression", "zstd")
        if compression not in ("none", "lz4", "zstd"):
            raise ConfigurationError("logging.mcap.compression: expected none, lz4, or zstd")
        logging_cfg["mcap"] = {
            "directory": directory,
            "compression": compression,
            "queue_size": number(mcap_cfg.get("queue_size", 1000), "logging.mcap.queue_size", integer=True),
        }
    return AppConfig(
        tuple(workers),
        tuple(codecs),
        logging_cfg,
        number(raw.get("hwm", 100), "hwm", integer=True),
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    try:
        text = Path(path).read_text() if path else files("pcvmf.defaults").joinpath("demo.yaml").read_text()
        return parse_config(yaml.safe_load(text))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"{path or 'packaged demo'}: {exc}") from exc
