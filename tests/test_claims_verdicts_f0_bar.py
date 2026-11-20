"""Tests for mission bar, f0 gate, formal-claims-audit verdicts, soko integrity, claim hygiene, and Family C security."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from mcproof.oracles import (
    grade_family_completion,
    run_claim_hygiene_oracle,
    run_f0_gate_oracle,
    run_mission_bar_oracle,
    run_prose_and_mixed_zone_oracle,
    run_soko_integrity_and_evidence_oracle,
    run_verdicts_oracle,
    sanitize_verdict_id,
)
from mcproof.paths import repo_root

from helpers import expect_eq, expect_false, expect_in, expect_true, requires_dep


@requires_dep("soko", "mission", "f0", "formal-claims-audit")
def test_pinned_soko_mission_f0_and_verdicts_oracles_pass() -> None:
    soko_rec = run_soko_integrity_and_evidence_oracle()
    expect_true(soko_rec.passed, f"soko integrity failed: {soko_rec.findings}")

    bar_rec = run_mission_bar_oracle(repo_root() / "lean", no_lean=True, offline=True)
    expect_true(bar_rec.passed, f"mission bar check failed: {bar_rec.findings}")
    expect_eq(bar_rec.epistemic_status, "IN_PROGRESS")

    f0_rec = run_f0_gate_oracle()
    expect_true(f0_rec.passed, f"f0 gate failed: {f0_rec.findings}")
    expect_eq(f0_rec.checks["mutations_killed"], 4)

    verdict_rec = run_verdicts_oracle()
    expect_true(verdict_rec.passed, f"empty main verdicts dir should pass structurally: {verdict_rec.findings}")


@requires_dep("formal-claims-audit")
def test_verdicts_oracle_validates_40char_sha_and_unique_keys(tmp_path: Path) -> None:
    good_verdict = {
        "id": "sample-verdict-01",
        "source_repo": "https://github.com/Proven-Commons/tar",
        "source_commit": "7517a86223e6741b0a6b5c0b3b0fabcf68347bee",
        "claim": "Extracted paths stay inside destination.",
        "claim_link": "https://github.com/Proven-Commons/tar/blob/main/README.md",
        "verdict": "weaker",
        "axioms": ["propext", "Classical.choice", "Quot.sound"],
        "command": "lake comparator --paranoid",
        "output_summary": "Statement omits embedded slash check.",
        "reviewer": "test-reviewer",
        "lab_statement": {"file": "Archive.lean", "name": "extractAll_safe", "lean": "True"},
        "independent_statement": {"lean": "True", "source": "Contained.lean", "author": "auditor"},
        "tool": {"name": "comparator", "version": "5.0.0", "lean_version": "4.35.0"},
    }
    good_file = tmp_path / "sample-verdict-01.json"
    good_file.write_text(json.dumps(good_verdict, indent=2), encoding="utf-8")
    rec_ok = run_verdicts_oracle(good_file)
    expect_true(rec_ok.passed, f"valid verdict rejected: {rec_ok.findings}")

    bad_verdict = dict(good_verdict)
    bad_verdict["source_commit"] = "7517a86"
    bad_file = tmp_path / "sample-verdict-01.json"
    bad_file.write_text(json.dumps(bad_verdict, indent=2), encoding="utf-8")
    rec_bad = run_verdicts_oracle(bad_file)
    expect_false(rec_bad.passed, "7-char source_commit must fail check_verdicts.py")


def test_family_c_verdict_id_blocks_path_traversal_and_writes_zero_files(tmp_path: Path) -> None:
    canary_target = tmp_path / "escaped.json"
    bad_ids = [
        "../escaped",
        "../../escaped",
        "/etc/passwd",
        "C:/foo",
        "C:\\foo",
        str(canary_target),
        "foo..bar",
        ".hidden",
        "",
    ]
    for bad_id in bad_ids:
        expect_eq(sanitize_verdict_id(bad_id), None, f"expected {bad_id!r} to be rejected")
        doc = f"""# Verdict Review

Claim tier: `VERIFIED`

```json
{json.dumps({"id": bad_id, "verdict": "weaker", "source_commit": "7517a86223e6741b0a6b5c0b3b0fabcf68347bee"})}
```

## What is not proved

- Performance sits outside the scope of this check.

## What you must trust

