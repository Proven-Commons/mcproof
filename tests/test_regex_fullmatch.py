"""Anchored digest, commit and rational patterns must reject a trailing newline."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

from mcproof.domain_protocol import _parse_exact_rational, audit_transition_certificate
from mcproof.lineage import StaleLineageError, build_lineage_manifest
from mcproof.paths import repo_root

from helpers import expect_eq, expect_in

HEX64 = "a" * 64


def _rules(cert: dict) -> list[str]:
    return [f["rule"] for f in audit_transition_certificate(cert)["findings"]]


def test_canonical_rational_still_parses() -> None:
    expect_eq(str(_parse_exact_rational("3/4")), "3/4")
    expect_eq(str(_parse_exact_rational("-5")), "-5")


def test_rational_trailing_newline_rejected() -> None:
    with pytest.raises(ValueError):
        _parse_exact_rational("3/4\n")


def test_witness_digest_trailing_newline_rejected() -> None:
    ok = {"epistemic_status": "VERIFIED", "witness_or_proof_sha256": HEX64,
          "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64}}
    expect_eq(_rules(ok), [])
    bad_w = {**ok, "witness_or_proof_sha256": HEX64 + "\n"}
    expect_in("CERT_INVALID_WITNESS_SHA256", _rules(bad_w))


def test_tcb_checker_digest_trailing_newline_rejected() -> None:
    bad = {"epistemic_status": "VERIFIED", "witness_or_proof_sha256": HEX64,
           "tcb_pins": {"tcb_manifest_verified": True, "checker_sha256": HEX64 + "\n"}}
    expect_in("CERT_TCB_MANIFEST_UNLOCKED", _rules(bad))


def test_upstream_commit_trailing_newline_rejected(tmp_path: Path) -> None:
    root = repo_root()
    lin = json.loads((root / "spec" / "lineage.json").read_text(encoding="utf-8"))
    repos = {}
    for k, v in lin["upstream_repos"].items():
        repos[k] = {"dir": k.split("/")[-1], "url": v["url"], "commit": v["commit"], "roles": v["roles"]}
    deps = tmp_path / "deps"
    deps.mkdir()
    (deps / "DEPS_MANIFEST.json").write_text(json.dumps({"repos": repos}), encoding="utf-8")
    build_lineage_manifest(root, d_dir=deps)
    first = sorted(repos)[0]
    repos[first]["commit"] += "\n"
    (deps / "DEPS_MANIFEST.json").write_text(json.dumps({"repos": repos}), encoding="utf-8")
    with pytest.raises(StaleLineageError):
        build_lineage_manifest(root, d_dir=deps)


def test_bootstrap_deps_rejects_commit_pin_with_trailing_newline(tmp_path: Path) -> None:
    script = repo_root() / "bin" / "bootstrap-deps"
    loader = importlib.machinery.SourceFileLoader("bootstrap_deps_under_test", str(script))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise AssertionError("bootstrap-deps failed to load")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    with pytest.raises(ValueError):
        mod._clone_at_exact_sha("https://example.invalid/repo.git", "a" * 40 + "\n", tmp_path / "dest")
