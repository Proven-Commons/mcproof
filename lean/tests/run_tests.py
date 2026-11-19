#!/usr/bin/env python3
"""Differential test runner comparing mcproof_lean against independent Python exact arithmetic."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import random
import subprocess

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


def py_prefund(h_val: int, c_val: int, r_val: int) -> int:
    return max(0, h_val - c_val * r_val)


def py_dual_floor(scale: int, pairs: list[tuple[int, int]]) -> int:
    if scale == 0:
        return 0
    num = sum(w * d for w, d in pairs)
    return int(Fraction(num, scale) // 1)


def py_cyclic_dist(k: int, a: int, b: int) -> int:
    if k == 0:
        return 0
    return ((b % k) + k - (a % k)) % k


def py_ceil_div(num: int, scale: int) -> int:
    if scale == 0:
        return 0
    return -(-num // scale)


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

    # Pre-funded monotone potential differential checks (including zero clamping boundary)
    prefund_cases = [(12, 1, 1), (10, 1, 0), (5, 2, 4), (0, 3, 2)] + [
        (rng.randint(0, 120), rng.randint(0, 6), rng.randint(0, 25)) for _ in range(36)
    ]
    for h_val, c_val, r_val in prefund_cases:
        got = int(call_cli(exe, "prefund", str(h_val), str(c_val), str(r_val)))
        exp = py_prefund(h_val, c_val, r_val)
        total_inputs += 1
        if got != exp:
            failures += 1

    # Operator-counting / Farkas dual floor differential checks
    for idx in range(30):
        scale = 0 if idx == 0 else rng.randint(1, 12)
        k_len = rng.randint(0, 6)
        pairs = [(rng.randint(0, 15), rng.randint(0, 30)) for _ in range(k_len)]
        flat_args = [x for w, d in pairs for x in (str(w), str(d))]
        got = int(call_cli(exe, "dualfloor", str(scale), *flat_args))
        exp = py_dual_floor(scale, pairs)
        total_inputs += 1
        if got != exp:
            failures += 1

    # Cyclic mode-switch metric differential & triangle checks
    for idx in range(40):
        k_val = 0 if idx == 0 else rng.randint(1, 16)
        a_val = rng.randint(0, 50)
        b_val = rng.randint(0, 50)
        got = int(call_cli(exe, "cyclicdist", str(k_val), str(a_val), str(b_val)))
        exp = py_cyclic_dist(k_val, a_val, b_val)
        total_inputs += 1
        if got != exp:
            failures += 1

    # Rational ceiling differential checks
    for idx in range(30):
        scale_c = 0 if idx == 0 else rng.randint(1, 20)
        num_c = 0 if idx == 1 else rng.randint(0, 250)
        got = int(call_cli(exe, "ceildiv", str(num_c), str(scale_c)))
        exp = py_ceil_div(num_c, scale_c)
        total_inputs += 1
        if got != exp:
            failures += 1

    # RMSNorm tangent projection differential & orthogonality checks
    for _ in range(25):
        h1, h2 = rng.randint(-30, 30), rng.randint(-30, 30)
        d1, d2 = rng.randint(-30, 30), rng.randint(-30, 30)
        got_parts = [int(x) for x in call_cli(exe, "tangentproj", str(h1), str(h2), str(d1), str(d2)).split(",")]
        nh = h1 * h1 + h2 * h2
        hd = h1 * d1 + h2 * d2
        exp_parts = [nh * d1 - hd * h1, nh * d2 - hd * h2]
        total_inputs += 1
        if got_parts != exp_parts or (h1 * got_parts[0] + h2 * got_parts[1]) != 0:
            failures += 1

    # Multi-layer sumSqNat differential checks
    for _ in range(15):
        k_layers = rng.randint(0, 6)
        ds = [rng.randint(0, 20) for _ in range(k_layers)]
        got_sq = int(call_cli(exe, "sumsq", *[str(v) for v in ds]))
        exp_sq = sum(v * v for v in ds)
        total_inputs += 1
        if got_sq != exp_sq:
            failures += 1

    results_md = (
        "# Differential Test Record\n\n"
        "- Oracle: Python 3 int and fractions.Fraction\n"
        f"- Seed: {SEED}\n"
        f"- Inputs: {total_inputs}\n"
        f"- Failures: {failures}\n"
    )
    (ROOT / "tests" / "TEST-RESULTS.md").write_text(results_md, encoding="utf-8", newline="\n")
    if failures != 0:
        raise RuntimeError(f"{failures} differential test failure(s) across {total_inputs} inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
