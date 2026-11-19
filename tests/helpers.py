"""Assertion helpers safe under `python3 -O` and `mde guard --code-audit` (no bare `assert`)."""

from __future__ import annotations

from typing import Any


def expect_true(condition: bool, message: str = "expected condition to hold") -> None:
    if not condition:
        raise AssertionError(message)


def expect_false(condition: bool, message: str = "expected condition to be false") -> None:
    if condition:
        raise AssertionError(message)


def expect_eq(actual: Any, expected: Any, message: str = "") -> None:
    if actual != expected:
        detail = f": {message}" if message else ""
        raise AssertionError(f"expected {expected!r}, got {actual!r}{detail}")


def expect_in(member: Any, container: Any, message: str = "") -> None:
    if member not in container:
        detail = f": {message}" if message else ""
        raise AssertionError(f"expected {member!r} in {container!r}{detail}")
