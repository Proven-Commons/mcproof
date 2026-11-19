"""Tests for Plane 1 spec token target, SHA-256 lineage binding, prose gates, mde guard, and CLI grader."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from mcproof.cli import main as cli_main
from mcproof.lineage import (
    CANONICAL_ZONE_MANIFEST_ID,
    estimate_spec_tokens,
    find_forbidden_control_bytes,
    verify_lineage_manifest,
)
from mcproof.oracles import (
    grade_family_completion,
    run_mde_code_audit,
    run_prose_and_mixed_zone_oracle,
)
from mcproof.paths import repo_root

from helpers import expect_eq, expect_false, expect_in, expect_true


def test_plane1_spec_token_budget_and_lineage_binding() -> None:
    r_root = repo_root()
    spec_path = r_root / "spec" / "plane1_formal_spec.md"
    expect_true(spec_path.is_file(), "spec/plane1_formal_spec.md must exist")

    stats = estimate_spec_tokens(spec_path.read_text(encoding="utf-8"))
    expect_true(100000 <= stats["utf8_bytes"] <= 120000, f"expected ~106.8k bytes, got {stats['utf8_bytes']}")
    if stats["cl100k_base_tokens"] != stats["char_div4_estimate"]:
        toks = stats["cl100k_base_tokens"]
        expect_true(28000 <= toks <= 36000, f"expected ~32.7k cl100k tokens, got {toks}")
    lineage_doc = json.loads((r_root / "spec" / "lineage.json").read_text(encoding="utf-8"))
    pinned_toks = int(lineage_doc["plane1_spec_token_stats"]["cl100k_base_tokens"])
    expect_true(28000 <= pinned_toks <= 36000, f"expected ~32.7k pinned tokens, got {pinned_toks}")

    rep = verify_lineage_manifest(r_root)
    expect_true(rep.passed, f"lineage verification failed: {rep.findings}")
    expect_false(rep.stale_lineage, "lineage must not be stale")
    expect_false(rep.zone_manifest_drift, "zone manifest must match canonical digest")
    expect_eq(rep.zone_manifest_id, CANONICAL_ZONE_MANIFEST_ID)


def test_lineage_detects_single_byte_plane1_tamper_and_zone_drift(tmp_path: Path) -> None:
    work = tmp_path / "repo_copy"
    work.mkdir()
    for sub in ("spec", "schemas", "lean"):
        shutil.copytree(repo_root() / sub, work / sub, ignore=shutil.ignore_patterns(".lake"))

    # 1. Verify clean copy passes
    clean_rep = verify_lineage_manifest(work)
    expect_true(clean_rep.passed, f"copied tree should verify cleanly: {clean_rep.findings}")

    # 2. Flip 1 byte in spec/plane1_formal_spec.md -> must trigger stale_lineage
    spec_file = work / "spec" / "plane1_formal_spec.md"
    orig_bytes = spec_file.read_bytes()
    spec_file.write_bytes(orig_bytes + b"\n")
    tampered_rep = verify_lineage_manifest(work)
    expect_false(tampered_rep.passed, "1-byte Plane 1 edit must fail closed")
    expect_true(tampered_rep.stale_lineage, "stale_lineage flag must be True")

    # Restore spec and mutate zone-manifest.v0.1.json -> must trigger zone_manifest_drift
    spec_file.write_bytes(orig_bytes)
    zm_path = work / "schemas" / "zone-manifest.v0.1.json"
    zm_data = json.loads(zm_path.read_text(encoding="utf-8"))
    zm_data["mde_version"] = "0.2.0-drifted"
    zm_path.write_text(json.dumps(zm_data, indent=2), encoding="utf-8")
    drift_rep = verify_lineage_manifest(work)
    expect_false(drift_rep.passed, "rotated zone manifest must fail closed")
    expect_true(drift_rep.zone_manifest_drift, "zone_manifest_drift flag must be True")


def test_all_markdown_docs_pass_check_prose_and_dupes() -> None:
    r_root = repo_root()
    md_files = [
        r_root / "README.md",
        r_root / "docs" / "CONTINUITY.md",
        r_root / "spec" / "plane1_formal_spec.md",
        r_root / "lean" / "README.md",
        r_root / "lean" / "SPEC.md",
        r_root / "lean" / "tests" / "TEST-RESULTS.md",
        r_root / "datasets" / "README.md",
        r_root / "compile" / "README.md",
        r_root / "stack" / "README.md",
        r_root / "stack" / "STACK_REPORT.md",
        r_root / "verification" / "VERIFICATION_REPORT.md",
    ]
    for md_path in md_files:
        expect_true(md_path.is_file(), f"missing markdown doc {md_path.name}")
        rec = run_prose_and_mixed_zone_oracle(
            md_path.read_text(encoding="utf-8"),
            label=md_path.name,
            verify_embedded_lean=False,
        )
        expect_true(rec.passed, f"prose/dupes failure in {md_path.name}: {rec.findings}")


def test_entire_repo_passes_mde_guard_code_audit() -> None:
    rec = run_mde_code_audit([repo_root()])
    expect_true(rec.passed, f"mde guard --code-audit found violations in repo: {rec.findings}")


def test_family_d_mixed_grader_and_cli_smoke(tmp_path: Path) -> None:
    good_family_d = """# Bezout Coprime Audit Note

