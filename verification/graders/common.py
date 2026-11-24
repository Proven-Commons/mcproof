"""Shared deterministic Tier 2 oracle utilities for the sealed mcproof-vault."""

from __future__ import annotations

import ast
from decimal import Decimal, getcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from mcproof.lean_harness import (
    COMPILE_BLOCKING_LINT_RULES,
    CandidateSandboxUnavailable,
    lint_lean4_source,
    run_confined_command,
)

getcontext().prec = 100

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = Path(os.environ.get("MCPROOF_VAULT_DIR") or (REPO_ROOT.parents[1] / "mcproof-vault"))
WORK_ROOT = VAULT_ROOT.parent
LAB_ROOT = REPO_ROOT.parent
DEPS_ROOT = Path(os.environ.get("MCPROOF_DEPS_DIR") or (LAB_ROOT / "deps"))
SILICONCORDAT_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (REPO_ROOT.parents[1] / "siliconcordat"))

STANDARD_LEAN_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
BAR_TRUST_WORDS = ("kernel", "compiler", "runtime", "hardware")
VALID_CLAIM_TIERS = frozenset({"PROVEN", "VERIFIED", "KNOWN", "CONJECTURE"})


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def strip_thinking_blocks(text: str) -> str:
    """Remove leading <think>...</think> reasoning blocks if emitted by hybrid templates."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>\s*", "", text)
    return cleaned


def find_mde_binary() -> list[str]:
    release_bin = SILICONCORDAT_ROOT / "mde" / "target" / "release" / "mde"
    debug_bin = SILICONCORDAT_ROOT / "mde" / "target" / "debug" / "mde"
    if release_bin.is_file():
        return [str(release_bin)]
    if debug_bin.is_file():
        return [str(debug_bin)]
    manifest = SILICONCORDAT_ROOT / "mde" / "Cargo.toml"
    return ["cargo", "run", "--quiet", "--manifest-path", str(manifest), "--"]


def find_lean_toolchain_bin() -> Path:
    elan_tc = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.35.0" / "bin"
    if (elan_tc / "lean").is_file():
        return elan_tc
    elan_bin = Path.home() / ".elan" / "bin"
    if (elan_bin / "lean").is_file():
        return elan_bin
    raise FileNotFoundError("Lean 4 toolchain binary not found under ~/.elan")


def _load_module_from_path(mod_name: str, file_path: Path) -> Any:
    if not file_path.is_file():
        raise FileNotFoundError(f"Required oracle dependency missing: {file_path.name}")
    spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {file_path.name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_soko_lean4_auditor() -> Any:
    return _load_module_from_path(
        "soko_lean4_auditor",
        DEPS_ROOT / "soko" / "soko_mcp" / "lean4_auditor.py",
    )


def load_soko_checker_auditor() -> Any:
    return _load_module_from_path(
        "soko_checker_auditor",
        DEPS_ROOT / "soko" / "soko_mcp" / "checker_auditor.py",
    )


def load_verdict_checker() -> Any:
    return _load_module_from_path(
        "fca_check_verdicts",
        DEPS_ROOT / "formal-claims-audit" / "scripts" / "check_verdicts.py",
    )


def extract_fenced_blocks(text: str, lang: str | None = None) -> list[str]:
    """Extract triple-backtick code blocks, optionally filtered by language prefix."""
    blocks: list[str] = []
    lines = text.splitlines()
    in_fence = False
    fence_lang = ""
    buf: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = stripped[3:].strip().lower()
                buf = []
            else:
                if lang is None or fence_lang == lang.lower() or fence_lang.startswith(lang.lower() + " "):
                    blocks.append("\n".join(buf))
                in_fence = False
                fence_lang = ""
                buf = []
            continue
        if in_fence:
            buf.append(line)
    return blocks


def extract_skip_containers(text: str) -> list[str]:
    """Extract HTML containers marked with data-eido-skip."""
    pattern = re.compile(
        r"<(?P<tag>div|section|article|aside|pre)\b[^>]*\bdata-eido-skip(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?[^>]*>"
        r"(?P<body>[\s\S]*?)</(?P=tag)>",
        re.IGNORECASE,
    )
    return [m.group(0) for m in pattern.finditer(text)]


def strip_fenced_and_skip_blocks(text: str) -> str:
    """Return prose lines outside fenced blocks and outside data-eido-skip containers."""
    without_skip = re.sub(
        r"<(?P<tag>div|section|article|aside|pre)\b[^>]*\bdata-eido-skip(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?[^>]*>"
        r"[\s\S]*?</(?P=tag)>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    out: list[str] = []
    in_fence = False
    for line in without_skip.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def parse_markdown_sections(markdown: str) -> dict[str, str]:
    """Map lowercased markdown heading titles to body text outside code fences."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in markdown.splitlines():
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