- Lean kernel, compiler, runtime, and hardware.
"""
        old_tmp = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = str(tmp_path)
        try:
            rec = grade_family_completion("C", doc, expected_tier="VERIFIED")
        finally:
            if old_tmp is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = old_tmp
        expect_false(rec.passed, f"malicious verdict id {bad_id!r} must fail closed")
        expect_in("INVALID_VERDICT_ID", {f["rule"] for f in rec.findings})
        expect_eq(list(tmp_path.iterdir()), [], f"zero files may be left in {tmp_path} for {bad_id!r}")


def test_claim_tier_precedence_is_deterministic_across_python_hash_seeds() -> None:
    ambiguous_doc = """# Multi-Tier Discussion

This note compares CONJECTURE, KNOWN, VERIFIED, and PROVEN claims without an explicit header.

## What is not proved

- Unbounded inputs sit outside finite checks.

## What you must trust

- Python runtime and host hardware.
"""
    code = (
        "import json, sys; "
        f"sys.path.insert(0, {str(repo_root() / 'src')!r}); "
        "from mcproof.oracles import run_claim_hygiene_oracle; "
        f"r = run_claim_hygiene_oracle({ambiguous_doc!r}); "
        "print(json.dumps({'tier': r.checks['declared_tier'], 'sha': r.receipt_sha256}))"
    )
    seen_tiers: set[str] = set()
    seen_shas: set[str] = set()
    for seed in ("0", "1", "2", "42", "99999"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout.strip())
        seen_tiers.add(out["tier"])
        seen_shas.add(out["sha"])
    expect_eq(seen_tiers, {"CONJECTURE"}, "least-inflationary tier present must win deterministically")
    expect_eq(len(seen_shas), 1, f"receipt_sha256 drifted across PYTHONHASHSEED: {seen_shas}")


def test_dupes_fallback_records_finding_on_unparseable_stderr_failure(tmp_path: Path) -> None:
    fake_prose = tmp_path / "fake_prose_gate.py"
    fake_prose.write_text(
        "import sys\n"
        "if '--dupes' in sys.argv:\n"
        "    sys.stderr.write('UNFORMATTED DUPES ERROR ON STDERR\\n')\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    rec = run_prose_and_mixed_zone_oracle(
        "# Clean Heading\n\nPlain prose paragraph.\n",
        verify_embedded_lean=False,
        prose_script_override=fake_prose,
    )
    expect_false(rec.passed, "non-zero --dupes exit with unindented stderr must fail closed")
    expect_in("PROSE_DUPES_VIOLATION", {f["rule"] for f in rec.findings})


def test_claim_hygiene_enforces_disclaimers_and_blocks_tier_inflation() -> None:
    honest_doc = """# Finite Recurrence Check

Claim tier: `VERIFIED`

Checked exact integer residual vectors up to width 5 with zero failures.

## What is not proved

- Widths above 5 are not checked by this finite script.
- Execution speed is outside the check.

## What you must trust

- Python 3 exact `int` arithmetic and the host CPU hardware and runtime.
"""
    rec_honest = run_claim_hygiene_oracle(honest_doc, expected_tier="VERIFIED")
    expect_true(rec_honest.passed, f"honest VERIFIED doc failed: {rec_honest.findings}")

    inflated_doc = """# Finite Recurrence Check

Claim tier: `PROVEN`

Tested up to n = 100 via finite check and bounded search with zero counterexamples.

## What is not proved

- Only finite n <= 100 was sampled.

## What you must trust

- Python runtime and host hardware.
"""
    rec_inflated = run_claim_hygiene_oracle(inflated_doc, has_kernel_proof=False)
    expect_false(rec_inflated.passed, "finite check claiming PROVEN must fail")
    expect_in("CLAIM_TIER_INFLATION", {f["rule"] for f in rec_inflated.findings})

    missing_sections_doc = """# Theorem Note

Claim tier: `PROVEN`

Proved `a + b = b + a` in Lean 4.
"""
    rec_missing = run_claim_hygiene_oracle(missing_sections_doc, has_kernel_proof=True)
    expect_false(rec_missing.passed, "missing What is not proved / What you must trust must fail")
    m_rules = {f["rule"] for f in rec_missing.findings}
    expect_in("MISSING_WHAT_IS_NOT_PROVED", m_rules)
    expect_in("MISSING_WHAT_YOU_MUST_TRUST", m_rules)