This report verifies coprime divisor preservation at commit `3165e20e7a16c0035cab2fd01231e78e4e1d7f86`.

Claim tier: `PROVEN`

<div data-eido-skip="true">
Formal statement pinned to commit `3165e20e7a16c0035cab2fd01231e78e4e1d7f86` (`propext`, `Classical.choice`, `Quot.sound`).
</div>

```lean
theorem add_zero_right_check (n : Nat) : n + 0 = n := by
  omega
```

## What is not proved

- External CLI serialization sits outside this theorem.

## What you must trust

- The Lean 4.35.0 kernel, compiler, runtime, and host hardware.
"""
    rec_d = grade_family_completion("D", good_family_d, expected_tier="PROVEN")
    expect_true(rec_d.passed, f"valid Family D completion rejected: {rec_d.findings}")

    # Strip data-eido-skip -> must fail Hazard 7 protection
    stripped_d = good_family_d.replace('data-eido-skip="true"', 'class="plain"')
    rec_stripped = grade_family_completion("D", stripped_d, expected_tier="PROVEN")
    expect_false(rec_stripped.passed, "Family D without data-eido-skip must fail")
    expect_in("MISSING_DATA_EIDO_SKIP", {f["rule"] for f in rec_stripped.findings})

    # CLI smoke check
    sample_md = tmp_path / "mixed.md"
    sample_md.write_text(good_family_d, encoding="utf-8")
    rc = cli_main(["--json", "grade", "--family", "D", "--input", str(sample_md), "--expected-tier", "PROVEN"])
    expect_eq(rc, 0, "mcproof grade CLI should exit 0 on valid Family D")


def test_zero_control_bytes_across_tracked_files_and_nul_rejected(tmp_path: Path) -> None:
    r_root = repo_root()
    for p in sorted(r_root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(r_root)
        if any(part in (".git", ".venv", ".lake", "__pycache__", ".pytest_cache", ".mde") for part in rel.parts):
            continue
        if p.suffix in (".gguf", ".wfsl"):
            continue
        ctrl = find_forbidden_control_bytes(p.read_bytes())
        expect_eq(ctrl, [], f"unexpected control bytes in {rel.as_posix()}: {ctrl[:3]}")

    # Planting a NUL (0x00) or SOH (0x01) byte in Plane 1 spec must fail verify_lineage_manifest
    work = tmp_path / "ctrl_copy"
    work.mkdir()
    for sub in ("spec", "schemas", "lean"):
        shutil.copytree(r_root / sub, work / sub, ignore=shutil.ignore_patterns(".lake"))
    spec_copy = work / "spec" / "plane1_formal_spec.md"
    spec_copy.write_bytes(spec_copy.read_bytes() + b"\x00")
    rep = verify_lineage_manifest(work)
    expect_false(rep.passed, "planted NUL control byte must fail lineage verification")
    expect_true(rep.stale_lineage, "planted NUL control byte must mark stale_lineage")
