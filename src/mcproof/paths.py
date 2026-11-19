"""Portable, zero-hardcoded-path workspace and toolchain discovery for mcproof."""

from __future__ import annotations

import os
from pathlib import Path
import shutil


def repo_root() -> Path:
    """Return the root directory of the mcproof repository checkout."""
    override = os.environ.get("MCPROOF_REPO_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]


def deps_dir() -> Path:
    """Return the sibling deps/ directory holding pinned Plane 1 and Tier 2 repos."""
    override = os.environ.get("MCPROOF_DEPS_DIR")
    if override:
        return Path(override).resolve()
    return (repo_root().parent / "deps").resolve()


def dep_repo(name: str) -> Path:
    """Return path to a named repository inside deps/."""
    target = deps_dir() / name
    if not target.is_dir():
        raise FileNotFoundError(f"missing pinned dependency repo '{name}' under {deps_dir()}")
    return target


def elan_bin_dir() -> Path:
    """Locate elan toolchain binaries (~/.elan/bin or ELAN_HOME/bin)."""
    elan_home = os.environ.get("ELAN_HOME")
    if elan_home:
        cand = Path(elan_home) / "bin"
        if cand.is_dir():
            return cand.resolve()
    default_cand = Path.home() / ".elan" / "bin"
    if default_cand.is_dir():
        return default_cand.resolve()
    for tool in ("lake", "lean"):
        found = shutil.which(tool)
        if found:
            return Path(found).resolve().parent
    raise FileNotFoundError("Lean 4 elan bin directory not found (~/.elan/bin or PATH)")


def find_lean_tool(name: str) -> str:
    """Resolve `lean`, `lake`, or `leanchecker` binary path."""
    try:
        cand = elan_bin_dir() / name
        if cand.is_file():
            return str(cand)
    except FileNotFoundError:
        found = shutil.which(name)
        if found:
            return found
        raise
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"Lean tool '{name}' not found in {elan_bin_dir()} or PATH")


def siliconcordat_mde_root() -> Path:
    """Locate the read-only siliconcordat/mde repository checkout."""
    override = os.environ.get("MCPROOF_MDE_ROOT")
    if override:
        return Path(override).resolve()
    # Workspace layout: <work>/mcproof-lab/repo -> <work>/siliconcordat/mde
    r_root = repo_root()
    candidates = [
        r_root.parent.parent / "siliconcordat" / "mde",
        r_root.parent / "mde",
    ]
    for cand in candidates:
        if (cand / "Cargo.toml").is_file():
            return cand.resolve()
    raise FileNotFoundError("siliconcordat/mde checkout not found; set MCPROOF_MDE_ROOT")


def check_prose_script() -> Path:
    """Locate the canonical check-prose.py script (~/.hermes/team-skills/scripts/check-prose.py)."""
    override = os.environ.get("MCPROOF_CHECK_PROSE")
    if override:
        return Path(override).resolve()
    cand = Path.home() / ".hermes" / "team-skills" / "scripts" / "check-prose.py"
    if cand.is_file():
        return cand.resolve()
    raise FileNotFoundError("check-prose.py not found under ~/.hermes/team-skills/scripts/")
