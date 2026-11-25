"""Pluggable domain-general `DomainOracle` protocol, budget ledger, and certificate auditor.

Defines the clean domain boundary for `Proven-Commons/mcproof` (`mde:formal-verification`):
1. `DomainOracle` (`typing.Protocol`): pluggable interface implemented by domain-general mathematical
   and coding verifiers (`FormalVerificationDomainOracle`) as well as external specialist MDEs in
   separate repositories without introducing domain-specific game or application code into `mcproof`.
2. `BudgetLedger`: exact integer accounting for turns, tokens, transition steps, and sandbox calls.
3. `run_restricted_sandbox_cell`: 4.0-second, network-free, filesystem-isolated Python micro-computation
   sandbox usable by any `DomainOracle` closed-loop repair runner.
4. `audit_transition_certificate`, `verify_dual_product_parity`, and `audit_portfolio_bounds`:
   deterministic soundness checkers enforcing non-tautological `must_fail_controls` (`A6`), rejecting
   `LINT_PASS` / `LOWER_BOUND` tier-swap promotions (`A7`), requiring a KNOWN `citation`
   (`source`, `reference`, `artifact_sha256`), and catching all 8 abstract certificate
   unsoundness classes (`F-01` through `F-08`).
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable
import unicodedata

from .repair_loop import (
    MAX_RETRIEVAL_TOKENS_HARD_CAP,
    default_inference_oracle,
    format_diagnostics,
    retrieve_plane1_excerpt,
    sanitize_oracle_diagnostics,
)

MAX_SANDBOX_TIMEOUT_SEC = 4.0
MAX_CERT_ABS_INT = 10**60
STRICT_RATIONAL_RE = re.compile(r"^-?[0-9]+(?:/[1-9][0-9]*)?$")
SHA256_64_RE = re.compile(r"^[0-9a-f]{64}$")
# Blank-looking filler / ignorable codepoints whose Unicode category is Lo/So/Mn/Cf
# (e.g. Braille Pattern Blank U+2800, Hangul Filler U+3164, Halfwidth Hangul Filler U+FFA0).
_CITATION_INVISIBLE_CHARS = frozenset(
    "\u034f\u115f\u1160\u17b4\u17b5\u180e\u200b\u200c\u200d\u2060\u2800\u3164\ufeff\uffa0"
)
_INVISIBLE_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Cs", "Mn", "Zl", "Zp", "Zs"})
NON_VERIFIED_SUBTIERS: frozenset[str] = frozenset(
    {
        "LINT_PASS",
        "LOWER_BOUND",
        "LOWER_BOUND_UNWITNESSED",
        "VERIFIED_ON_BOUNDED_REACHABLE_SUBGRAPH",
        "CONJECTURE",
        "UNVERIFIED_CALLER_BOUNDS",
    }
)
RECOGNIZED_CERT_STATUSES: frozenset[str] = NON_VERIFIED_SUBTIERS | frozenset(
    {"VERIFIED", "PROVEN", "REJECTED", "KNOWN", "REFUSED", "IN_PROGRESS"}
)

ALLOWLISTED_SANDBOX_MODULES: frozenset[str] = frozenset(
    {
        "__future__",
        "bisect",
        "collections",
        "copy",
        "dataclasses",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "hashlib",
        "heapq",
        "itertools",
        "json",
        "math",
        "numbers",
        "operator",
        "re",
        "statistics",
        "string",
        "typing",
    }
)

FORBIDDEN_SANDBOX_BUILTINS: frozenset[str] = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)

FORBIDDEN_SANDBOX_DUNDERS: frozenset[str] = frozenset(
    {
        "__bases__",
        "__builtins__",
        "__code__",
        "__dict__",
        "__globals__",
        "__loader__",
        "__mro__",
        "__spec__",
        "__subclasses__",
        "ag_frame",
        "cr_frame",
        "f_back",
        "f_builtins",
        "f_code",
        "f_globals",
        "f_locals",
        "gi_frame",
        "tb_frame",
    }
)

FORBIDDEN_SANDBOX_MODULE_HOPS: frozenset[str] = frozenset(
    {
        "_builtins",
        "_frozen_importlib",
        "_imp",
        "_io",
        "_os",
        "_posixsubprocess",
        "_sys",
        "builtins",
        "codecs",
        "importlib",
        "io",
        "modules",
        "nt",
        "open",
        "os",
        "pathlib",
        "posix",
        "shutil",
        "socket",
        "subprocess",
        "sys",
    }
)


@dataclass(frozen=True)
class DomainDiagnostic:
    """Sanitized, label-free diagnostic emitted by a deterministic Tier 2 `DomainOracle`."""

    rule: str
    message: str
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"rule": self.rule, "message": self.message}
        if self.line is not None:
            out["line"] = self.line
        return out


@dataclass(frozen=True)
class DomainGradeResult:
    """Deterministic Tier 2 verification verdict for a candidate completion or witness."""

    passed: bool
    epistemic_status: str
    diagnostics: tuple[DomainDiagnostic, ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "epistemic_status": self.epistemic_status,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "metrics": dict(self.metrics),
        }


@dataclass
class BudgetLedger:
    """Exact integer budget accounting for closed-loop formal synthesis and state-space exploration."""

    max_turns: int = 4
    max_tokens: int = 16384
    max_steps: int = 10000
    max_sandbox_calls: int = 4
    turns_used: int = 0
    tokens_used: int = 0
    steps_used: int = 0
    sandbox_calls_used: int = 0
    format_errors: int = 0

    def exhausted(self) -> bool:
        return (
            self.turns_used >= self.max_turns
            or self.tokens_used >= self.max_tokens
            or self.steps_used >= self.max_steps
        )

    def utilization_ratio(self) -> Fraction:
        if self.max_turns <= 0:
            return Fraction(1, 1)
        return Fraction(self.turns_used, self.max_turns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_turns": self.max_turns,
            "max_tokens": self.max_tokens,
            "max_steps": self.max_steps,
            "max_sandbox_calls": self.max_sandbox_calls,
            "turns_used": self.turns_used,
            "tokens_used": self.tokens_used,
            "steps_used": self.steps_used,
            "sandbox_calls_used": self.sandbox_calls_used,
            "format_errors": self.format_errors,
            "budget_exhausted": self.exhausted(),
        }


@runtime_checkable
class DomainOracle(Protocol):
    """Pluggable domain-general interface for Plane 1 retrieval and Tier 2 closed-loop repair."""

    @property
    def domain_id(self) -> str: ...

    def retrieve_plane1_context(
        self,
        task: Mapping[str, Any],
        prior_diagnostics: Sequence[DomainDiagnostic] = (),
        max_tokens: int = 1250,
    ) -> str: ...

    def grade_candidate(
        self,
        task: Mapping[str, Any],
        candidate: str,
    ) -> DomainGradeResult: ...

    def format_repair_feedback(
        self,
        task: Mapping[str, Any],
        grade: DomainGradeResult,
    ) -> str: ...


class FormalVerificationDomainOracle:
    """Label-free inference-time `DomainOracle` for `mcproof` Families A, B, C, and D."""

    def __init__(self, *, spec_path: Path | None = None) -> None:
        self._spec_path = spec_path

    @property
    def domain_id(self) -> str:
        return "mde:formal-verification"

    def retrieve_plane1_context(
        self,
        task: Mapping[str, Any],
        prior_diagnostics: Sequence[DomainDiagnostic] = (),
        max_tokens: int = 1250,
    ) -> str:
        capped = min(max(250, int(max_tokens)), MAX_RETRIEVAL_TOKENS_HARD_CAP)
        fam = str(task.get("family", "A")).strip().upper()
        prompt_text = str(task.get("prompt", ""))
        findings_dicts = [d.to_dict() for d in prior_diagnostics]
        res = retrieve_plane1_excerpt(
            family=fam,
            prompt_text=prompt_text,
            prior_findings=findings_dicts,
            max_tokens=capped,
            spec_path=self._spec_path,
        )
        return str(res["excerpt"])

    def grade_candidate(
        self,
        task: Mapping[str, Any],
        candidate: str,
    ) -> DomainGradeResult:
        fam = str(task.get("family", "A")).strip().upper()
        public_view = {"id": task.get("id", ""), "family": fam, "prompt": task.get("prompt", "")}
        raw = default_inference_oracle(public_view, candidate)
        sanitized = sanitize_oracle_diagnostics(fam, raw.get("findings", ()))
        diags = tuple(
            DomainDiagnostic(
                rule=d["rule"],
                message=d["diagnostic"],
                line=int(d["line"]) if "line" in d else None,
            )
            for d in sanitized
        )
        return DomainGradeResult(
            passed=bool(raw["passed"]),
            epistemic_status=str(raw["epistemic_status"]),
            diagnostics=diags,
            metrics={"raw_finding_count": len(raw.get("findings", ()))},
        )

    def format_repair_feedback(
        self,
        task: Mapping[str, Any],
        grade: DomainGradeResult,
    ) -> str:
        fam = str(task.get("family", "A")).strip().upper()
        return format_diagnostics(
            [d.to_dict() for d in grade.diagnostics],
            family=fam,
        )


def audit_sandbox_cell_ast(
    code: str,
    *,
    extra_forbidden_modules: Sequence[str] = (),
    strict_exact_math: bool = False,
) -> list[str]:
    """Static AST check enforcing pure-stdlib module allowlist, zero I/O, and optional exact-math checks."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"SyntaxError: line {exc.lineno}: {exc.msg}"]

    extra_forb = {str(m).split(".")[0] for m in extra_forbidden_modules}
    allowed_mods = ALLOWLISTED_SANDBOX_MODULES - extra_forb
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in allowed_mods:
                    violations.append(f"forbidden_import:{top}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if (node.level or 0) > 0 or top not in allowed_mods:
                violations.append(f"forbidden_from_import:{node.module or '.'}")
            else:
                for alias in node.names:
                    imp_name = alias.name
                    if imp_name == "*" or imp_name.startswith("_") or imp_name in FORBIDDEN_SANDBOX_MODULE_HOPS:
                        violations.append(f"forbidden_from_import_symbol:{imp_name}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_SANDBOX_DUNDERS or node.attr == "__class__" or (
                node.attr.startswith("__") and node.attr.endswith("__")
            ):
                violations.append(f"forbidden_dunder_attr:{node.attr}")
            elif node.attr in FORBIDDEN_SANDBOX_MODULE_HOPS or node.attr in (
                "system",
                "popen",
                "urlopen",
                "urlretrieve",
                "write_text",
                "write_bytes",
            ):
                violations.append(f"forbidden_attr_call:{node.attr}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_SANDBOX_BUILTINS:
            violations.append(f"forbidden_builtin:{node.id}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_SANDBOX_BUILTINS:
                    violations.append(f"forbidden_builtin:{node.func.id}")
                elif strict_exact_math and node.func.id == "float":
                    violations.append("forbidden_float_coercion:float")
                elif strict_exact_math and node.func.id == "pow" and len(node.args) == 2:
                    exp_arg = node.args[1]
                    if (isinstance(exp_arg, ast.Constant) and type(exp_arg.value) is int and exp_arg.value < 0) or (
                        isinstance(exp_arg, ast.UnaryOp) and isinstance(exp_arg.op, ast.USub)
                    ):
                        violations.append("forbidden_negative_pow:pow")
        elif strict_exact_math and isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Div):
                violations.append("forbidden_float_div:/")
            elif isinstance(node.op, ast.Pow):
                if (isinstance(node.right, ast.Constant) and type(node.right.value) is int and node.right.value < 0) or (
                    isinstance(node.right, ast.UnaryOp) and isinstance(node.right.op, ast.USub)
                ):
                    violations.append("forbidden_negative_pow:**")
        elif strict_exact_math and isinstance(node, ast.Constant) and isinstance(node.value, float):
            violations.append(f"forbidden_float_literal:{node.value!r}")
    return violations


def run_restricted_sandbox_cell(
    code: str,
    *,
    timeout_sec: float = MAX_SANDBOX_TIMEOUT_SEC,
    injected_globals: Mapping[str, int | str | bool | list[Any] | dict[str, Any]] | None = None,
    extra_forbidden_modules: Sequence[str] = (),
    strict_exact_math: bool = False,
) -> dict[str, Any]:
    """Execute a pure-algorithmic Python micro-computation cell under a hard <= 4.0s wall-clock cap."""
    capped_timeout = min(max(0.1, float(timeout_sec)), MAX_SANDBOX_TIMEOUT_SEC)
    ast_violations = audit_sandbox_cell_ast(
        code,
        extra_forbidden_modules=extra_forbidden_modules,
        strict_exact_math=strict_exact_math,
    )
    if ast_violations:
        return {
            "ok": False,
            "returncode": 2,
            "timed_out": False,
            "ast_rejected": True,
            "violations": ast_violations,
            "timeout_sec": capped_timeout,
            "stdout": "",
            "stderr": "; ".join(ast_violations),
        }

    extra_forb = {str(m).split(".")[0] for m in extra_forbidden_modules}
    allowed_sorted = sorted(ALLOWLISTED_SANDBOX_MODULES - extra_forb)
    preimport_mods = [m for m in allowed_sorted if m != "__future__"]
    preamble_lines: list[str] = []
    if injected_globals:
        for key in sorted(injected_globals.keys(), key=repr):
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key):
                return {
                    "ok": False,
                    "returncode": 2,
                    "timed_out": False,
                    "ast_rejected": True,
                    "violations": [f"invalid_injected_global_key:{key!r}"],
                    "timeout_sec": capped_timeout,
                    "stdout": "",
                    "stderr": f"invalid injected_globals key {key!r}",
                }
            preamble_lines.append(f"_ns[{key!r}] = {injected_globals[key]!r}")

    with tempfile.TemporaryDirectory(prefix="mcproof_sandbox_") as tmp_dir:
        if os.name != "nt":
            os.chmod(tmp_dir, 0o700)
        code_hex = code.encode("utf-8").hex()
        driver_src = (
            "import " + ", ".join(preimport_mods) + "\n"
            "import builtins as _b\n"
            f"_ALLOWLIST = frozenset({allowed_sorted!r})\n"
            "_orig_import = _b.__import__\n"
            "_orig_compile = _b.compile\n"
            "_orig_exec = _b.exec\n"
            "def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):\n"
            "    if level and level > 0:\n"
            "        raise ImportError('relative imports are forbidden in sandbox')\n"
            "    top = str(name).split('.')[0]\n"
            "    if top not in _ALLOWLIST:\n"
            "        raise ImportError(f'module {top!r} is not in sandbox allowlist')\n"
            "    return _orig_import(name, globals, locals, fromlist, level)\n"
            "_safe_b = dict(_b.__dict__)\n"
            "_safe_b['__import__'] = _guarded_import\n"
            "for _k in ('open', 'input', 'breakpoint', 'eval', 'exec', 'compile'):\n"
            "    _safe_b.pop(_k, None)\n"
            "_ns = {'__name__': '__main__', '__builtins__': _safe_b}\n"
            + ("\n".join(preamble_lines) + "\n" if preamble_lines else "")
            + f"_src = bytes.fromhex({code_hex!r}).decode('utf-8')\n"
            "_co = _orig_compile(_src, '<sandbox_cell>', 'exec')\n"
            "import sys as _sys\n"
            "_sys.addaudithook(lambda ev, _a: (_ for _ in ()).throw(PermissionError(ev)) "
            "if ev in ('open','os.system','os.mkdir','os.remove','os.unlink','os.rmdir','os.rename') "
            "or ev.startswith(('subprocess.','socket.')) else None)\n"
            "del _sys\n"
            "_orig_exec(_co, _ns, _ns)\n"
        )
        driver_path = Path(tmp_dir) / "cell_driver.py"
        driver_path.write_text(driver_src, encoding="utf-8", newline="\n")

        clean_env: dict[str, str] = {
            "PATH": os.environ.get("PATH", "") if os.name == "nt" else "/usr/bin:/bin",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        if os.name == "nt":
            for win_key in ("SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
                if win_key in os.environ:
                    clean_env[win_key] = os.environ[win_key]
        proc = subprocess.Popen(
            [sys.executable, "-I", "-B", "-O", str(driver_path)],
            cwd=tmp_dir,
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name != "nt"),
        )
        try:
            out, err = proc.communicate(timeout=capped_timeout)
            return {
                "ok": proc.returncode == 0,
                "returncode": int(proc.returncode),
                "timed_out": False,
                "ast_rejected": False,
                "violations": [],
                "timeout_sec": capped_timeout,
                "stdout": out[:8000],
                "stderr": err[:2000],
            }
        except subprocess.TimeoutExpired:
            kill_err: str | None = None
            try:
                if hasattr(os, "killpg") and hasattr(signal, "SIGKILL"):
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except OSError as exc:
                kill_err = str(exc)
            out, err = proc.communicate()
            return {
                "ok": False,
                "returncode": -9,
                "timed_out": True,
                "ast_rejected": False,
                "violations": ["sandbox_timeout_exceeded_4s"],
                "timeout_sec": capped_timeout,
                "stdout": (out or "")[:4000],
                "stderr": f"TimeoutExpired: cell exceeded {capped_timeout:.1f}s limit"
                + (f" ({kill_err})" if kill_err else ""),
            }


def verify_dual_product_parity(
    *,
    spec_init: Any,
    impl_init: Any,
    spec_actions: Callable[[Any], Sequence[Any]],
    impl_actions: Callable[[Any], Sequence[Any]],
    spec_step: Callable[[Any, Any], Any],
    impl_step: Callable[[Any, Any], Any],
    spec_invariant: Callable[[Any], bool],
    impl_invariant: Callable[[Any], bool],
    spec_is_goal: Callable[[Any], bool],
    impl_is_goal: Callable[[Any], bool],
    spec_obs: Callable[[Any], Any],
    impl_obs: Callable[[Any], Any],
    max_product_states: int = 10000,
) -> dict[str, Any]:
    """Product-graph `(s_spec, u_impl)` verifier closing `F-06` coarse-observation & collapsed-spec bugs."""
    visited: set[tuple[Any, Any]] = {(spec_init, impl_init)}
    queue: deque[tuple[Any, Any]] = deque([(spec_init, impl_init)])
    mismatches: list[dict[str, str]] = []

    while queue:
        s_state, u_state = queue.popleft()
        if spec_obs(s_state) != impl_obs(u_state):
            mismatches.append({"rule": "F06_OBSERVATION_DIVERGENCE", "message": f"obs({s_state!r}) != obs({u_state!r})"})
            break
        s_inv = bool(spec_invariant(s_state))
        u_inv = bool(impl_invariant(u_state))
        if s_inv != u_inv or not u_inv:
            mismatches.append(
                {
                    "rule": "F06_IMPL_INVARIANT_VIOLATION_OR_DIVERGENCE",
                    "message": f"spec.invariant={s_inv}, impl.invariant={u_inv} at product state",
                }
            )
            break
        if bool(spec_is_goal(s_state)) != bool(impl_is_goal(u_state)):
            mismatches.append({"rule": "F06_GOAL_PARITY_MISMATCH", "message": "spec.is_goal != impl.is_goal"})
            break
        s_acts = sorted(spec_actions(s_state), key=repr)
        u_acts = sorted(impl_actions(u_state), key=repr)
        if s_acts != u_acts:
            mismatches.append({"rule": "F06_ACTION_SET_MISMATCH", "message": "spec.actions != impl.actions"})
            break
        for act in s_acts:
            nxt = (spec_step(s_state, act), impl_step(u_state, act))
            if nxt not in visited:
                if len(visited) >= max_product_states:
                    return {
                        "passed": False,
                        "complete_space": False,
                        "epistemic_status": "REJECTED_INCOMPLETE_PRODUCT_SPACE",
                        "states_checked": len(visited),
                        "findings": [
                            {
                                "rule": "F05_INCOMPLETE_PRODUCT_GRAPH",
                                "message": f"product BFS truncated at max_product_states={max_product_states}",
                            }
                        ],
                    }
                visited.add(nxt)
                queue.append(nxt)

    passed = len(mismatches) == 0
    return {
        "passed": passed,
        "complete_space": True,
        "epistemic_status": "PROVEN" if passed else "REJECTED_DIFFERENTIAL_MISMATCH",
        "states_checked": len(visited),
        "findings": mismatches,
    }


def audit_portfolio_bounds(
    items: Sequence[Mapping[str, Any]],
    *,
    registered_verified_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Audit portfolio lower/upper bound records, closing `F-07` caller-bound inflation and bound inversions."""
    findings: list[dict[str, str]] = []
    triaged: list[dict[str, Any]] = []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or len(items) == 0:
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "items": [],
            "findings": [{"rule": "CERT_PORTFOLIO_EMPTY", "message": "Portfolio bounds list must be a non-empty sequence."}],
        }
    for idx, row in enumerate(items):
        if not isinstance(row, Mapping):
            findings.append(_type_finding(f"items[{idx}]", "an object", row))
            triaged.append({"id": f"item_{idx}", "epistemic_status": "REJECTED", "caller_bounds_verified": False})
            continue
        iid = str(row.get("id", "unknown"))
        p_floor = row.get("proven_floor")
        s_known = row.get("shortest_known")
        l_rec = row.get("live_record")
        raw_row_status = row.get("epistemic_status")
        row_bad_type = False
        for bname, bval in (("proven_floor", p_floor), ("shortest_known", s_known), ("live_record", l_rec)):
            if bval is not None and not _is_count(bval):
                findings.append(_type_finding(f"{iid}.{bname}", "a non-negative integer", bval))
                row_bad_type = True
        if raw_row_status is not None and not isinstance(raw_row_status, str):
            findings.append(_type_finding(f"{iid}.epistemic_status", "a string", raw_row_status))
            row_bad_type = True
        if row_bad_type:
            status = "REJECTED_INVALID_BOUND_TYPE"
        elif p_floor is not None and s_known is not None and p_floor > s_known:
            findings.append(
                {
                    "rule": "CERT_F07_INCONSISTENT_PORTFOLIO_BOUNDS",
                    "message": f"{iid}: proven_floor ({p_floor}) > shortest_known ({s_known})",
                }
            )
            status = "REJECTED_INCONSISTENT_PORTFOLIO_BOUNDS"
        elif s_known is not None and l_rec is not None and s_known > l_rec:
            findings.append(
                {
                    "rule": "CERT_F07_INCONSISTENT_PORTFOLIO_BOUNDS",
                    "message": f"{iid}: shortest_known ({s_known}) > live_record ({l_rec})",
                }
            )
            status = "REJECTED_INCONSISTENT_PORTFOLIO_BOUNDS"
        elif p_floor is not None and l_rec is not None and p_floor > l_rec:
            findings.append(
                {
                    "rule": "CERT_F07_INCONSISTENT_PORTFOLIO_BOUNDS",
                    "message": f"{iid}: proven_floor ({p_floor}) > live_record ({l_rec})",
                }
            )
            status = "REJECTED_INCONSISTENT_PORTFOLIO_BOUNDS"
        elif iid not in registered_verified_ids:
            if isinstance(raw_row_status, str) and raw_row_status.strip().upper() in ("VERIFIED", "PROVEN"):
                findings.append(
                    {
                        "rule": "CERT_F07_UNVERIFIED_CALLER_BOUNDS",
                        "message": f"{iid}: caller-supplied bounds lack registered proof/witness certificates",
                    }
                )
            status = "UNVERIFIED_CALLER_BOUNDS"
        else:
            status = "VERIFIED"
        triaged.append({"id": iid, "epistemic_status": status, "caller_bounds_verified": iid in registered_verified_ids})

    passed = len(findings) == 0
    return {
        "passed": passed,
        "epistemic_status": "VERIFIED" if passed else "REJECTED",
        "items": triaged,
        "findings": findings,
    }


def _citation_text_visible(value: str) -> bool:
    """True when `value` contains at least one visible, non-blank, non-format character."""
    return any(
        ch.isprintable()
        and not ch.isspace()
        and ch not in _CITATION_INVISIBLE_CHARS
        and unicodedata.category(ch) not in _INVISIBLE_UNICODE_CATEGORIES
        for ch in value
    )


def _witness_value_valid(value: Any, *, _depth: int = 0) -> bool:
    """True iff `value` is a non-empty, non-blank exact witness element (no bool/float/None/empty containers)."""
    if _depth > 16:
        return False
    if value is None or type(value) is bool or isinstance(value, float):
        return False
    if type(value) is int:
        return True
    if isinstance(value, str):
        return _citation_text_visible(value)
    if isinstance(value, list):
        return len(value) > 0 and all(_witness_value_valid(elem, _depth=_depth + 1) for elem in value)
    if isinstance(value, Mapping):
        return len(value) > 0 and all(
            isinstance(k, str) and _citation_text_visible(k) and _witness_value_valid(v, _depth=_depth + 1)
            for k, v in value.items()
        )
    return False


def _known_citation_findings(cert: Mapping[str, Any]) -> list[dict[str, str]]:
    """Require a KNOWN citation. Proof digests and `tcb_pins` are not one.

    `cert["citation"]` is `{"source", "reference", "artifact_sha256"}`.
    `source` and `reference` need at least one printable, non-invisible character.
    `artifact_sha256` matches `^[0-9a-f]{64}$` and is not 64 zeros.
    A REJECTED or REFUSED prior plus a valid citation is intended to promote to KNOWN.
    """
    citation = cert.get("citation")
    if not isinstance(citation, Mapping):
        return [
            {
                "rule": "CERT_KNOWN_CITATION_MISSING",
                "message": (
                    "KNOWN requires citation.source, citation.reference, and "
                    "citation.artifact_sha256. witness_or_proof_sha256 and tcb_pins are not a citation."
                ),
            }
        ]
    findings: list[dict[str, str]] = []
    for key in ("source", "reference"):
        if key not in citation or citation.get(key) is None:
            findings.append(
                {
                    "rule": "CERT_KNOWN_CITATION_MISSING",
                    "message": f"KNOWN citation.{key} is absent.",
                }
            )
            continue
        value = citation.get(key)
        if not isinstance(value, str):
            findings.append(
                {
                    "rule": "CERT_KNOWN_CITATION_MALFORMED",
                    "message": f"KNOWN citation.{key} must be a non-empty string.",
                }
            )
        elif not _citation_text_visible(value):
            findings.append(
                {
                    "rule": "CERT_KNOWN_CITATION_MISSING",
                    "message": f"KNOWN citation.{key} is blank or has no visible character.",
                }
            )
    if "artifact_sha256" not in citation or citation.get("artifact_sha256") is None:
        findings.append(
            {
                "rule": "CERT_KNOWN_CITATION_MISSING",
                "message": "KNOWN citation.artifact_sha256 is absent.",
            }
        )
    else:
        digest = citation.get("artifact_sha256")
        if not isinstance(digest, str) or not digest.strip():
            findings.append(
                {
                    "rule": "CERT_KNOWN_CITATION_MISSING" if isinstance(digest, str) else "CERT_KNOWN_CITATION_MALFORMED",
                    "message": (
                        "KNOWN citation.artifact_sha256 is blank."
                        if isinstance(digest, str)
                        else "KNOWN citation.artifact_sha256 must match ^[0-9a-f]{64}$."
                    ),
                }
            )
        elif not SHA256_64_RE.fullmatch(digest) or digest == "0" * 64:
            findings.append(
                {
                    "rule": "CERT_KNOWN_CITATION_MALFORMED",
                    "message": (
                        "KNOWN citation.artifact_sha256 must match ^[0-9a-f]{64}$ "
                        f"and must not be 64 zeros (got {digest!r})."
                    ),
                }
            )
    return findings


_CERT_FLAG_FIELDS: tuple[str, ...] = (
    "includes_hidden_state",
    "caller_bounds_verified",
    "differential_match",
    "unverified_caller_claim",
    "valid_winning_witness",
    "valid_winning_route",
    "truncated_by_budget",
    "exact_optimum_reached",
    "complete_space",
    "complete_domain_closed",
    "impl_invariant_checked",
    "impl_goal_parity_checked",
    "obs_projection_injective",
)
_CERT_COUNT_FIELDS: tuple[str, ...] = (
    "step_consistency_violations",
    "open_transitions",
    "proven_floor",
)
# These two may be null, which means the same as leaving the key out.
_CERT_OPTIONAL_COUNT_FIELDS: tuple[str, ...] = ("max_bound", "witness_cost", "certified_lower_bound")
_CERT_TEXT_FIELDS: tuple[str, ...] = (
    "epistemic_status",
    "prior_status",
    "evidence_kind",
    "proof_mode",
    "state_hash_mode",
    "certificate_kind",
    "witness_or_proof_sha256",
    "instance_sha256",
    "canonical_instance_sha256",
)
_CERT_ORACLE_LIST_FIELDS: tuple[str, ...] = ("oracles_checked", "engines_verified", "checkers_executed")
_CERT_CONTROL_FLAG_FIELDS: tuple[str, ...] = ("oracle_invoked", "unexpectedly_passed", "seed_equals_target")


def _type_finding(path: str, expected: str, value: Any) -> dict[str, str]:
    shown = repr(value)
    if len(shown) > 40:
        shown = shown[:37] + "..."
    return {
        "rule": "CERT_FIELD_TYPE_INVALID",
        "message": f"{path} must be {expected} (got {type(value).__name__} {shown}).",
    }


def _is_count(value: Any) -> bool:
    """True for a non-negative `int`. A `bool` is not a count."""
    return type(value) is int and value >= 0


def _certificate_type_findings(cert: Mapping[str, Any]) -> list[dict[str, str]]:
    """Check the type of every field the auditor reads, before any value is compared.

    The value checks test `is False`, truthiness or `int()`. A flag written as the
    string "false" or as 0, or a count written as a negative number, slips past them.
    """
    findings: list[dict[str, str]] = []
    for key in _CERT_FLAG_FIELDS:
        if key in cert and type(cert[key]) is not bool:
            findings.append(_type_finding(key, "a boolean", cert[key]))
    for key in _CERT_COUNT_FIELDS:
        if key in cert and not _is_count(cert[key]):
            findings.append(_type_finding(key, "a non-negative integer", cert[key]))
    for key in _CERT_OPTIONAL_COUNT_FIELDS:
        if cert.get(key) is not None and not _is_count(cert[key]):
            findings.append(_type_finding(key, "a non-negative integer or null", cert[key]))
    for key in _CERT_TEXT_FIELDS:
        if key in cert and not isinstance(cert[key], str):
            findings.append(_type_finding(key, "a string", cert[key]))
    if "tcb_pins" in cert:
        pins = cert["tcb_pins"]
        if not isinstance(pins, Mapping):
            findings.append(_type_finding("tcb_pins", "an object", pins))
        else:
            if "tcb_manifest_verified" in pins and type(pins["tcb_manifest_verified"]) is not bool:
                findings.append(_type_finding("tcb_pins.tcb_manifest_verified", "a boolean", pins["tcb_manifest_verified"]))
            for key in ("checker_sha256", "checker_auditor_py_sha256"):
                if pins.get(key) is not None and not isinstance(pins[key], str):
                    findings.append(_type_finding(f"tcb_pins.{key}", "a string", pins[key]))
    if "must_fail_controls" in cert:
        controls = cert["must_fail_controls"]
        if not isinstance(controls, list):
            findings.append(_type_finding("must_fail_controls", "a list of strings", controls))
        else:
            for idx, name in enumerate(controls):
                if not isinstance(name, str):
                    findings.append(_type_finding(f"must_fail_controls[{idx}]", "a string", name))
    if "control_records" in cert:
        records = cert["control_records"]
        if not isinstance(records, list):
            findings.append(_type_finding("control_records", "a list of objects", records))
        else:
            for idx, rec in enumerate(records):
                if not isinstance(rec, Mapping):
                    findings.append(_type_finding(f"control_records[{idx}]", "an object", rec))
                    continue
                if "name" in rec and (not isinstance(rec["name"], str) or not _citation_text_visible(rec["name"])):
                    findings.append(_type_finding(f"control_records[{idx}].name", "a non-empty string", rec["name"]))
                for key in _CERT_CONTROL_FLAG_FIELDS:
                    if key in rec and type(rec[key]) is not bool:
                        findings.append(_type_finding(f"control_records[{idx}].{key}", "a boolean", rec[key]))
    for okey in _CERT_ORACLE_LIST_FIELDS:
        if okey in cert:
            olist = cert[okey]
            if not isinstance(olist, list):
                findings.append(_type_finding(okey, "a list of non-empty strings", olist))
            else:
                for idx, entry in enumerate(olist):
                    if not isinstance(entry, str) or not _citation_text_visible(entry):
                        findings.append(_type_finding(f"{okey}[{idx}]", "a non-empty string", entry))
    for wkey in ("witness", "winning_witness"):
        if wkey in cert and cert[wkey] is not None:
            wval = cert[wkey]
            if not isinstance(wval, (str, list)):
                findings.append(_type_finding(wkey, "a string, list, or null", wval))
            elif isinstance(wval, list):
                for idx, elem in enumerate(wval):
                    if not _witness_value_valid(elem):
                        findings.append(_type_finding(f"{wkey}[{idx}]", "a non-blank exact step value", elem))
    return findings


def audit_transition_certificate(
    cert: Mapping[str, Any],
    *,
    require_must_fail_controls: bool = False,
    registered_artifact_digests: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Domain-general fail-closed auditor covering `F-01..F-08` plus `A6`/`A7` and KNOWN citations.

    A KNOWN certificate carries `citation`: `source` and `reference` are non-empty
    strings, and `artifact_sha256` is a lowercase 64-hex digest of the cited artifact.
    """
    if not isinstance(cert, Mapping):
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "finding_count": 1,
            "findings": [
                {
                    "rule": "CERT_NOT_AN_OBJECT",
                    "message": f"Certificate must be a JSON object (got {type(cert).__name__}).",
                }
            ],
        }
    findings: list[dict[str, str]] = _certificate_type_findings(cert)
    status = str(cert.get("epistemic_status", "")).strip().upper()
    proof_mode = str(cert.get("proof_mode", "")).strip().lower()

    # An omitted or invented status has no checks to fail, so it must not pass.
    if not status:
        findings.append(
            {
                "rule": "CERT_STATUS_ABSENT",
                "message": "Certificate omits epistemic_status.",
            }
        )
    elif status not in RECOGNIZED_CERT_STATUSES:
        findings.append(
            {
                "rule": "CERT_STATUS_UNKNOWN",
                "message": f"epistemic_status {status!r} is not a recognized certificate status.",
            }
        )
    prior_status = str(cert.get("prior_status", "")).strip().upper()
    evidence_kind = str(cert.get("evidence_kind", "")).strip().lower()

    # A7: Reject tier-swap promotions of LINT_PASS / LOWER_BOUND / bounded-subgraph
    # to VERIFIED, PROVEN, or KNOWN. A citation does not make a lower prior legal.
    if status in ("VERIFIED", "PROVEN", "KNOWN"):
        if prior_status in NON_VERIFIED_SUBTIERS or evidence_kind in ("static_lint", "lower_bound_only", "bounded_subgraph"):
            findings.append(
                {
                    "rule": "CERT_A7_ILLEGAL_TIER_SWAP",
                    "message": f"Cannot promote {prior_status or evidence_kind} to {status} without full replayed witness/proof.",
                }
            )
        if cert.get("valid_winning_witness") is False or cert.get("valid_winning_route") is False:
            findings.append(
                {
                    "rule": "CERT_A7_ILLEGAL_TIER_SWAP",
                    "message": f"Rejected witness cannot carry epistemic_status={status}.",
                }
            )

    if status == "KNOWN":
        findings.extend(_known_citation_findings(cert))

    # A6: Non-empty, distinct, non-tautological must_fail_controls
    if require_must_fail_controls or "must_fail_controls" in cert or "control_records" in cert:
        controls = cert.get("must_fail_controls")
        if not isinstance(controls, list) or len(controls) == 0:
            findings.append(
                {
                    "rule": "CERT_A6_MISSING_OR_DUPLICATE_CONTROLS",
                    "message": "Certificate must include a non-empty must_fail_controls list.",
                }
            )
        else:
            clean_names = [c.strip() for c in controls if isinstance(c, str) and _citation_text_visible(c)]
            if len(clean_names) != len(controls) or len(set(clean_names)) != len(clean_names):
                findings.append(
                    {
                        "rule": "CERT_A6_MISSING_OR_DUPLICATE_CONTROLS",
                        "message": "must_fail_controls contains empty or duplicate control identifiers.",
                    }
                )
        seen_control_names: set[str] = set()
        raw_crecs = cert.get("control_records")
        for crec in (raw_crecs if isinstance(raw_crecs, list) else []):
            if not isinstance(crec, Mapping):
                continue
            raw_cname = crec.get("name")
            cname = raw_cname.strip() if isinstance(raw_cname, str) and _citation_text_visible(raw_cname) else "unnamed_control"
            if isinstance(raw_cname, str) and _citation_text_visible(raw_cname):
                seen_control_names.add(cname)
            if crec.get("unexpectedly_passed") is True:
                findings.append(
                    {
                        "rule": "CERT_A6_CONTROL_PASSED",
                        "message": f"Negative control {cname!r} unexpectedly passed.",
                    }
                )
            if (
                crec.get("oracle_invoked") is False
                or crec.get("seed_equals_target") is True
                or ("oracle_invoked" not in crec)
                or ("unexpectedly_passed" not in crec)
            ):
                findings.append(
                    {
                        "rule": "CERT_A6_TAUTOLOGICAL_CONTROL",
                        "message": f"Negative control {cname!r} is tautological or omits oracle_invoked/unexpectedly_passed.",
                    }
                )
        if isinstance(controls, list) and len(controls) > 0:
            expected_cnames = {c.strip() for c in controls if isinstance(c, str) and _citation_text_visible(c)}
            missing_cnames = sorted(expected_cnames - seen_control_names)
            if missing_cnames:
                findings.append(
                    {
                        "rule": "CERT_A6_CONTROL_COVERAGE_INCOMPLETE",
                        "message": f"control_records omits must_fail_controls entries: {missing_cnames}.",
                    }
                )

    # F-01: Optimistic differential boolean without >=2 distinct independent replay engines
    if cert.get("differential_match") is True:
        present_okeys = [okey for okey in _CERT_ORACLE_LIST_FIELDS if okey in cert]
        if not present_okeys or any(
            not isinstance(cert[okey], list)
            or len({e.strip() for e in cert[okey] if isinstance(e, str) and _citation_text_visible(e)}) < 2
            for okey in present_okeys
        ):
            findings.append(
                {
                    "rule": "CERT_SINGLE_ORACLE_DIFFERENTIAL",
                    "message": "differential_match=True requires >=2 distinct independent verification engines.",
                }
            )

    # F-02: Partial-projection state hash missing hidden state bits
    if cert.get("includes_hidden_state") is False or str(cert.get("state_hash_mode", "")).strip().lower() in ("observable_projection_only", "ascii_only", "rendered_board_only"):
        findings.append(
            {
                "rule": "CERT_PARTIAL_STATE_PROJECTION",
                "message": "State digest omits hidden transition state; full canonical state commitment required.",
            }
        )

    # F-03: Unpinned TCB manifest or missing 64-hex checker/auditor SHA-256 (fail closed when omitted, NEON-D5)
    pins = cert.get("tcb_pins")
    if status in ("VERIFIED", "PROVEN", "LOWER_BOUND"):
        if not isinstance(pins, Mapping):
            findings.append(
                {
                    "rule": "CERT_TCB_MANIFEST_UNLOCKED",
                    "message": "Certified record omits mandatory tcb_pins manifest commitment.",
                }
            )
        else:
            present_chk_keys = [k for k in ("checker_sha256", "checker_auditor_py_sha256") if k in pins]
            chk_valid = bool(present_chk_keys) and all(
                isinstance(pins[k], str) and bool(SHA256_64_RE.fullmatch(pins[k])) and pins[k] != "0" * 64
                for k in present_chk_keys
            )
            if pins.get("tcb_manifest_verified") is not True or not chk_valid:
                findings.append(
                    {
                        "rule": "CERT_TCB_MANIFEST_UNLOCKED",
                        "message": "TCB pins must verify SHA256SUMS and bind non-zero 64-hex checker/auditor SHA-256(s).",
                    }
                )

    # NEON-D2: Truncated search budget cannot claim exact optimum or PROVEN status
    if cert.get("truncated_by_budget") is True and (
        status == "PROVEN"
        or str(cert.get("certificate_kind", "")).strip().upper() == "EXACT_DIJKSTRA_OPTIMUM"
        or cert.get("exact_optimum_reached") is True
    ):
        findings.append(
            {
                "rule": "CERT_TRUNCATED_SEARCH_BUDGET",
                "message": "Search truncated by budget cannot claim PROVEN or EXACT_DIJKSTRA_OPTIMUM.",
            }
        )

    # F-04: Unwitnessed or mismatched-length `proven_floor` claimed as `VERIFIED`.
    # A certificate that says `exact_optimum_reached: false`, or that carries a witness
    # key with no witness in it, fails whether or not `proven_floor` is present.
    p_floor = cert.get("proven_floor") if _is_count(cert.get("proven_floor")) else None
    max_b = cert.get("max_bound") if _is_count(cert.get("max_bound")) else None
    if p_floor is not None and max_b is not None and p_floor > max_b:
        findings.append(
            {
                "rule": "CERT_FLOOR_EXCEEDS_MAX_BOUND",
                "message": f"proven_floor ({p_floor}) exceeds search max_bound ({max_b}).",
            }
        )
    if status in ("VERIFIED", "PROVEN"):
        present_wkeys = [wk for wk in ("witness", "winning_witness") if wk in cert]
        witness_claimed = "proven_floor" in cert or bool(present_wkeys)
        valid_witnesses = [
            cert[wk]
            for wk in present_wkeys
            if isinstance(cert[wk], (str, list)) and _witness_value_valid(cert[wk])
        ]
        all_present_nonempty = bool(present_wkeys) and len(valid_witnesses) == len(present_wkeys)
        if cert.get("exact_optimum_reached") is False or (witness_claimed and not all_present_nonempty):
            findings.append(
                {
                    "rule": "CERT_UNWITNESSED_VERIFIED_OPTIMUM",
                    "message": "Unwitnessed lower bound must carry status LOWER_BOUND_UNWITNESSED, never VERIFIED/PROVEN.",
                }
            )
        elif p_floor is not None:
            witness_cost = cert.get("witness_cost")
            if witness_cost is not None:
                if _is_count(witness_cost) and witness_cost != p_floor:
                    findings.append(
                        {
                            "rule": "CERT_WITNESS_FLOOR_MISMATCH",
                            "message": f"Witness cost {witness_cost} != claimed proven_floor {p_floor}.",
                        }
                    )
            else:
                for wval in valid_witnesses:
                    if len(wval) != p_floor:
                        findings.append(
                            {
                                "rule": "CERT_WITNESS_FLOOR_MISMATCH",
                                "message": f"Witness cost {len(wval)} != claimed proven_floor {p_floor}.",
                            }
                        )
                        break

    # Instance digest format & mismatch checks (fail closed on blank/newline/all-zero)
    for ikey in ("instance_sha256", "canonical_instance_sha256"):
        if ikey in cert and isinstance(cert[ikey], str):
            ival = cert[ikey]
            if not SHA256_64_RE.fullmatch(ival) or ival == "0" * 64:
                findings.append(
                    {
                        "rule": "CERT_INSTANCE_DIGEST_MALFORMED",
                        "message": f"{ikey} must be a non-zero lowercase 64-hex SHA-256 digest.",
                    }
                )
    if "instance_sha256" in cert and "canonical_instance_sha256" in cert:
        if cert.get("instance_sha256") != cert.get("canonical_instance_sha256"):
            findings.append(
                {
                    "rule": "CERT_INSTANCE_DIGEST_MISMATCH",
                    "message": "Certificate instance_sha256 does not match canonical target instance.",
                }
            )
    if _is_count(cert.get("step_consistency_violations")) and cert["step_consistency_violations"] > 0:
        findings.append(
            {
                "rule": "CERT_STEP_INCONSISTENCY",
                "message": "Layered search lower bound is invalid when step_consistency_violations > 0.",
            }
        )

    # F-05: Truncated inductive potential on incomplete concrete state graph
    incomplete_graph = (
        cert.get("complete_space") is False
        or cert.get("complete_domain_closed") is False
        or (_is_count(cert.get("open_transitions")) and cert["open_transitions"] > 0)
    )
    if (
        proof_mode == "inductive_potential"
        or status == "VERIFIED_ON_BOUNDED_REACHABLE_SUBGRAPH"
        or (cert.get("certified_lower_bound") is not None and incomplete_graph)
    ):
        if incomplete_graph or cert.get("complete_space") is not True and cert.get("complete_domain_closed") is not True:
            findings.append(
                {
                    "rule": "CERT_TRUNCATED_INDUCTIVE_POTENTIAL",
                    "message": "inductive_potential or certified_lower_bound on an incomplete concrete graph is unsound.",
                }
            )

    # F-06: Spec-only PROVEN under coarse project_obs or skipped impl parity
    if status == "PROVEN" and (
        cert.get("impl_invariant_checked") is False
        or cert.get("impl_goal_parity_checked") is False
        or cert.get("obs_projection_injective") is False
    ):
        findings.append(
            {
                "rule": "CERT_IMPL_INVARIANT_SKIPPED",
                "message": "PROVEN status is unsound when implementation invariant/goal parity is unchecked under coarse observation.",
            }
        )

    # F-07: Unverified caller bounds stamped VERIFIED
    if (cert.get("unverified_caller_claim") is True or cert.get("caller_bounds_verified") is False) and status in ("VERIFIED", "PROVEN"):
        findings.append(
            {
                "rule": "CERT_UNVERIFIED_CALLER_INFLATION",
                "message": "Caller-supplied numeric bounds without registered certificate verification cannot be stamped VERIFIED.",
            }
        )

    # F-08: Missing, malformed non-64-hex, or unregistered witness_or_proof_sha256 (fail closed, NEON-D5)
    if status in ("VERIFIED", "PROVEN"):
        w_sha = str(cert.get("witness_or_proof_sha256", ""))
        if not SHA256_64_RE.fullmatch(w_sha) or w_sha == "0" * 64:
            findings.append(
                {
                    "rule": "CERT_INVALID_WITNESS_SHA256",
                    "message": f"witness_or_proof_sha256 must be a lowercase 64-hex SHA-256 digest (got {w_sha!r}).",
                }
            )
        elif registered_artifact_digests is not None and w_sha not in registered_artifact_digests:
            findings.append(
                {
                    "rule": "CERT_UNREGISTERED_WITNESS_DIGEST",
                    "message": "witness_or_proof_sha256 is absent from verified certificate registry.",
                }
            )

    passed = len(findings) == 0
    # Do not relabel a lower bound, a conjecture, or a rejection as VERIFIED.
    if not passed:
        out_status = "REJECTED"
    elif status in ("VERIFIED", "PROVEN"):
        out_status = "VERIFIED"
    else:
        out_status = status
    return {
        "passed": passed,
        "epistemic_status": out_status,
        "finding_count": len(findings),
        "findings": findings,
    }


def loads_strict_certificate_json(raw_json: str, *, max_abs_int: int = MAX_CERT_ABS_INT) -> Any:
    """Parse certificate JSON rejecting duplicate keys, floats, NaN/Infinity, and oversized integers."""

    def _reject_float(token: str) -> None:
        raise ValueError(f"floating-point JSON literal forbidden in exact certificate: {token!r}")

    def _reject_const(token: str) -> None:
        raise ValueError(f"non-finite JSON constant forbidden in exact certificate: {token!r}")

    def _bounded_int(token: str) -> int:
        if len(token.lstrip("-")) > 62:
            raise ValueError(f"integer literal exceeds safe digit bound ({len(token)} chars)")
        val = int(token)
        if abs(val) > max_abs_int:
            raise ValueError(f"integer literal exceeds |v| <= {max_abs_int} cap")
        return val

    def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"duplicate JSON object key forbidden: {k!r}")
            out[k] = v
        return out

    return json.loads(
        raw_json,
        object_pairs_hook=_no_duplicate_keys,
        parse_int=_bounded_int,
        parse_float=_reject_float,
        parse_constant=_reject_const,
    )


MAX_DUAL_OBJECTIVE_BITS = 850  # ~255 decimal digits; blocks quadratic bigint stringification DoS


def _parse_exact_rational(val: Any, *, max_abs_int: int = MAX_CERT_ABS_INT) -> Fraction:
    """Parse an exact `int` (`type(val) is int`, never `bool`) or canonical `'p/q'` string into `Fraction`."""
    if type(val) is int:
        if abs(val) > max_abs_int:
            raise ValueError("integer exceeds cap")
        return Fraction(val, 1)
    max_digits = len(str(max_abs_int)) + 1
    if isinstance(val, str):
        if len(val) > (2 * max_digits + 3):
            raise ValueError(f"rational string exceeds safe length bound ({len(val)} chars)")
        if STRICT_RATIONAL_RE.fullmatch(val):
            if "/" in val:
                n_str, d_str = val.split("/", 1)
                if len(n_str.lstrip("-")) > max_digits or len(d_str) > max_digits:
                    raise ValueError("rational component exceeds safe digit bound")
                num, den = int(n_str), int(d_str)
            else:
                if len(val.lstrip("-")) > max_digits:
                    raise ValueError("rational component exceeds safe digit bound")
                num, den = int(val), 1
            if abs(num) > max_abs_int or abs(den) > max_abs_int:
                raise ValueError("rational component exceeds cap")
            return Fraction(num, den)
    raise ValueError(f"invalid exact rational token {val!r} (bool/float forbidden)")


def verify_rational_lp_certificate(cert: Mapping[str, Any]) -> dict[str, Any]:
    """Verify exact rational LP dual lower-bound (`bounds`) or Farkas (`infeasible`) certificates."""
    if not isinstance(cert, Mapping):
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "findings": [{"rule": "LP_CERT_NOT_AN_OBJECT", "message": f"LP certificate must be a JSON object (got {type(cert).__name__})."}],
        }
    raw_mode = cert.get("mode", "bounds")
    if not isinstance(raw_mode, str):
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "findings": [{"rule": "LP_CERT_MALFORMED", "message": "mode must be a string"}],
        }
    mode = raw_mode.strip().lower()
    findings: list[dict[str, str]] = []
    try:
        raw_a, raw_b, raw_y = cert["A"], cert["b"], cert["y"]
        if not isinstance(raw_a, list) or not isinstance(raw_b, list) or not isinstance(raw_y, list):
            raise TypeError("A, b, and y must be lists")
        if any(not isinstance(row, list) for row in raw_a):
            raise TypeError("each row of A must be a list")
        matrix_a = [[_parse_exact_rational(x) for x in row] for row in raw_a]
        rhs_b = [_parse_exact_rational(x) for x in raw_b]
        dual_y = [_parse_exact_rational(x) for x in raw_y]
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "findings": [{"rule": "LP_CERT_MALFORMED", "message": str(exc)}],
        }

    m_rows = len(matrix_a)
    n_cols = len(matrix_a[0]) if m_rows > 0 else 0
    if m_rows == 0 or n_cols == 0:
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "findings": [{"rule": "LP_CERT_EMPTY_SYSTEM", "message": "LP constraint matrix A must have >= 1 row and >= 1 column."}],
        }
    if len(rhs_b) != m_rows or len(dual_y) != m_rows or any(len(r) != n_cols for r in matrix_a):
        return {
            "passed": False,
            "epistemic_status": "REJECTED",
            "findings": [{"rule": "LP_CERT_DIMENSION_MISMATCH", "message": "A, b, y dimensions do not align"}],
        }

    if any(yv < 0 for yv in dual_y):
        findings.append({"rule": "LP_DUAL_NEGATIVE_MULTIPLIER", "message": "dual vector y must satisfy y >= 0"})

    # Compute y^T A (length n_cols) and y^T b (scalar) for primal system A x >= b, x >= 0
    yt_a = [sum((dual_y[i] * matrix_a[i][j] for i in range(m_rows)), Fraction(0, 1)) for j in range(n_cols)]
    yt_b = sum((dual_y[i] * rhs_b[i] for i in range(m_rows)), Fraction(0, 1))

    if mode == "bounds":
        try:
            raw_c = cert["c"]
            if not isinstance(raw_c, list):
                raise TypeError("c must be a list")
            cost_c = [_parse_exact_rational(x) for x in raw_c]
            claimed_lb = _parse_exact_rational(cert["claimed_lower_bound"])
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "passed": False,
                "epistemic_status": "REJECTED",
                "findings": [{"rule": "LP_CERT_MALFORMED", "message": str(exc)}],
            }
        if len(cost_c) != n_cols:
            findings.append({"rule": "LP_CERT_DIMENSION_MISMATCH", "message": "len(c) != cols(A)"})
        else:
            for j in range(n_cols):
                if yt_a[j] > cost_c[j]:
                    findings.append(
                        {
                            "rule": "LP_DUAL_INFEASIBLE_COLUMN",
                            "message": f"column {j}: (y^T A)[{j}] = {yt_a[j]} exceeds c[{j}] = {cost_c[j]}",
                        }
                    )
                    break
        if yt_b < claimed_lb:
            findings.append(
                {
                    "rule": "LP_DUAL_OBJECTIVE_BELOW_CLAIM",
                    "message": f"y^T b = {yt_b} < claimed_lower_bound = {claimed_lb}",
                }
            )
    elif mode == "infeasible":
        # Farkas certificate for {A x >= b, x >= 0} = empty: y >= 0, y^T A <= 0, and y^T b > 0
        for j in range(n_cols):
            if yt_a[j] > 0:
                findings.append(
                    {
                        "rule": "LP_FARKAS_POSITIVE_COLUMN",
                        "message": f"Farkas certificate requires (y^T A)[{j}] <= 0, got {yt_a[j]}",
                    }
                )
                break
        if yt_b <= 0:
            findings.append(
                {
                    "rule": "LP_FARKAS_NONPOSITIVE_WITNESS",
                    "message": f"Farkas certificate requires y^T b > 0, got {yt_b}",
                }
            )
    else:
        findings.append({"rule": "LP_CERT_UNSUPPORTED_MODE", "message": f"unsupported LP mode {mode!r}"})

    if yt_b.numerator.bit_length() > MAX_DUAL_OBJECTIVE_BITS or yt_b.denominator.bit_length() > MAX_DUAL_OBJECTIVE_BITS:
        findings.append(
            {
                "rule": "LP_DUAL_OBJECTIVE_DIGIT_CAP",
                "message": "exact dual objective exceeds safe output digit cap",
            }
        )
        dual_obj_str = "<capped>"
    else:
        dual_obj_str = f"{yt_b.numerator}/{yt_b.denominator}"

    passed = len(findings) == 0
    return {
        "passed": passed,
        "epistemic_status": "VERIFIED" if passed else "REJECTED",
        "dual_objective": dual_obj_str,
        "findings": findings,
    }


