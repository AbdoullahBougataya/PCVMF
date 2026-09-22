"""Shared, resource-free plugin validation and loading."""

import importlib
import inspect
import re
from typing import Any

from .api import ConfigurationError, Plugin


def load_class(path: str, expected: type) -> type:
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", path):
        raise ConfigurationError(f"expected module:Class import path; received {path!r}")
    module_name, name = path.split(":")
    try:
        cls = getattr(importlib.import_module(module_name), name)
    except Exception as exc:
        raise ConfigurationError(f"cannot import {path}: {exc}") from exc
    if not isinstance(cls, type) or not issubclass(cls, expected) or inspect.isabstract(cls):
        raise ConfigurationError(f"{path} must be a concrete {expected.__name__} subclass")
    return cls


def plugin_spec(spec: Any, expected: type[Plugin], path: str) -> tuple[type, dict]:
    from .validation import keys, mapping

    spec = mapping(spec, path)
    keys(spec, {"class", "options"}, path)
    try:
        cls = load_class(spec.get("class"), expected)
        options = mapping(spec.get("options", {}), f"{path}.options")
        cls.validate_options(options)
    except Exception as exc:
        raise ConfigurationError(f"{path}: {exc}") from exc
    return cls, options


def instantiate(spec: dict, expected: type[Plugin]) -> Plugin:
    cls, options = plugin_spec(spec, expected, expected.__name__)
    return cls(options)
