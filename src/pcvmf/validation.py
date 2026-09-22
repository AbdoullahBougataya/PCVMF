import math
from typing import Any

from .api import ConfigurationError


def mapping(value: Any, path: str) -> dict:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ConfigurationError(f"{path}: expected a mapping with string keys")
    return value


def keys(value: dict, allowed: set[str], path: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConfigurationError(f"{path}: unknown keys: {', '.join(sorted(unknown))}")


def number(
    value: Any,
    path: str,
    minimum: float = 0,
    integer: bool = False,
    inclusive: bool = False,
):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigurationError(f"{path}: expected a finite number")
    if integer and not isinstance(value, int):
        raise ConfigurationError(f"{path}: expected an integer")
    if value < minimum or (not inclusive and value == minimum):
        raise ConfigurationError(
            f"{path}: expected {'at least' if inclusive else 'greater than'} {minimum}; received {value}"
        )
    return value


def string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{path}: expected a nonempty string")
    return value
