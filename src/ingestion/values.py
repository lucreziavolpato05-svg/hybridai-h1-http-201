"""Scalar parsing helpers; dataset semantics remain in explicit adapters."""

import math
import warnings
from hashlib import sha256

from .identity import uic_code


def text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"Expected text/scalar, got {value!r}")
    return " ".join(str(value).split()) or None


def source_uic(value: object) -> str:
    # Several inspected SBB schemas declare UIC as double (8503000.0).
    if type(value) is float and math.isfinite(value) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and value.strip().endswith(".0"):
        value = value.strip()[:-2]
    return uic_code(value, "UIC/BPUIC")


def boolean(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false", "0", "1"}:
        return value.strip().lower() in {"true", "1"}
    raise ValueError(f"Invalid boolean: {value!r}")


def stable_id(prefix: str, *parts: str) -> str:
    import json
    digest = sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]
    return f"{prefix}_{digest}"


def report_skips(dataset: str, errors: list[str]) -> None:
    if errors:
        warnings.warn(f"{dataset}: {len(errors)} malformed rows skipped; examples: {'; '.join(errors[:3])}",
                      stacklevel=2)