def find_section_prefix(sections: Mapping[str, str], prefix: str) -> str | None:
    target = prefix.lower()
    matched = [body for heading, body in sections.items() if heading.startswith(target)]
    if not matched:
        return None
    return "\n\n".join(matched).strip()


def check_boundary_sections(
    text: str,
    *,
    require_trust_words: bool = True,
    min_section_chars: int = 20,
) -> list[str]:
    """Verify mandatory 'What is not proved' and 'What you must trust' sections."""
    secs = parse_markdown_sections(text)
    errors: list[str] = []
    not_proved = find_section_prefix(secs, "what is not proved")
    if not_proved is None or len(not_proved.strip()) < min_section_chars:
        errors.append("missing_or_empty_section:What is not proved")
    trust = find_section_prefix(secs, "what you must trust")
    if trust is None or len(trust.strip()) < min_section_chars:
        errors.append("missing_or_empty_section:What you must trust")
    elif require_trust_words:
        lower_trust = trust.lower()
        missing_words = [w for w in BAR_TRUST_WORDS if w not in lower_trust]
        if missing_words:
            errors.append(f"missing_trust_words:{','.join(missing_words)}")
    return errors


def run_prose_guard(prose_text: str) -> dict[str, Any]:
    """Run vendored `mcproof.prose_gate` (`prose_gate.py` + `--dupes`) and `mde guard` on prose text."""
    errors: list[str] = []
    env_prose = os.environ.get("MCPROOF_CHECK_PROSE")
    check_prose_py = (
        Path(env_prose).expanduser().resolve()
        if env_prose
        else (REPO_ROOT / "src" / "mcproof" / "prose_gate.py").resolve()
    )
    with tempfile.TemporaryDirectory() as td:
        prose_file = Path(td) / "draft.md"
        prose_file.write_text(prose_text + "\n", encoding="utf-8")
        if check_prose_py.is_file():
            for extra_args, tag in (([], "prose_gate_failed"), (["--dupes"], "prose_dupes_failed")):
                cp = subprocess.run(
                    [sys.executable, str(check_prose_py), *extra_args, str(prose_file)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if cp.returncode != 0:
                    detail = (cp.stdout + "\n" + cp.stderr).strip()
                    errors.append(f"{tag}:{detail[:240]}")
        mde_cmd = [*find_mde_binary(), "guard", "--json", "--text", prose_text]
        mg = subprocess.run(mde_cmd, capture_output=True, text=True, timeout=15, check=False)
        if mg.returncode != 0:
            try:
                rep = json.loads(mg.stdout)
                for f in rep.get("findings", []):
                    errors.append(f"mde_guard:{f.get('rule')}:{f.get('message')}")
            except json.JSONDecodeError:
                errors.append(f"mde_guard_failed:{(mg.stdout + mg.stderr).strip()[:240]}")
    return {"ok": len(errors) == 0, "errors": errors}


def run_mde_code_audit_file(file_path: Path) -> list[str]:
    """Run mde guard --code-audit --json on a Python or JSON file."""
    cmd = [*find_mde_binary(), "guard", "--code-audit", "--json", str(file_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if proc.returncode == 0:
        return []
    try:
        rep = json.loads(proc.stdout)
        return [f"{f.get('rule')}:{f.get('message')}" for f in rep.get("findings", [])]
    except json.JSONDecodeError:
        return [f"mde_code_audit_error:{(proc.stdout + proc.stderr).strip()[:200]}"]


def run_lean4_verification(
    lean_source: str,
    *,
    required_checks: Sequence[Mapping[str, str]] = (),
    run_leanchecker: bool = True,
    timeout_sec: int = 45,
) -> dict[str, Any]:
    """Verify a stock-Init Lean 4 module via soko lean4_auditor, lean compiler, #print axioms, and leanchecker."""
    errors: list[str] = []
    auditor = load_soko_lean4_auditor()
    audit_rep = auditor.audit_lean4_source(lean_source, label="candidate.lean", strict_init_only=True)
    if not audit_rep.get("ok", False):
        for f in audit_rep.get("findings", []):
            errors.append(f"lean4_auditor:{f.get('code')}@{f.get('line')}:{f.get('detail')}")
        return {
            "ok": False,
            "errors": errors,
            "auditor": audit_rep,
            "axioms": {},
            "leanchecker_ran": False,
        }

    # The soko auditor does not treat `attribute [init]` as a reason to stop.
    # This lint does. The compile below is confined either way.
    lint = lint_lean4_source(lean_source, require_theorem=False, check_vacuous=False)
    for item in lint["findings"]:
        if item.get("rule") in COMPILE_BLOCKING_LINT_RULES:
            errors.append(f"lint:{item.get('rule')}:{item.get('message')}")
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "auditor": audit_rep,
            "axioms": {},
            "leanchecker_ran": False,
        }

    tc_bin = find_lean_toolchain_bin()
    lean_exe = str(tc_bin / "lean")
    checker_exe = str(tc_bin / "leanchecker")
    env = dict(os.environ)
    cur_path = env.get("PATH", "")
    env["PATH"] = f"{tc_bin}{os.pathsep}{cur_path}" if cur_path else str(tc_bin)
    libdir = subprocess.check_output([lean_exe, "--print-libdir"], text=True, env=env, timeout=15).strip()

    harness_lines: list[str] = [lean_source, "", "-- Vault deterministic signature & axiom check harness"]
    thm_names: list[str] = []
    for idx, chk in enumerate(required_checks):
        name = chk["name"]
        expected_type = chk["type"]
        thm_names.append(name)
        harness_lines.append(f"theorem _vault_sig_check_{idx} : {expected_type} := {name}")
        harness_lines.append(f"#print axioms {name}")

    combined_source = "\n".join(harness_lines) + "\n"
    axioms_by_thm: dict[str, list[str]] = {}
    leanchecker_ok = False

    with tempfile.TemporaryDirectory() as td:
        mod_path = Path(td) / "CandidateMod.lean"
        olean_path = Path(td) / "CandidateMod.olean"
        mod_path.write_text(combined_source, encoding="utf-8")

        try:
            comp = run_confined_command(
                [lean_exe, "-o", str(olean_path), str(mod_path)],
                cwd=Path(td),
                env=env,
                timeout_sec=timeout_sec,
            )
        except CandidateSandboxUnavailable as exc:
            errors.append(f"sandbox_unavailable:{exc}")
            return {
                "ok": False,
                "errors": errors,
                "auditor": audit_rep,
                "axioms": axioms_by_thm,
                "leanchecker_ran": False,
            }
        if comp.returncode != 0:
            msg = (comp.stdout + "\n" + comp.stderr).strip()
            errors.append(f"lean_compile_failed:{msg[:400]}")
            return {
                "ok": False,
                "errors": errors,
                "auditor": audit_rep,
                "axioms": axioms_by_thm,
                "leanchecker_ran": False,
            }

        # Parse `#print axioms` lines from stdout
        out_text = comp.stdout
        for name in thm_names:
            no_ax_pat = re.compile(rf"'{re.escape(name)}'\s+does not depend on any axioms")
            dep_pat = re.compile(rf"'{re.escape(name)}'\s+depends on axioms:\s*\[([^\]]*)\]")
            if no_ax_pat.search(out_text):
                axioms_by_thm[name] = []
            else:
                m = dep_pat.search(out_text)
                if m is None:
                    errors.append(f"missing_axiom_report:{name}")
                else:
                    used = [x.strip() for x in m.group(1).split(",") if x.strip()]
                    axioms_by_thm[name] = used
                    illegal = [a for a in used if a not in STANDARD_LEAN_AXIOMS]
                    if illegal:
                        errors.append(f"illegal_axioms:{name}:{','.join(illegal)}")

        if "sorryAx" in out_text:
            errors.append("illegal_axiom:sorryAx_detected")

        if not errors and run_leanchecker and Path(checker_exe).is_file():
            env_chk = dict(env)
            env_chk["LEAN_PATH"] = f"{td}{os.pathsep}{libdir}"
            try:
                chk_run = run_confined_command(
                    [checker_exe, "CandidateMod"],
                    cwd=Path(td),
                    env=env_chk,
                    timeout_sec=timeout_sec,
                )
            except CandidateSandboxUnavailable as exc:
                errors.append(f"sandbox_unavailable:{exc}")
                return {
                    "ok": False,
                    "errors": errors,
                    "auditor": audit_rep,
                    "axioms": axioms_by_thm,
                    "leanchecker_ran": False,
                }
            if chk_run.returncode != 0:
                msg = (chk_run.stdout + "\n" + chk_run.stderr).strip()
                errors.append(f"leanchecker_failed:{msg[:300]}")
            else:
                leanchecker_ok = True

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "auditor": audit_rep,
        "axioms": axioms_by_thm,
        "leanchecker_ran": leanchecker_ok,
    }


def run_dual_checker_verification(
    candidate_py: str,
    *,
    generator_py: str,
    entry_fn: str,
    valid_cases: Sequence[Any],
    corrupted_cases: Sequence[Mapping[str, Any]],
    min_kill_rate: float = 0.80,
) -> dict[str, Any]:
    """Verify an exact-math Python checker via soko checker_auditor, mde code-audit, and mutation-kill suite."""
    errors: list[str] = []
    try:
        parsed_tree = ast.parse(candidate_py)
    except SyntaxError as exc:
        return {"ok": False, "errors": [f"syntax_error:{exc}"], "kill_rate": 0.0}

    for node in ast.walk(parsed_tree):
        if isinstance(node, ast.Assert):
            errors.append(f"bare_assert_forbidden:line_{getattr(node, 'lineno', 0)}")

    auditor = load_soko_checker_auditor()
    dual_rep = auditor.audit_dual_checkers(generator_py, candidate_py, strict_exact_math=True)
    if dual_rep.get("verdict") != "PASS":
        if not dual_rep.get("distinct_alpha_skeleton", False):
            errors.append("identical_alpha_skeleton_with_generator")
        impl_findings = dual_rep.get("impl_audit", {}).get("findings", [])
        for f in impl_findings:
            errors.append(f"checker_auditor:{f.get('rule')}@{f.get('line')}")

    with tempfile.TemporaryDirectory() as td:
        cand_file = Path(td) / "candidate_checker.py"
        cand_file.write_text(candidate_py + "\n", encoding="utf-8")
        mde_errs = run_mde_code_audit_file(cand_file)
        for e in mde_errs:
            errors.append(f"mde_code_audit:{e}")

        if errors:
            return {
                "ok": False,
                "errors": errors,
                "dual_audit": dual_rep,
                "kill_rate": 0.0,
            }

        result_file = Path(td) / "eval_result.json"
        runner_code = (
            "import json, pathlib, sys\n"
            "import candidate_checker as mod\n"
            "payload = json.loads(sys.stdin.read())\n"
            "fn_name = payload['entry_fn']\n"
            "if not hasattr(mod, fn_name):\n"
            "    pathlib.Path(payload['result_path']).write_text(json.dumps({'error': f'missing_entry_fn:{fn_name}'}), encoding='utf-8')\n"
            "    raise SystemExit(2)\n"
            "fn = getattr(mod, fn_name)\n"
            "valid_results = []\n"
            "for item in payload['valid_cases']:\n"
            "    try:\n"
            "        res = fn(*item)\n"
            "        valid_results.append(res is True)\n"
            "    except Exception as exc:\n"
            "        valid_results.append(f'ERR:{type(exc).__name__}:{exc}')\n"
            "killed = []\n"
            "for mut in payload['corrupted_cases']:\n"
            "    args = mut['args']\n"
            "    try:\n"
            "        res = fn(*args)\n"
            "        killed.append(res is False)\n"
            "    except (ValueError, TypeError):\n"
            "        killed.append(True)\n"
            "    except Exception as exc:\n"
            "        killed.append(f'CRASH:{type(exc).__name__}')\n"
            "pathlib.Path(payload['result_path']).write_text(json.dumps({'valid_results': valid_results, 'killed': killed}), encoding='utf-8')\n"
        )
        runner_file = Path(td) / "run_eval.py"
        runner_file.write_text(runner_code, encoding="utf-8")

        payload = json.dumps(
            {
                "entry_fn": entry_fn,
                "valid_cases": list(valid_cases),
                "corrupted_cases": list(corrupted_cases),
                "result_path": str(result_file),
            }
        )
        proc = subprocess.run(
            [sys.executable, "-I", "-O", "-B", "-W", "error", str(runner_file)],
            cwd=td,
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0 or not result_file.is_file():
            msg = (proc.stdout + "\n" + proc.stderr).strip()
            return {
                "ok": False,
                "errors": [f"runtime_execution_failed:{msg[:300]}"],
                "dual_audit": dual_rep,
                "kill_rate": 0.0,
            }
        out = json.loads(result_file.read_text(encoding="utf-8"))

    valid_res = out["valid_results"]
    killed_res = out["killed"]
    for i, vr in enumerate(valid_res):
        if vr is not True:
            errors.append(f"valid_case_{i}_rejected:{vr}")

    crashes = [k for k in killed_res if isinstance(k, str) and k.startswith("CRASH:")]
    for c in crashes:
        errors.append(f"unhandled_mutation_exception:{c}")

    kill_count = sum(1 for k in killed_res if k is True)
    total_mut = len(corrupted_cases)
    kill_rate = (kill_count / total_mut) if total_mut > 0 else 0.0
    # Exact rational 4/5 = 80% floor when default min_kill_rate == 0.80
    below_floor = (total_mut == 0) or (
        (kill_count * 5 < total_mut * 4) if min_kill_rate == 0.80 else (kill_rate < min_kill_rate)
    )
    if below_floor:
        errors.append(f"mutation_kill_below_floor:{kill_count}/{total_mut}={kill_rate:.2f}<{min_kill_rate:.2f}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "dual_audit": dual_rep,
        "valid_passed": sum(1 for v in valid_res if v is True),
        "valid_total": len(valid_res),
        "mutations_killed": kill_count,
        "mutations_total": total_mut,
        "kill_rate": kill_rate,
    }


def sig15_decimal(x: Decimal) -> Decimal:
    if x == 0:
        return Decimal(0)
    return x.quantize(Decimal("1e" + str(x.adjusted() - 14)))


def fraction_agrees_15sig(num: int, den: int, decimal_str: str) -> bool:
    if den == 0:
        return False
    return sig15_decimal(Decimal(num) / Decimal(den)) == sig15_decimal(Decimal(decimal_str))


def fnv1a_32_hex(text: str) -> str:
    """Compute weft-eido 8-hex FNV-1a digest over whitespace-normalized UTF-16 code units."""
    norm = re.sub(r"\s+", " ", text).strip()
    h = 0x811C9DC5
    utf16_bytes = norm.encode("utf-16-le")
    for idx in range(0, len(utf16_bytes), 2):
        code_unit = int.from_bytes(utf16_bytes[idx : idx + 2], "little")
        h ^= code_unit
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"
