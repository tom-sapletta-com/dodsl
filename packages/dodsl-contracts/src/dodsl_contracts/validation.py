from __future__ import annotations

from typing import Any

from .errors import DoDslValidationError


def strict_keys(
    value: dict[str, Any],
    allowed: set[str],
    required: set[str],
    context: str,
) -> None:
    """Reject missing and unknown keys using the stable doDSL error contract."""

    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        raise DoDslValidationError(
            f"{context}_KEYS_INVALID:unknown={sorted(unknown)}:missing={sorted(missing)}"
        )


__all__ = ["strict_keys"]
