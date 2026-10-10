from __future__ import annotations


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError("value must be >= 1")
    return parsed
