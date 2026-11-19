"""Tests for Plane 1 spec token stats, SHA-256 lineage binding, vendored prose_gate, datasets SHA256SUMS, and CLI boundary."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

from mcproof.cli import main as cli_main
from mcproof.lineage import (
    CANONICAL_ZONE_MANIFEST_ID,
    compute_corpus_tree_sha256,
    estimate_spec_tokens,
    find_forbidden_control_bytes,
    verify_lineage_manifest,
)
from mcproof.oracles import (
    grade_family_completion,
    run_mde_code_audit,
    run_prose_and_mixed_zone_oracle,
)
from mcproof.paths import check_prose_script, repo_root

from helpers import expect_eq, expect_false, expect_in, expect_true, requires_dep, requires_lean, requires_mde


def test_plane1_spec_token_budget_and_tiktoken_missing_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    r_root = repo_root()
    spec_path = r_root / "spec" / "plane1_formal_spec.md"
    expect_true(spec_path.is_file(), "spec/plane1_formal_spec.md must exist")
    spec_text = spec_path.read_text(encoding="utf-8")

    stats = estimate_spec_tokens(spec_text)
    expect_true(100000 <= stats["utf8_bytes"] <= 120000, f"expected ~106.8k bytes, got {stats['utf8_bytes']}")
    expect_eq(stats["qwen35_tokens"], 32216)
    if stats["cl100k_base_tokens"] is not None:
        toks = int(stats["cl100k_base_tokens"])
        expect_true(28000 <= toks <= 36000, f"expected ~30.9k cl100k tokens, got {toks}")

    # Simulate missing tiktoken: cl100k_base_tokens must be None, never utf8_bytes // 4
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    no_tik = estimate_spec_tokens(spec_text)
    expect_eq(no_tik["cl100k_base_tokens"], None, "missing tiktoken must emit None, not char_div4_estimate")
    expect_eq(no_tik["cl100k_tokenizer"], None)
    expect_eq(no_tik["qwen35_tokens"], 32216)

    rep = verify_lineage_manifest(r_root)
    expect_true(rep.passed, f"lineage verification failed: {rep.findings}")
    expect_false(rep.stale_lineage, "lineage must not be stale")
    expect_false(rep.zone_manifest_drift, "zone manifest must match canonical digest")
    expect_eq(rep.zone_manifest_id, CANONICAL_ZONE_MANIFEST_ID)


def test_lineage_detects_tamper_siliconcordat_drift_and_deps_drift(tmp_path: Path) -> None:
    work = tmp_path / "repo_copy"
    work.mkdir()
    for sub in ("spec", "schemas", "lean"):
        shutil.copytree(repo_root() / sub, work / sub, ignore=shutil.ignore_patterns(".lake"))

    # 1. Clean copy passes without external deps when require_deps=False
    clean_rep = verify_lineage_manifest(work, d_dir=tmp_path / "absent_deps", require_deps=False)
    expect_true(clean_rep.passed, f"copied tree should verify cleanly: {clean_rep.findings}")
    expect_false(clean_rep.deps_manifest_verified)

    # 2. require_deps=True fails closed when DEPS_MANIFEST.json is absent
    req_rep = verify_lineage_manifest(work, d_dir=tmp_path / "absent_deps", require_deps=True)
    expect_false(req_rep.passed, "require_deps=True must fail when DEPS_MANIFEST.json is missing")

    # 3. Flip 1 byte in spec/plane1_formal_spec.md -> stale_lineage
    spec_file = work / "spec" / "plane1_formal_spec.md"
    orig_bytes = spec_file.read_bytes()
    spec_file.write_bytes(orig_bytes + b"\n")
    tampered_rep = verify_lineage_manifest(work, d_dir=tmp_path / "absent_deps")
    expect_false(tampered_rep.passed, "1-byte Plane 1 edit must fail closed")
    expect_true(tampered_rep.stale_lineage)
    spec_file.write_bytes(orig_bytes)

    # 4. Self-referential tamper of siliconcordat_commits in lineage.json -> caught against SILICONCORDAT_PINNED_COMMITS
    lin_file = work / "spec" / "lineage.json"
    orig_lin = lin_file.read_text(encoding="utf-8")
    lin_obj = json.loads(orig_lin)
    lin_obj["siliconcordat_commits"]["siliconcordat/warp"] = "0" * 40
    lin_file.write_text(json.dumps(lin_obj, indent=2) + "\n", encoding="utf-8")
    sc_rep = verify_lineage_manifest(work, d_dir=tmp_path / "absent_deps")
    expect_false(sc_rep.passed, "drifted siliconcordat_commits must fail closed")

    # 5. Self-referential tamper of upstream_repos + recomputed tree hash -> caught by DEPS_MANIFEST.json & git HEAD
    lin_obj = json.loads(orig_lin)
    fake_deps = tmp_path / "fake_deps"
    fake_deps.mkdir()
    manifest_repos = {}
    for k, v in lin_obj["upstream_repos"].items():
        manifest_repos[k] = {"dir": k.split("/")[-1], "url": v["url"], "commit": v["commit"], "roles": v["roles"]}
    (fake_deps / "DEPS_MANIFEST.json").write_text(json.dumps({"repos": manifest_repos}), encoding="utf-8")

    lin_obj["upstream_repos"]["ahrazzle/soko"]["commit"] = "a" * 40
    lin_obj["source_lineage"]["corpus_tree_sha256"] = compute_corpus_tree_sha256(
        lin_obj["tracked_plane1_files"],
        lin_obj["upstream_repos"],
        lin_obj["zone_manifest_id"],
    )
    lin_file.write_text(json.dumps(lin_obj, indent=2) + "\n", encoding="utf-8")
    dm_rep = verify_lineage_manifest(work, d_dir=fake_deps)
    expect_false(dm_rep.passed, "recomputed tree with altered upstream commit must fail against DEPS_MANIFEST.json")
    lin_file.write_text(orig_lin, encoding="utf-8")

    # 6. Git checkout HEAD drift under deps/ -> caught by git rev-parse HEAD check
    soko_git = fake_deps / "soko"
    soko_git.mkdir()
    subprocess.run(["git", "-C", str(soko_git), "init", "--quiet"], check=True)
    (soko_git / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-C",
            str(soko_git),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@users.noreply.github.com",
            "add",
            "README.md",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(soko_git),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@users.noreply.github.com",
            "commit",
            "-m",
            "init",
            "--quiet",
        ],
        check=True,
    )
    git_drift_rep = verify_lineage_manifest(work, d_dir=fake_deps)
    expect_false(git_drift_rep.passed, "drifted git HEAD in deps/soko must fail verify_lineage_manifest")


def test_vendored_prose_gate_runs_without_home_directory_scripts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("MCPROOF_CHECK_PROSE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    script = check_prose_script()
    expect_eq(script.name, "prose_gate.py")
    expect_true(script.is_file(), "vendored prose_gate.py must exist inside repo")

    r_root = repo_root()
    md_files = [
        r_root / "README.md",
        r_root / "docs" / "CONTINUITY.md",
        r_root / "docs" / "CROSS_POLLINATION.md",
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


def test_datasets_sha256sums_matches_all_294_files_pure_python() -> None:
    ds_root = repo_root() / "datasets"
    sums_path = ds_root / "SHA256SUMS"
    expect_true(sums_path.is_file(), "datasets/SHA256SUMS must exist")
    lines = [ln.strip() for ln in sums_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    expect_eq(len(lines), 294, "expected 294 tracked dataset files")

    listed: set[str] = set()
    for ln in lines:
        sha, rel = ln.split("  ", 1)
        listed.add(rel)
        target = ds_root / rel
        expect_true(target.is_file(), f"missing dataset file {rel}")
        actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        expect_eq(actual_sha, sha, f"SHA-256 mismatch on {rel}")

    actual_files = {
        p.relative_to(ds_root).as_posix()
        for p in ds_root.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS" and ".mde" not in p.parts and "__pycache__" not in p.parts
    }
    expect_eq(listed, actual_files, "unlisted or missing files in datasets/")


def test_cli_exception_boundary_emits_fail_closed_json_receipt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("MCPROOF_DEPS_DIR", str(tmp_path / "missing_deps"))
    rc = cli_main(["--json", "f0-gate"])
    expect_eq(rc, 1, "missing dep must exit 1 with structured JSON receipt")
    out = capsys.readouterr().out
    parsed = json.loads(out)
    expect_eq(parsed["schema"], "mcproof-receipt/v0.1")
    expect_false(parsed["passed"])
    expect_eq(parsed["epistemic_status"], "REJECTED")
    expect_in("ORACLE_EXEC_ERROR", {f["rule"] for f in parsed["findings"]})


@requires_mde()
def test_entire_repo_passes_mde_guard_code_audit() -> None:
    rec = run_mde_code_audit([repo_root() / "src", repo_root() / "tests", repo_root() / "datasets" / "scripts"])
    expect_true(rec.passed, f"mde guard --code-audit found violations: {rec.findings}")


@requires_dep("soko")
@requires_lean()
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

    stripped_d = good_family_d.replace('data-eido-skip="true"', 'class="plain"')
    rec_stripped = grade_family_completion("D", stripped_d, expected_tier="PROVEN")
    expect_false(rec_stripped.passed, "Family D without data-eido-skip must fail")
    expect_in("MISSING_DATA_EIDO_SKIP", {f["rule"] for f in rec_stripped.findings})

    sample_md = tmp_path / "mixed.md"
    sample_md.write_text(good_family_d, encoding="utf-8")
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        rc = cli_main(["--json", "grade", "--family", "D", "--input", str(sample_md), "--expected-tier", "PROVEN"])
    finally:
        sys.stdout = old_stdout
    expect_eq(rc, 0, "mcproof grade CLI should exit 0 on valid Family D")


def test_zero_control_bytes_across_tracked_files_and_nul_rejected(tmp_path: Path) -> None:
    r_root = repo_root()
    for p in sorted(r_root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(r_root)
        if any(part in (".git", ".venv", ".lake", "__pycache__", ".pytest_cache", ".mde") for part in rel.parts):
            continue
        if p.suffix in (".gguf", ".wfsl", ".npz", ".bin"):
            continue
        ctrl = find_forbidden_control_bytes(p.read_bytes())
        expect_eq(ctrl, [], f"unexpected control bytes in {rel.as_posix()}: {ctrl[:3]}")

    work = tmp_path / "ctrl_copy"
    work.mkdir()
    for sub in ("spec", "schemas", "lean"):
        shutil.copytree(r_root / sub, work / sub, ignore=shutil.ignore_patterns(".lake"))
    spec_copy = work / "spec" / "plane1_formal_spec.md"
    spec_copy.write_bytes(spec_copy.read_bytes() + b"\x00")
    rep = verify_lineage_manifest(work, d_dir=tmp_path / "absent_deps")
    expect_false(rep.passed, "planted NUL control byte must fail lineage verification")
    expect_true(rep.stale_lineage, "planted NUL control byte must mark stale_lineage")


def test_leak_audit_ignores_public_spec_boilerplate_and_catches_real_vault_leak(tmp_path: Path) -> None:
    r_root = repo_root()
    sys.path.insert(0, str(r_root / "verification"))
    from leak_audit import audit_directory_zero_leaks, verify_zero_vault_leak_text  # noqa: PLC0415

    spec_text = (r_root / "spec" / "plane1_formal_spec.md").read_text(encoding="utf-8")
    shared_footer = "## What you must trust\n\n- Standard Lean axioms `[propext, Classical.choice, Quot.sound]`."
    # If a vault prompt embeds a substring already in plane1_formal_spec.md, boilerplate does not false-positive
    boilerplate_line = next(ln.strip() for ln in spec_text.splitlines() if len(ln.strip()) >= 40)
    synthetic_prompt = (
        "Prove unique sealed theorem vault_secret_bijection_omega_99421 with zero escape hatches. "
        + boilerplate_line
    )
    safe_res = verify_zero_vault_leak_text(
        boilerplate_line + "\n" + shared_footer,
        [synthetic_prompt],
        label="doc.md",
        public_spec_text=spec_text,
    )
    expect_true(safe_res["windows_checked"] >= 1, "expected non-boilerplate vault windows checked")

    # Genuine leak of unique vault prompt prefix MUST fail closed
    raised = False
    try:
        verify_zero_vault_leak_text(
            "Leaked: Prove unique sealed theorem vault_secret_bijection_omega_99421",
            [synthetic_prompt],
            label="leaked.md",
            public_spec_text=spec_text,
        )
    except RuntimeError as exc:
        raised = "SECURITY VIOLATION" in str(exc)
    expect_true(raised, "expected genuine 32-char vault prompt window leak to raise RuntimeError")

    sub = tmp_path / "sample_dir"
    sub.mkdir()
    (sub / "clean.md").write_text(boilerplate_line + "\n", encoding="utf-8")
    summary = audit_directory_zero_leaks(
        sub,
        [synthetic_prompt],
        public_spec_path=r_root / "spec" / "plane1_formal_spec.md",
    )
    expect_eq(summary["files_checked"], 1, "expected 1 file audited")