def verify_minimal_goal_stopping(
    *,
    init_state: Any,
    actions: Sequence[Any],
    step_fn: Callable[[Any, Any], Any],
    is_goal_fn: Callable[[Any], bool],
) -> dict[str, Any]:
    """Verify an action sequence reaches a goal state and halts without post-goal extra actions."""
    cur = init_state
    if bool(is_goal_fn(cur)):
        if len(actions) > 0:
            return {
                "passed": False,
                "epistemic_status": "REJECTED",
                "first_goal_step": 0,
                "total_actions": len(actions),
                "findings": [
                    {
                        "rule": "CERT_POST_GOAL_EXTRA_ACTIONS",
                        "message": f"initial state already satisfies goal, yet {len(actions)} extra actions were emitted",
                    }
                ],
            }
        return {"passed": True, "epistemic_status": "VERIFIED", "first_goal_step": 0, "total_actions": 0, "findings": []}

    for idx, act in enumerate(actions, start=1):
        nxt = step_fn(cur, act)
        if nxt is None:
            return {
                "passed": False,
                "epistemic_status": "REJECTED",
                "first_goal_step": None,
                "total_actions": len(actions),
                "findings": [{"rule": "CERT_INVALID_TRANSITION_STEP", "message": f"invalid step at index {idx}"}],
            }
        cur = nxt
        if bool(is_goal_fn(cur)) and idx < len(actions):
            return {
                "passed": False,
                "epistemic_status": "REJECTED",
                "first_goal_step": idx,
                "total_actions": len(actions),
                "findings": [
                    {
                        "rule": "CERT_POST_GOAL_EXTRA_ACTIONS",
                        "message": f"goal reached at step {idx}, followed by {len(actions) - idx} trailing extra actions",
                    }
                ],
            }

    reached = bool(is_goal_fn(cur))
    return {
        "passed": reached,
        "epistemic_status": "VERIFIED" if reached else "REJECTED",
        "first_goal_step": len(actions) if reached else None,
        "total_actions": len(actions),
        "findings": [] if reached else [{"rule": "CERT_GOAL_NOT_REACHED", "message": "terminal state is not a goal"}],
    }
