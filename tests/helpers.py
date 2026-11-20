"""Assertion and dependency-skip helpers safe under `python3 -O` and `mde guard --code-audit`."""

from __future__ import annotations

import shutil
from typing import Any
import pytest

from mcproof.paths import deps_dir, find_lean_tool, siliconcordat_mde_root


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


def has_dep(name: str) -> bool:
    return (deps_dir() / name).is_dir()


def has_lean_toolchain() -> bool:
    try:
        find_lean_tool("lean")
        find_lean_tool("lake")
        return True
    except FileNotFoundError:
        return False


def has_mde_binary_or_cargo() -> bool:
    try:
        root = siliconcordat_mde_root()
    except FileNotFoundError:
        return False
    if (root / "target" / "release" / "mde").is_file() or (root / "target" / "debug" / "mde").is_file():
        return True
    return shutil.which("cargo") is not None


def requires_dep(*names: str) -> pytest.MarkDecorator:
    missing = [n for n in names if not has_dep(n)]
    return pytest.mark.skipif(
        bool(missing),
        reason=f"requires pinned deps {missing} (run `./bin/bootstrap-deps`; see README.md)",
    )


def requires_lean() -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not has_lean_toolchain(),
        reason="requires Lean 4.35.0 elan toolchain (`lean` and `lake`; see README.md)",
    )


def requires_mde() -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not has_mde_binary_or_cargo(),
        reason="requires siliconcordat/mde checkout (`./bin/bootstrap-deps --with-siliconcordat` + `cargo build`; see README.md)",
    )
