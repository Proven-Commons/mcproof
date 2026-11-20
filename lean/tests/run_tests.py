#!/usr/bin/env python3
"""Differential test runner comparing mcproof_lean against independent Python exact arithmetic."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261119


def find_binary() -> Path:
    exe = ROOT / ".lake" / "build" / "bin" / "mcproof_lean"
    if exe.is_file():
        return exe
    lake = Path.home() / ".elan" / "bin" / "lake"
    cmd = [str(lake) if lake.is_file() else "lake", "build", "mcproof_lean"]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if res.returncode != 0 or not exe.is_file():
        raise RuntimeError(f"failed to build mcproof_lean: {res.stderr.strip()}")
    return exe


def call_cli(exe: Path, *args: str) -> str:
    res = subprocess.run([str(exe), *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"mcproof_lean {args!r} exited {res.returncode}: {res.stderr.strip()}")
    return res.stdout.strip()


def py_clamp(lo: int, hi: int, x: int) -> int:
    if x < lo:
        return lo
    if hi < x:
        return hi
    return x


def py_bezout(a: int, b: int, x: int, y: int, g: int) -> bool:
    return a * x + b * y == g


def py_rat_le(n1: int, d1: int, n2: int, d2: int) -> bool:
    if d1 <= 0 or d2 <= 0:
        return False
    return Fraction(n1, d1) <= Fraction(n2, d2)


def py_clean_segments(segs: list[str]) -> str:
    if not segs:
        return "REJECT"
    for seg in segs:
        if seg in ("", ".", "..") or "/" in seg or "\x00" in seg:
            return "REJECT"
    return "OK:" + "/".join(segs)


def main() -> int:
    exe = find_binary()
    rng = random.Random(SEED)
    total_inputs = 0
    failures = 0

    for _ in range(60):
        lo = rng.randint(0, 500)
        hi = rng.randint(0, 500)
        x = rng.randint(0, 600)
        got = int(call_cli(exe, "clamp", str(lo), str(hi), str(x)))
        exp = py_clamp(lo, hi, x)
        total_inputs += 1
        if got != exp:
            failures += 1

    for _ in range(60):
        a = rng.randint(-200, 200)
        b = rng.randint(-200, 200)
        x = rng.randint(-50, 50)
        y = rng.randint(-50, 50)
        valid = rng.choice([True, False])
        delta = 0 if valid else rng.choice([-3, -1, 1, 2, 7])
        g = a * x + b * y + delta
        got = call_cli(exe, "bezout", str(a), str(b), str(x), str(y), str(g)) == "true"
        exp = py_bezout(a, b, x, y, g)
        total_inputs += 1
        if got != exp:
            failures += 1

    for _ in range(60):
        n1 = rng.randint(-300, 300)
        d1 = rng.randint(-5, 40)
        n2 = rng.randint(-300, 300)
        d2 = rng.randint(-5, 40)
        got = call_cli(exe, "ratle", str(n1), str(d1), str(n2), str(d2)) == "true"
        exp = py_rat_le(n1, d1, n2, d2)
        total_inputs += 1
        if got != exp:
            failures += 1

    segment_cases = [
        ["alpha", "beta", "file.lean"],
        ["single"],
        [],
        [".."],
        ["."],
        ["safe", "../escape"],
        ["nested/slash"],
        ["valid", ""],
        ["report_01", "receipt.json"],
        ["a", "b", "..", "c"],
    ]
    for segs in segment_cases:
        got = call_cli(exe, "segments", *segs)
        exp = py_clean_segments(segs)
        total_inputs += 1
        if got != exp:
            failures += 1

    results_md = (
        "# Differential Test Record\n\n"
        f"- Oracle: Python {sys.version_info.major}.{sys.version_info.minor} int and fractions.Fraction\n"
        f"- Seed: {SEED}\n"
        f"- Inputs: {total_inputs}\n"
        f"- Failures: {failures}\n"
    )
    (ROOT / "tests" / "TEST-RESULTS.md").write_text(results_md, encoding="utf-8")
    if failures != 0:
        raise RuntimeError(f"{failures} differential test failure(s) across {total_inputs} inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
