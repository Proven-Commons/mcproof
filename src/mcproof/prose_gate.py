#!/usr/bin/env python3
"""Self-contained deterministic prose and duplicate-reference gate for mcproof.

Vendored inside `src/mcproof/prose_gate.py` so fresh clones on Linux, macOS, and
Windows run all prose and `--dupes` checks with zero external home-directory scripts.

CLI usage:
    python3 -m mcproof.prose_gate <file> [<file> ...]
    python3 -m mcproof.prose_gate --dupes <file> [<file> ...]
    python3 -m mcproof.prose_gate --text "candidate markdown string"

Exit codes: 0 clean, 1 findings detected, 3 usage/IO error.
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Sequence
import urllib.parse

EM_DASH = "\u2014"

BANNED_PHRASES: tuple[str, ...] = (
    r"two things worth stating",
    r"findings first",
    r"the honest gap",
    r"i want to be upfront",
    r"one caveat worth flagging",
    r"two notes for",
    r"note on mechanism",
    r"a few thoughts",
    r"worth settling",
    r"worth pinning down",
    r"something to consider",
    r"\b(two|three|four|five) ([a-z]+ ){0,3}(notes|points|things|thoughts|observations|findings)[.:]",
    r"^one ([a-z]+ ){1,4}notes?\s*[:.]",
    r"^a quick note\b",
    r"i'?d frame this differently",
    r"i'?d argue",
    r"i would say",
    r"my earlier note",
    r"this deserves",
    r"stand on their own",
    r"deserves precision",
    r"after tracing",
    r"it turns out that",
    r"i checked .{0,20} and found",
    r"the right shape",
    r"right design",
    r"exactly what is needed",
    r"the natural single base",
    r"the obvious choice",
    r"a step in the right direction",
    r"the strongest evidence",
    r"the strongest proof",
    r"the strongest signal",
    r"the best datapoint",
    r"the best data point",
    r"the best report",
    r"the best analysis",
    r"the cleanest proof",
    r"^notably",
    r"^importantly",
    r"^it is worth noting",
    r"^at its core",
    r"that is okay",
    r"no shame",
    r"none subsumes another",
    r"the rest follows",
    r"nothing else to add",
)

# Host filesystem paths and private network addresses that must never be published
IDENTIFIER_PATTERNS: tuple[str, ...] = (
    "/" + "Users/",
    "/" + "home/",
    r"[A-Za-z]:\\Users\\",
    "ci@" + r"example\.invalid",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b",
)

MENTION_RE = re.compile(r"(?<![\w.@])@\w+")


def strip_code(text: str) -> str:
    """Drop fenced blocks and inline backtick code while preserving exact line numbers."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def check(name: str, raw: str) -> list[str]:
    prose = strip_code(raw)
    findings: list[str] = []

    for n, line in enumerate(prose.splitlines(), 1):
        if EM_DASH in line:
            findings.append(f"{name}:{n}: em dash (T2) -> use a period or comma: {line.strip()[:110]}")
        if ";" in line and len(line) > 60:
            findings.append(f"{name}:{n}: semicolon stitching clauses (T2) -> prefer a period: {line.strip()[:110]}")

    for pat in BANNED_PHRASES:
        for m in re.finditer(pat, prose, re.IGNORECASE | re.MULTILINE):
            line_no = prose[: m.start()].count("\n") + 1
            findings.append(f"{name}:{line_no}: banned phrase '{m.group(0)}' (AI tell)")

    for pat in IDENTIFIER_PATTERNS:
        for m in re.finditer(pat, raw, re.IGNORECASE):
            line_no = raw[: m.start()].count("\n") + 1
            findings.append(f"{name}:{line_no}: non-portable path or private identifier '{m.group(0)}'")

    for m in MENTION_RE.finditer(prose):
        line_no = prose[: m.start()].count("\n") + 1
        findings.append(
            f"{name}:{line_no}: @-mention '{m.group(0)}' -> remove handle mention from prose"
        )

    longs = [n for n, ln in enumerate(prose.splitlines(), 1) if len(ln) > 420 and not ln.strip().startswith("|")]
    if longs:
        findings.append(f"{name}: paragraph over 420 chars on line(s) {longs} -> split it")

    return findings


def check_dupes(name: str, raw: str) -> list[str]:
    """Duplicate-reference gate: each external URL / PR # / issue # appears at most once."""
    counts: dict[str, int] = {}
    first_line: dict[str, int] = {}
    forms: dict[str, list[str]] = {}
    url_spans: list[tuple[int, int]] = []

    def _record(key: str, form: str, pos: int) -> None:
        counts[key] = counts.get(key, 0) + 1
        first_line.setdefault(key, raw[:pos].count("\n") + 1)
        forms.setdefault(key, [])
        if form not in forms[key]:
            forms[key].append(form)

    gh_path_re = re.compile(r"github\.com/[^/\s]+/[^/\s]+/(?:pull|issues)/(\d+)", re.IGNORECASE)
    for m in re.finditer(r"https?://\S+", raw, re.IGNORECASE):
        url = m.group(0).rstrip(".,;:!?'\"`)]}>")
        url_spans.append((m.start(), m.end()))
        gh = gh_path_re.search(url)
        if gh:
            _record("gh#" + gh.group(1), url, m.start())
            continue
        try:
            parts = urllib.parse.urlparse(url)
            if parts.scheme and parts.netloc:
                key = (parts.scheme.lower() + "://" + parts.netloc.lower() + parts.path).lower()
            else:
                key = url.lower()
        except ValueError:
            key = url.lower()
        _record(key, url, m.start())

    for m in re.finditer(r"(?:PR|issue)?\s*#(\d+)", raw, re.IGNORECASE):
        if any(s <= m.start() < e for s, e in url_spans):
            continue
        key = "gh#" + m.group(1)
        _record(key, m.group(0).strip(), m.start())

    out: list[str] = []
    for k in sorted(counts):
        n = counts[k]
        if n > 1:
            seen = "; ".join(forms.get(k, [k]))
            out.append(
                f"{name}:{first_line[k]}: duplicate reference '{k}' appears {n}x -> mention once (seen: {seen})"
            )
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic blocking prose and duplicate-reference gate.")
    parser.add_argument("--dupes", action="store_true", help="Check duplicate URL / PR # / issue # references")
    parser.add_argument("--text", nargs="+", default=None, help="Literal markdown string to check")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    if args.text is not None:
        sources = [("<text>", " ".join(args.text))]
    elif not args.files:
        print(__doc__)
        return 3
    else:
        sources = []
        for p in args.files:
            try:
                with open(p, encoding="utf-8") as fh:
                    sources.append((p, fh.read()))
            except OSError as exc:
                print(f"prose_gate: cannot read {p}: {exc}", file=sys.stderr)
                return 3

    if args.dupes:
        findings: list[str] = []
        for name, text in sources:
            findings.extend(check_dupes(name, text))
        if findings:
            print(f"check-prose --dupes: {len(findings)} duplicate reference(s). DO NOT POST:\n")
            for f in findings:
                print(f"  {f}")
            return 1
        print(f"check-prose --dupes: clean ({len(sources)} file(s))")
        return 0

    findings = []
    for name, text in sources:
        findings.extend(check(name, text))
    if findings:
        print(f"check-prose: {len(findings)} finding(s). DO NOT POST until each is fixed or justified:\n")
        for f in findings:
            print(f"  {f}")
        return 1

    total_lines = sum(len(t.splitlines()) for _, t in sources)
    print(f"check-prose: clean ({len(sources)} file(s), {total_lines} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
