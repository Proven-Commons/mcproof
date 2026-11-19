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
    """Resolve `lean`, `lake`, or `leanchecker` binary path across POSIX and Windows."""
    try:
        bdir = elan_bin_dir()
        found_in_elan = shutil.which(name, path=str(bdir))
        if found_in_elan:
            return str(Path(found_in_elan).resolve())
        for cand in (bdir / name, bdir / f"{name}.exe"):
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
        deps_dir() / "mde",
    ]
    for cand in candidates:
        if (cand / "Cargo.toml").is_file():
            return cand.resolve()
    raise FileNotFoundError("siliconcordat/mde checkout not found; set MCPROOF_MDE_ROOT or run ./bin/bootstrap-deps --with-siliconcordat")


def check_prose_script(override: str | Path | None = None) -> Path:
    """Locate the vendored `mcproof.prose_gate` script or an explicit override (`--prose-script` / `MCPROOF_CHECK_PROSE`)."""
    if override is not None:
        cand = Path(override).expanduser().resolve()
        if not cand.is_file():
            raise FileNotFoundError(f"prose gate override script not found: {cand}")
        return cand
    env_override = os.environ.get("MCPROOF_CHECK_PROSE")
    if env_override:
        cand = Path(env_override).expanduser().resolve()
        if not cand.is_file():
            raise FileNotFoundError(f"MCPROOF_CHECK_PROSE script not found: {cand}")
        return cand
    vendored = (Path(__file__).resolve().parent / "prose_gate.py").resolve()
    if vendored.is_file():
        return vendored
    raise FileNotFoundError("vendored prose_gate.py not found in src/mcproof/")
