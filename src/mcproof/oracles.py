"""Unified deterministic Tier 2 verification runner for the Formal Verification MDE."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from .lean_harness import verify_lean4_project_comparator, verify_lean4_source
from .lineage import canonical_json_bytes, verify_lineage_manifest
from .mutation import (
    run_candidate_python_confined,
    run_checker_mutation_suite,
    run_f0_gate_and_corruptions,
    run_python_strict,
)
from .paths import check_prose_script, dep_repo, repo_root, siliconcordat_mde_root

TIER_PRECEDENCE: tuple[str, ...] = ("REFUSED", "CONJECTURE", "KNOWN", "VERIFIED", "PROVEN")
ALLOWED_CLAIM_TIERS: frozenset[str] = frozenset(TIER_PRECEDENCE)
VERDICT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SHA40_RE = re.compile(r"\b[0-9a-fA-F]{40}\b")
FENCED_BLOCK_RE = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.DOTALL)


def sanitize_verdict_id(raw_id: Any) -> str | None:
    """Validate untrusted Family C verdict IDs, rejecting separators, drive colons, and `..` on all platforms."""
    if not isinstance(raw_id, str) or not raw_id:
        return None
    if "/" in raw_id or "\\" in raw_id or ":" in raw_id or ".." in raw_id:
        return None
    vid = Path(raw_id).name
    if vid != raw_id or ".." in vid:
        return None
    if not VERDICT_ID_RE.fullmatch(vid):
        return None
    return vid


@dataclass(frozen=True)
class OracleReceipt:
    """Machine-checkable deterministic receipt matching schemas/oracle-receipt.v0.1.schema.json."""

    oracle: str
    passed: bool
    epistemic_status: str
    checks: dict[str, Any]
    findings: tuple[dict[str, Any], ...]
    receipt_sha256: str

    @classmethod
    def create(
        cls,
        *,
        oracle: str,
        passed: bool,
        epistemic_status: str,
        checks: Mapping[str, Any],
        findings: Sequence[Mapping[str, Any]],
    ) -> "OracleReceipt":
        norm_findings = tuple(
            {
                "rule": str(f.get("rule", "FINDING")),
                "message": str(f.get("message", "")),
                **({"path": str(f["path"])} if "path" in f and f["path"] is not None else {}),
                **({"line": int(f["line"])} if "line" in f and f["line"] is not None else {}),
            }
            for f in findings
        )
        checks_dict = dict(checks)
        body = {
            "schema": "mcproof-receipt/v0.1",
            "oracle": oracle,
            "passed": bool(passed),
            "epistemic_status": epistemic_status,
            "checks": checks_dict,
            "findings": list(norm_findings),
        }
        digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        return cls(
            oracle=oracle,
            passed=bool(passed),
            epistemic_status=epistemic_status,
            checks=checks_dict,
            findings=norm_findings,
            receipt_sha256=digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "mcproof-receipt/v0.1",
            "oracle": self.oracle,
            "passed": self.passed,
            "epistemic_status": self.epistemic_status,
            "checks": self.checks,
            "findings": list(self.findings),
            "receipt_sha256": self.receipt_sha256,
        }


def _load_dep_module(repo_name: str, rel_path: str, mod_alias: str) -> Any:
    full_path = dep_repo(repo_name) / rel_path
    spec = importlib.util.spec_from_file_location(mod_alias, full_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {full_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_alias] = mod
    spec.loader.exec_module(mod)
    return mod


def extract_fenced_blocks(text: str, lang_aliases: Sequence[str]) -> list[str]:
    wanted = {a.lower() for a in lang_aliases}
    blocks: list[str] = []
    for match in FENCED_BLOCK_RE.finditer(text):
        lang = match.group(1).strip().lower()
        if lang in wanted:
            blocks.append(match.group(2))
    return blocks


# 1. Lean 4 Oracle ------------------------------------------------------------

def run_lean4_oracle(
    source_or_path: str | Path,
    *,
    is_project_dir: bool = False,
    strict_init_only: bool = True,
    check_vacuous: bool = True,
    require_theorem: bool = True,
    allow_unsandboxed: bool = False,
    timeout_sec: int = 180,
) -> OracleReceipt:
    """Run Lean 4 compiler, soko lean4_auditor, Proven-Commons escape-hatch lint, WeakStatement check, and kernel axiom check."""
    if is_project_dir or (isinstance(source_or_path, Path) and source_or_path.is_dir()):
        proj = Path(source_or_path)
        res = verify_lean4_project_comparator(
            proj,
            strict_init_only=strict_init_only,
            allow_unsandboxed=allow_unsandboxed,
            timeout_sec=timeout_sec,
        )
    else:
        if isinstance(source_or_path, Path) or (
            isinstance(source_or_path, str)
            and "\n" not in source_or_path
            and Path(source_or_path).is_file()
        ):
            p = Path(source_or_path)
            src_text = p.read_text(encoding="utf-8")
            label = p.name
        else:
            src_text = str(source_or_path)
            label = "Candidate.lean"
        res = verify_lean4_source(
            src_text,
            label=label,
            strict_init_only=strict_init_only,
            check_vacuous=check_vacuous,
            require_theorem=require_theorem,
            timeout_sec=timeout_sec,
        )

    return OracleReceipt.create(
        oracle="lean4",
        passed=res.passed,
        epistemic_status="PROVEN" if res.passed else "REJECTED",
        checks=res.to_dict(),
        findings=res.findings,
    )


# 2. siliconcordat/mde Guard & Integrity Wrappers -----------------------------

def _mde_command_prefix(*, force_cargo_run: bool = False) -> list[str]:
    mde_root = siliconcordat_mde_root()
    prebuilt_release = mde_root / "target" / "release" / "mde"
    prebuilt_debug = mde_root / "target" / "debug" / "mde"
    if not force_cargo_run:
        if prebuilt_release.is_file():
            return [str(prebuilt_release)]
        if prebuilt_debug.is_file():
            return [str(prebuilt_debug)]
    return [
        "cargo",
        "run",
        "--quiet",
        "--locked",
        "--manifest-path",
        str(mde_root / "Cargo.toml"),
        "--",
    ]


def run_mde_code_audit(
    paths: Sequence[str | Path],
    *,
    force_cargo_run: bool = False,
    timeout_sec: int = 60,
) -> OracleReceipt:
    """Run `siliconcordat/mde` `guard --code-audit --json` over `.py` and `.json` paths."""
    str_paths = [str(Path(p).resolve()) for p in paths]
    cmd = [*_mde_command_prefix(force_cargo_run=force_cargo_run), "guard", "--code-audit", "--json", *str_paths]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
    findings: list[dict[str, Any]] = []
    report: dict[str, Any] = {}
    try:
        report = json.loads(proc.stdout)
        for item in report.get("findings", []):
            findings.append({
                "rule": str(item.get("rule", "MDE_CODE_AUDIT")),
                "message": str(item.get("message", "")),
                "path": str(item.get("path", "")),
                "line": int(item.get("line", 0)),
            })
        passed = bool(report.get("passed", False)) and proc.returncode == 0
    except ValueError:
        passed = False
        findings.append({
            "rule": "MDE_GUARD_EXEC_ERROR",
            "message": f"mde guard --code-audit failed (exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()[:240]}",
        })

    return OracleReceipt.create(
        oracle="mde_code_audit",
        passed=passed,
        epistemic_status="VERIFIED" if passed else "REJECTED",
        checks={
            "files_checked": report.get("files_checked", 0),
            "total_lines": report.get("total_lines", 0),
            "used_cargo_run": force_cargo_run,
        },
        findings=findings,
    )


def run_mde_integrity(
    target_root: Path,
    *,
    write: bool = False,
    manifest_name: str = "SHA256SUMS",
    allow_unlisted: bool = False,
) -> OracleReceipt:
    """Run `siliconcordat/mde` `integrity --verify` or `--write` on a directory."""
    flag = "--write" if write else "--verify"
    cmd = [
        *_mde_command_prefix(force_cargo_run=False),
        "--root",
        str(target_root.resolve()),
        "integrity",
        flag,
        "--manifest",
        manifest_name,
    ]
    if allow_unlisted and not write:
        cmd.append("--allow-unlisted")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    findings: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = {"raw_output": (proc.stdout + proc.stderr).strip()[:300]}
    passed = proc.returncode == 0
    if not passed:
        findings.append({
            "rule": "MDE_INTEGRITY_MISMATCH",
            "message": f"mde integrity {flag} failed: {json.dumps(payload)[:260]}",
        })
    return OracleReceipt.create(
        oracle="mde_integrity",
        passed=passed,
        epistemic_status="VERIFIED" if passed else "REJECTED",
        checks=payload,
        findings=findings,
    )


# 3. Exact-Math Dual-Oracle Checker & Mutation Suite --------------------------

def run_checker_oracle(
    checker_source: str,
    *,
    generator_or_spec_source: str | None = None,
    entry_fn: str = "verify",
    valid_cases: Sequence[Mapping[str, Any]] = (),
    planted_mutations: Sequence[Mapping[str, Any]] | None = None,
    strict_exact_math: bool = True,
    force_cargo_run: bool = False,
) -> OracleReceipt:
    """Audit a Python exact-math checker with soko checker_auditor, mde guard --code-audit, python3 -O -B -W error, and >= 80% mutation kill floor."""
    checker_mod = _load_dep_module("soko", "soko_mcp/checker_auditor.py", "soko_checker_auditor")
    findings: list[dict[str, Any]] = []

    try:
        dual_rep = checker_mod.audit_dual_checkers(
            spec_source=generator_or_spec_source if generator_or_spec_source else checker_source,
            impl_source=checker_source if generator_or_spec_source else None,
            strict_exact_math=strict_exact_math,
        )
    except SyntaxError as exc:
        return OracleReceipt.create(
            oracle="exact_checker",
            passed=False,
            epistemic_status="REJECTED",
            checks={"syntax_error": str(exc)},
            findings=[{"rule": "PYTHON_SYNTAX_ERROR", "line": exc.lineno or 1, "message": str(exc)}],
        )

    if generator_or_spec_source:
        impl_audit = dual_rep.get("impl_audit", {})
        for f in impl_audit.get("findings", []):
            findings.append({
                "rule": str(f["rule"]),
                "line": int(f.get("line", 0)),
                "message": str(f["detail"]),
            })
        if not dual_rep.get("distinct_alpha_skeleton", False):
            findings.append({
                "rule": "IDENTICAL_ALPHA_SKELETON",
                "line": 1,
                "message": "verifier shares an identical alpha-normalized AST skeleton with the generator/spec",
            })
    else:
        spec_audit = dual_rep.get("spec_audit", {})
        for f in spec_audit.get("findings", []):
            findings.append({
                "rule": str(f["rule"]),
                "line": int(f.get("line", 0)),
                "message": str(f["detail"]),
            })

    # Explicitly scan for `float(` calls in exact-math checkers (in addition to float literals & `/`)
    if strict_exact_math and re.search(r"\bfloat\s*\(", checker_source):
        findings.append({
            "rule": "FLOAT_COERCION_CALL",
            "line": 1,
            "message": "explicit float(...) coercion forbidden in exact int/Fraction checker",
        })

    with tempfile.TemporaryDirectory(prefix="mcproof_chk_") as tmp_str:
        tmp_py = Path(tmp_str) / "checker.py"
        tmp_py.write_text(checker_source, encoding="utf-8")
        mde_rep = run_mde_code_audit([tmp_py], force_cargo_run=force_cargo_run)
        for f in mde_rep.findings:
            findings.append({
                "rule": f["rule"],
                "line": f.get("line", 0),
                "message": f["message"],
            })

        # Verify module imports cleanly under confined `python3 -I -O -B -W error`
        smoke_proc, _, _ = run_candidate_python_confined(
            ["-c", "import runpy, sys; runpy.run_path(sys.argv[1])", str(tmp_py)],
            writable_dir=Path(tmp_str),
            timeout_sec=30,
            sandbox_mode="auto",
        )
        strict_import_ok = smoke_proc is not None and smoke_proc.returncode == 0
        if not strict_import_ok:
            err_msg = "" if smoke_proc is None else (smoke_proc.stderr or smoke_proc.stdout).strip()[:240]
            findings.append({
                "rule": "STRICT_PYTHON_IMPORT_ERROR",
                "message": f"failed under `python3 -I -O -B -W error`: {err_msg}",
            })

    mut_dict: dict[str, Any] | None = None
    if valid_cases:
        mut_rep = run_checker_mutation_suite(
            checker_source,
            entry_fn=entry_fn,
            valid_cases=valid_cases,
            planted_mutations=planted_mutations,
        )
        mut_dict = mut_rep.to_dict()
        mut_passed = mut_rep.passed
        findings.extend(mut_rep.findings)
    else:
        findings.append({
            "rule": "MISSING_VALID_CASES",
            "message": "mutation kill floor cannot be evaluated without valid_cases fixtures",
        })
        mut_passed = False

    passed = (
        dual_rep.get("verdict") == "PASS"
        and mde_rep.passed
        and strict_import_ok
        and mut_passed
        and len(findings) == 0
    )
    return OracleReceipt.create(
        oracle="exact_checker",
        passed=passed,
        epistemic_status="VERIFIED" if passed else "REJECTED",
        checks={
            "soko_checker_audit": dual_rep,
            "mde_code_audit_passed": mde_rep.passed,
            "strict_python_import_ok": strict_import_ok,
            "mutation_suite": mut_dict,
        },
        findings=findings,
    )


# 4. Mission Bar, Foundation-0 Gate, Verdicts, and Soko Integrity -------------

def run_mission_bar_oracle(
    project_dir: Path | None = None,
    *,
    no_lean: bool = True,
    offline: bool = True,
    run_tests: bool = False,
) -> OracleReceipt:
    """Run Proven-Commons `mission/bar/check.py` against a library repo."""
    target = (project_dir or (repo_root() / "lean")).resolve()
    check_script = dep_repo("mission") / "bar" / "check.py"

    with tempfile.TemporaryDirectory(prefix="mcproof_bar_") as tmp_str:
        out_json = Path(tmp_str) / "bar_report.json"
        args = [str(check_script), str(target), "--json", str(out_json)]
        if no_lean:
            args.append("--no-lean")
        if offline:
            args.append("--offline")
        if run_tests:
            args.append("--run-tests")
        proc = run_python_strict(args, cwd=target, timeout_sec=180)
        findings: list[dict[str, Any]] = []
        data: dict[str, Any] = {}
        if out_json.is_file():
            data = json.loads(out_json.read_text(encoding="utf-8"))
            for row in data.get("items", []):
                if row.get("status") == "FAIL":
                    findings.append({
                        "rule": f"BAR_ITEM_{row.get('item')}_FAIL",
                        "message": f"{row.get('title')}: {row.get('detail')}",
                    })
        else:
            findings.append({
                "rule": "BAR_PROJECT_ERROR",
                "message": (proc.stderr or proc.stdout).strip()[:260],
            })

    passed = proc.returncode == 0 and len(findings) == 0
    items = data.get("items", [])
    all_pass = bool(items) and all(r.get("status") == "PASS" for r in items)
    status = "VERIFIED" if (passed and all_pass and data.get("status") == "verified") else (
        "IN_PROGRESS" if passed else "REJECTED"
    )
    return OracleReceipt.create(
        oracle="mission_bar",
        passed=passed,
        epistemic_status=status,
        checks=data,
        findings=findings,
    )


def run_f0_gate_oracle(f0_root: Path | None = None) -> OracleReceipt:
    """Run Foundation-0 `scripts/gate.py` + `tests/run_gate_corruptions.py` under `python3 -O -B -W error`."""
    rep = run_f0_gate_and_corruptions(f0_root)
    return OracleReceipt.create(
        oracle="f0_gate",
        passed=rep.passed,
        epistemic_status="VERIFIED" if rep.passed else "REJECTED",
        checks=rep.to_dict(),
        findings=rep.findings,
    )


def run_verdicts_oracle(verdicts_path: Path | None = None) -> OracleReceipt:
    """Run Foundation-0 `formal-claims-audit/scripts/check_verdicts.py` under `python3 -O -B -W error`."""
    script = dep_repo("formal-claims-audit") / "scripts" / "check_verdicts.py"
    target = (verdicts_path or (dep_repo("formal-claims-audit") / "verdicts")).resolve()

    with tempfile.TemporaryDirectory(prefix="mcproof_verdicts_") as tmp_str:
        if target.is_file():
            check_dir = Path(tmp_str)
            (check_dir / target.name).write_bytes(target.read_bytes())
        else:
            check_dir = target

        proc = run_python_strict([str(script), str(check_dir)], timeout_sec=30)

    passed = proc.returncode == 0
    findings: list[dict[str, Any]] = []
    if not passed:
        for line in (proc.stderr or proc.stdout).splitlines():
            if line.strip():
                findings.append({"rule": "INVALID_VERDICT_RECORD", "message": line.strip()})

    return OracleReceipt.create(
        oracle="formal_claims_verdicts",
        passed=passed,
        epistemic_status="VERIFIED" if passed else "REJECTED",
        checks={"stdout": proc.stdout.strip(), "target": target.name},
        findings=findings,
    )


def run_soko_integrity_and_evidence_oracle() -> OracleReceipt:
    """Verify soko `SHA256SUMS` integrity manifest and `evidence.py` canonical boundary checks."""
    soko_root = dep_repo("soko")
    int_mod = _load_dep_module("soko", "soko_mcp/integrity.py", "soko_integrity")
    ev_mod = _load_dep_module("soko", "soko_mcp/evidence.py", "soko_evidence")

    int_res = int_mod.verify_source_manifest(soko_root, soko_root / "SHA256SUMS")
    findings: list[dict[str, Any]] = []
    if not int_res.get("source_integrity_verified", False):
        findings.append({
            "rule": "SOKO_MANIFEST_DRIFT",
            "message": f"soko SHA256SUMS verification failed: {int_res}",
        })

    # Exercise canonical starting-room validation (rejects vacuous all-wall grid, accepts valid room)
    vacuous_rejected = False
    try:
        ev_mod.validate_room(1, ["###", "###"])
    except ValueError:
        vacuous_rejected = True
    if not vacuous_rejected:
        findings.append({
            "rule": "SOKO_EVIDENCE_VACUOUS_ROOM_ACCEPTED",
            "message": "validate_room accepted a vacuous hero-free room",
        })

    ident = ev_mod.problem_identity(1, ["####", "#FG#", "####"])
    passed = len(findings) == 0
    return OracleReceipt.create(
        oracle="soko_integrity_evidence",
        passed=passed,
        epistemic_status="VERIFIED" if passed else "REJECTED",
        checks={
            "soko_manifest_sha256": int_res.get("manifest_sha256"),
            "files_verified": int_res.get("files_verified", 0),
            "vacuous_room_rejected": vacuous_rejected,
            "sample_instance_sha256": ident["instance_sha256"],
        },
        findings=findings,
    )


# 5. Claim-Tier Hygiene & Mixed-Register Zone Oracles -------------------------

def _extract_markdown_sections(markdown_text: str) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence:
            m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if m:
                current = m.group(2).strip().lower()
                found.setdefault(current, [])
                continue
        if current is not None:
            found[current].append(line)
    return {k: "\n".join(v).strip() for k, v in found.items()}


def run_claim_hygiene_oracle(
    markdown_text: str,
    *,
    expected_tier: str | None = None,
    has_kernel_proof: bool = False,
) -> OracleReceipt:
    """Enforce mandatory `What is not proved` & `What you must trust` sections and honest claim-tier labels."""
    secs = _extract_markdown_sections(markdown_text)
    findings: list[dict[str, Any]] = []

    not_proved_body = next((v for k, v in secs.items() if k.startswith("what is not proved")), None)
    trust_body = next((v for k, v in secs.items() if k.startswith("what you must trust")), None)

    if not not_proved_body or len(not_proved_body.strip()) < 15:
        findings.append({
            "rule": "MISSING_WHAT_IS_NOT_PROVED",
            "message": "formal claim document lacks a substantive 'What is not proved' boundary section",
        })
    elif re.fullmatch(r"(?i)\s*[-*]?\s*(none|nothing|n/a|everything is proved)\.?\s*", not_proved_body):
        findings.append({
            "rule": "VACUOUS_WHAT_IS_NOT_PROVED",
            "message": "'What is not proved' claims nothing sits outside the proof",
        })

    if not trust_body or len(trust_body.strip()) < 15:
        findings.append({
            "rule": "MISSING_WHAT_YOU_MUST_TRUST",
            "message": "formal claim document lacks a substantive 'What you must trust' TCB section",
        })
    else:
        trust_lower = trust_body.lower()
        required_roots = ("kernel", "compiler", "runtime", "hardware")
        if not any(w in trust_lower for w in required_roots) and "python" not in trust_lower:
            findings.append({
                "rule": "INCOMPLETE_TRUST_BOUNDARY",
                "message": "'What you must trust' must name concrete TCB components (kernel, compiler, runtime, hardware, or interpreter)",
            })

    # Extract explicit Claim tier / Status header or badge
    tier_match = re.search(
        r"(?im)^[ \t>*_-]*(?:claim[ \t-]*tier|epistemic[ \t-]*status|tier|label)[*_ \t]*:[*_ \t]*`?([A-Z_-]+)`?",
        markdown_text,
    )
    declared_tier = tier_match.group(1).upper() if tier_match else None
    if declared_tier is None:
        # Deterministic least-inflationary precedence across processes and PYTHONHASHSEED values
        found_tiers = [t for t in TIER_PRECEDENCE if re.search(rf"\b{t}\b", markdown_text)]
        if len(found_tiers) == 1:
            declared_tier = found_tiers[0]
        elif not found_tiers:
            findings.append({
                "rule": "MISSING_CLAIM_TIER_LABEL",
                "message": f"document must declare an explicit claim tier from {list(TIER_PRECEDENCE)}",
            })
        else:
            declared_tier = found_tiers[0]

    if declared_tier is not None and declared_tier not in ALLOWED_CLAIM_TIERS:
        findings.append({
            "rule": "INVALID_CLAIM_TIER_VOCABULARY",
            "message": f"tier {declared_tier!r} is not in canonical vocabulary {sorted(ALLOWED_CLAIM_TIERS)}",
        })

    # Detect tier inflation: claiming PROVEN on finite checks, bounded testing, conjectures, or without kernel proof
    lower_text = markdown_text.lower()
    finite_only_signals = (
        "finite check" in lower_text
        or "tested up to n =" in lower_text
        or "sampled" in lower_text
        or "monte carlo" in lower_text
        or "bounded search" in lower_text
        or "no formal proof" in lower_text
    )
    if declared_tier == "PROVEN" and not has_kernel_proof and finite_only_signals:
        findings.append({
            "rule": "CLAIM_TIER_INFLATION",
            "message": "document claims PROVEN while describing finite/sampled/unproved evidence (must be VERIFIED or CONJECTURE)",
        })

    if re.search(r"(?i)\bzero[- ]trust assumptions\b|\bno trust assumptions\b|\bnothing to trust\b", markdown_text):
        findings.append({
            "rule": "HIDDEN_TRUST_BYPASS",
            "message": "document falsely claims zero trust assumptions",
        })

    if expected_tier is not None and declared_tier != expected_tier.upper():
        findings.append({
            "rule": "EXPECTED_TIER_MISMATCH",
            "message": f"declared tier {declared_tier!r} != expected tier {expected_tier.upper()!r}",
        })

    passed = len(findings) == 0
    status = declared_tier if (passed and declared_tier in {"PROVEN", "VERIFIED", "KNOWN", "CONJECTURE"}) else (
        "VERIFIED" if passed else "REJECTED"
    )
    return OracleReceipt.create(
        oracle="claim_hygiene",
        passed=passed,
        epistemic_status=status,
        checks={
            "declared_tier": declared_tier,
            "expected_tier": expected_tier,
            "has_what_is_not_proved": bool(not_proved_body),
            "has_what_you_must_trust": bool(trust_body),
        },
        findings=findings,
    )


def _strip_data_eido_skip_regions(raw_text: str) -> str:
    """Blank out `<div data-eido-skip>...</div>` regions while preserving exact line count for prose checks."""
    pattern = re.compile(r"<([a-zA-Z0-9]+)\b[^>]*\bdata-eido-skip\b[^>]*>.*?</\1>", re.DOTALL)

    def _repl(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")

    return pattern.sub(_repl, raw_text)


def run_prose_and_mixed_zone_oracle(
    markdown_text: str,
    *,
    label: str = "document.md",
    require_formal_sections: bool = False,
    require_data_eido_skip: bool = False,
    verify_embedded_lean: bool = True,
    verify_verdict_shas: bool = False,
    prose_script_override: str | Path | None = None,
) -> OracleReceipt:
    """Check prose gates (`prose_gate.py` + `--dupes`) alongside mixed-zone formal block protections."""
    prose_script = check_prose_script(prose_script_override)
    findings: list[dict[str, Any]] = []

    prose_view = _strip_data_eido_skip_regions(markdown_text)
    with tempfile.TemporaryDirectory(prefix="mcproof_prose_") as tmp_str:
        doc_path = Path(tmp_str) / (Path(label).name or "document.md")
        doc_path.write_text(prose_view, encoding="utf-8")

        p_check = subprocess.run(
            [sys.executable, str(prose_script), str(doc_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if p_check.returncode != 0:
            before_p = len(findings)
            for ln in (p_check.stdout or "").splitlines():
                if ln.startswith("  "):
                    findings.append({"rule": "PROSE_GATE_VIOLATION", "message": ln.strip()})
            if len(findings) == before_p:
                findings.append({
                    "rule": "PROSE_GATE_VIOLATION",
                    "message": ((p_check.stdout or "") + "\n" + (p_check.stderr or "")).strip()[:240],
                })

        d_check = subprocess.run(
            [sys.executable, str(prose_script), "--dupes", str(doc_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if d_check.returncode != 0:
            before_d = len(findings)
            for ln in (d_check.stdout or "").splitlines():
                if ln.startswith("  "):
                    findings.append({"rule": "PROSE_DUPES_VIOLATION", "message": ln.strip()})
            if len(findings) == before_d:
                findings.append({
                    "rule": "PROSE_DUPES_VIOLATION",
                    "message": ((d_check.stdout or "") + "\n" + (d_check.stderr or "")).strip()[:240],
                })

    # Strip fenced blocks and inline backticks before checking outcome forecasts (matches mde guard & check-prose.py)
    stripped_prose_lines: list[str] = []
    in_fence = False
    for raw_ln in prose_view.splitlines():
        if raw_ln.lstrip().startswith("```"):
            in_fence = not in_fence
            stripped_prose_lines.append("")
            continue
        stripped_prose_lines.append("" if in_fence else re.sub(r"`[^`]*`", "", raw_ln))
    stripped_prose = "\n".join(stripped_prose_lines)

    for forecast_pat in (
        r"(?i)\bafter this lands\b",
        r"(?i)\bonce this ships\b",
        r"(?i)\bwhen this merges\b",
        r"(?i)\bif this lands\b",
        r"(?i)\bshould be closed\b",
        r"(?i)\bready to merge\b",
    ):
        for fm in re.finditer(forecast_pat, stripped_prose):
            findings.append({
                "rule": "OUTCOME_FORECAST_PHRASE",
                "message": f"banned outcome forecast or close directive: {fm.group(0)!r}",
            })

    if require_data_eido_skip and "data-eido-skip" not in markdown_text:
        findings.append({
            "rule": "MISSING_DATA_EIDO_SKIP",
            "message": "mixed-register formal document omits mandatory `data-eido-skip` protection marker",
        })

    if verify_verdict_shas and not SHA40_RE.search(markdown_text):
        findings.append({
            "rule": "MISSING_40CHAR_VERDICT_SHA",
            "message": "mixed-register verdict reference lacks a full 40-character commit SHA",
        })

    lean_blocks = extract_fenced_blocks(markdown_text, ("lean", "lean4"))
    lean_results: list[dict[str, Any]] = []
    has_proved_lean = False
    if verify_embedded_lean and lean_blocks:
        for idx, blk in enumerate(lean_blocks):
            l_rec = run_lean4_oracle(blk, strict_init_only=True, check_vacuous=True, require_theorem=True)
            lean_results.append(l_rec.checks)
            if not l_rec.passed:
                for lf in l_rec.findings:
                    findings.append({
                        "rule": f"EMBEDDED_LEAN_{lf['rule']}",
                        "message": f"lean block #{idx + 1}: {lf['message']}",
                    })
            else:
                has_proved_lean = True

    if require_formal_sections:
        hyg = run_claim_hygiene_oracle(markdown_text, has_kernel_proof=has_proved_lean)
        findings.extend(hyg.findings)

    passed = len(findings) == 0
    return OracleReceipt.create(
        oracle="prose_and_mixed_zone",
        passed=passed,
        epistemic_status="PROVEN" if (passed and has_proved_lean) else ("VERIFIED" if passed else "REJECTED"),
        checks={
            "lean_blocks_checked": len(lean_blocks),
            "data_eido_skip_present": "data-eido-skip" in markdown_text,
            "sha40_present": bool(SHA40_RE.search(markdown_text)),
        },
        findings=findings,
    )


# 6. Unified Family A / B / C / D Completion Grader ---------------------------

def grade_family_completion(
    family: str,
    completion_text: str,
    *,
    expected_tier: str | None = None,
    generator_source: str | None = None,
    valid_cases: Sequence[Mapping[str, Any]] = (),
    planted_mutations: Sequence[Mapping[str, Any]] | None = None,
    strict_init_only: bool = True,
) -> OracleReceipt:
    """Deterministic Tier 2 grader for Family A, B, C, and D model completions."""
    fam = family.strip().upper()

    if fam == "A":
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        lean_src = "\n\n".join(lean_blocks) if lean_blocks else completion_text
        return run_lean4_oracle(
            lean_src,
            strict_init_only=strict_init_only,
            check_vacuous=True,
            require_theorem=True,
        )

    if fam == "B":
        if not valid_cases:
            return OracleReceipt.create(
                oracle="family_b_checker",
                passed=False,
                epistemic_status="REJECTED",
                checks={"valid_cases_total": 0, "mutation_suite": None},
                findings=[{
                    "rule": "MISSING_VALID_CASES",
                    "message": "Family B requires fixture valid_cases for the >=80% mutation kill-floor evaluation",
                }],
            )
        py_blocks = extract_fenced_blocks(completion_text, ("python", "py"))
        py_src = py_blocks[-1] if py_blocks else completion_text
        gen_src = generator_source
        if gen_src is None and len(py_blocks) >= 2:
            gen_src = py_blocks[0]
            py_src = py_blocks[1]
        return run_checker_oracle(
            py_src,
            generator_or_spec_source=gen_src,
            valid_cases=valid_cases,
            planted_mutations=planted_mutations,
            strict_exact_math=True,
        )

    if fam == "C":
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        has_valid_lean = False
        extra_findings: list[dict[str, Any]] = []
        if lean_blocks:
            l_res = run_lean4_oracle("\n\n".join(lean_blocks), strict_init_only=strict_init_only)
            has_valid_lean = l_res.passed
            if not l_res.passed:
                extra_findings.extend(l_res.findings)

        json_blocks = extract_fenced_blocks(completion_text, ("json",))
        for jb in json_blocks:
            try:
                parsed = json.loads(jb)
                if isinstance(parsed, dict) and "verdict" in parsed and "source_commit" in parsed:
                    raw_id = parsed.get("id", "verdict_01")
                    vid = sanitize_verdict_id(raw_id)
                    if vid is None:
                        extra_findings.append({
                            "rule": "INVALID_VERDICT_ID",
                            "message": f"unsafe verdict id {raw_id!r}",
                        })
                        continue
                    with tempfile.TemporaryDirectory(prefix="mcproof_famc_") as td:
                        td_resolved = Path(td).resolve()
                        vf = (td_resolved / f"{vid}.json").resolve()
                        if not vf.is_relative_to(td_resolved) or vf.parent != td_resolved:
                            extra_findings.append({
                                "rule": "INVALID_VERDICT_ID",
                                "message": f"verdict path escaped temp directory for id {raw_id!r}",
                            })
                            continue
                        vf.write_text(jb, encoding="utf-8")
                        v_rep = run_verdicts_oracle(vf)
                        if not v_rep.passed:
                            extra_findings.extend(v_rep.findings)
            except ValueError as exc:
                extra_findings.append({"rule": "INVALID_JSON_BLOCK", "message": str(exc)})

        hyg = run_claim_hygiene_oracle(
            completion_text,
            expected_tier=expected_tier,
            has_kernel_proof=has_valid_lean,
        )
        all_findings = [*hyg.findings, *extra_findings]
        passed = len(all_findings) == 0
        return OracleReceipt.create(
            oracle="family_c_claims",
            passed=passed,
            epistemic_status=hyg.epistemic_status if passed else "REJECTED",
            checks={**hyg.checks, "lean_blocks_checked": len(lean_blocks)},
            findings=all_findings,
        )

    if fam == "D":
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        if not lean_blocks:
            return OracleReceipt.create(
                oracle="family_d_mixed",
                passed=False,
                epistemic_status="REJECTED",
                checks={"lean_blocks_checked": 0},
                findings=[{"rule": "MISSING_EMBEDDED_LEAN_BLOCK", "message": "Family D response must include a fenced Lean 4 block"}],
            )
        mixed = run_prose_and_mixed_zone_oracle(
            completion_text,
            require_formal_sections=True,
            require_data_eido_skip=True,
            verify_embedded_lean=True,
            verify_verdict_shas=True,
        )
        if expected_tier is not None:
            hyg = run_claim_hygiene_oracle(
                completion_text,
                expected_tier=expected_tier,
                has_kernel_proof=mixed.passed,
            )
            if not hyg.passed:
                combined = [*mixed.findings, *hyg.findings]
                return OracleReceipt.create(
                    oracle="family_d_mixed",
                    passed=False,
                    epistemic_status="REJECTED",
                    checks=mixed.checks,
                    findings=combined,
                )
        return mixed

    raise ValueError(f"unsupported prompt family {family!r} (expected A, B, C, or D)")


# 7. Full Reference Selftest --------------------------------------------------

def run_all_reference_selftests(*, allow_unsandboxed: bool = False) -> OracleReceipt:
    """Verify all pinned Tier 2 oracles and Plane 1 lineage end to end."""
    sub_results: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []

    lineage_rep = verify_lineage_manifest()
    sub_results["lineage"] = lineage_rep.to_dict()
    if not lineage_rep.passed:
        for msg in lineage_rep.findings:
            findings.append({"rule": "LINEAGE_DRIFT", "message": msg})

    soko_rep = run_soko_integrity_and_evidence_oracle()
    sub_results["soko"] = soko_rep.to_dict()
    findings.extend(soko_rep.findings)

    bar_rep = run_mission_bar_oracle(repo_root() / "lean", no_lean=True, offline=True)
    sub_results["mission_bar"] = bar_rep.to_dict()
    findings.extend(bar_rep.findings)

    f0_rep = run_f0_gate_oracle()
    sub_results["f0_gate"] = f0_rep.to_dict()
    findings.extend(f0_rep.findings)

    verdicts_rep = run_verdicts_oracle()
    sub_results["formal_claims_audit"] = verdicts_rep.to_dict()
    findings.extend(verdicts_rep.findings)

    fsp_proc = run_python_strict([str(dep_repo("finite-state-proofs") / "verify.py")])
    fsp_ok = fsp_proc.returncode == 0
    sub_results["finite_state_proofs"] = {"passed": fsp_ok, "stdout": fsp_proc.stdout.strip()}
    if not fsp_ok:
        findings.append({"rule": "FINITE_STATE_PROOFS_FAIL", "message": fsp_proc.stderr.strip()})

    mde_rep = run_mde_code_audit([repo_root() / "src", repo_root() / "schemas", repo_root() / "lean" / "tests"])
    sub_results["mde_code_audit"] = mde_rep.to_dict()
    findings.extend(mde_rep.findings)

    lean_rep = run_lean4_oracle(repo_root() / "lean", is_project_dir=True, allow_unsandboxed=allow_unsandboxed)
    sub_results["lean_comparator_paranoid"] = lean_rep.to_dict()
    findings.extend(lean_rep.findings)

    passed = len(findings) == 0
    return OracleReceipt.create(
        oracle="selftest_all",
        passed=passed,
        epistemic_status="VERIFIED" if passed else "REJECTED",
        checks=sub_results,
        findings=findings,
    )
