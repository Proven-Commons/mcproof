"""Deterministic Lean 4.35.0 theorem, axiom, WeakStatement, and 6-kernel comparator harness."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from .paths import dep_repo, elan_bin_dir, find_lean_tool, repo_root

STANDARD_AXIOMS: frozenset[str] = frozenset({"propext", "Classical.choice", "Quot.sound"})
SORRY_WARNING_RE = re.compile(r"warning:.*declaration uses [`']sorry[`']")

MODIFIERS_PAT = r"(@\[[^\]]*\][ \t]*)?((scoped|local|private|protected|noncomputable|public)[ \t]+)*"
BAR_FORBIDDEN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("UNPROVED_SORRY", re.compile(r"\bsorry\b")),
    ("UNPROVED_ADMIT", re.compile(r"\badmit\b")),
    ("UNSOUND_IMPLEMENTED_BY", re.compile(r"[iI]mplemented_?[bB]y\w*")),
    ("UNSOUND_EXTERN", re.compile(r"\bextern(Attr)?\b")),
    ("UNSOUND_UNSAFE", re.compile(r"\b\w*[uU]nsafe\w*\b")),
    (
        "UNVERIFIED_NATIVE_EVAL",
        re.compile(
            r"\bnative_decide\b|\+\s*native\b|\bnative\s*:=\s*true\b"
            r"|\bofReduce(Bool|Nat)\b|\btrustCompiler\b"
        ),
    ),
    ("UNSOUND_SKIP_KERNEL_TC", re.compile(r"\bskipKernelTC\b")),
    ("EXTRA_AXIOM_DECL", re.compile(rf"(?m)^[ \t]*{MODIFIERS_PAT}axiom\b")),
    ("OPAQUE_CONST_DECL", re.compile(rf"(?m)^[ \t]*{MODIFIERS_PAT}opaque\b")),
    (
        "FORBIDDEN_META_IMPORT",
        re.compile(
            r"(?m)^[ \t]*((public|meta|private)[ \t]+)*import[ \t]+"
            r"([^\n]*[ \t])?(Lean|Lake)(\.[\w.]+)?(?=\s|$)"
        ),
    ),
    (
        "SYNTAX_OVERRIDE_DECL",
        re.compile(
            rf"(?m)^[ \t]*{MODIFIERS_PAT}"
            r"(notation\d?|infixl|infixr|infix|prefix|postfix|macro|syntax|elab)"
            r"(?=[ \t]*[:(\"]|[ \t]+\w)"
        ),
    ),
    (
        "METAPROGRAM_ESCAPE",
        re.compile(
            r"\b(macro_rules|elab_rules|declare_syntax_cat|run_cmd|run_elab|run_meta"
            r"|simproc|dsimproc|simproc_decl|dsimproc_decl|binder_predicate)\b"
        ),
    ),
)

THEOREM_DECL_RE = re.compile(
    rf"(?ms)^[ \t]*(?:@\[[^\]]*\][ \t]*)?(?:(?:scoped|local|private|protected|noncomputable|public)[ \t]+)*"
    r"(?P<kw>theorem|lemma)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_.']*)\b(?P<header>.*?)(?::=|\bwhere\b|\|)"
)

AXIOM_AUDIT_TEMPLATE = """import Lean
import {module_name}

open Lean

def targetRoot : Name := Name.mkSimple {root_json}

#eval show CoreM Unit from do
  let env <- getEnv
  for (name, info) in env.constants.map₁.toList do
    let some idx := env.getModuleIdxFor? name | continue
    let mod := env.header.moduleNames[idx.toNat]!
    unless mod.getRoot == targetRoot do continue
    let kind := match info with
      | .thmInfo _ => "theorem"
      | .axiomInfo _ => "axiom"
      | .defnInfo _ => "def"
      | .opaqueInfo _ => "opaque"
      | _ => ""
    if kind.isEmpty then continue
    let isSrc := if (<- findDeclarationRanges? name).isSome then "src" else "gen"
    let axs <- collectAxioms name
    let axStr := ",".intercalate (axs.toList.map toString)
    IO.println s!"MCPROOF_AUDIT\\t{{kind}}\\t{{isSrc}}\\t{{name}}\\t{{axStr}}"
"""


def _load_soko_lean4_auditor() -> Any:
    soko_path = dep_repo("soko") / "soko_mcp" / "lean4_auditor.py"
    spec = importlib.util.spec_from_file_location("soko_lean4_auditor", soko_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load lean4_auditor from {soko_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["soko_lean4_auditor"] = mod
    spec.loader.exec_module(mod)
    return mod


def strip_lean_comments_and_strings(src: str) -> str:
    """Strip `--` line comments, nested `/- ... -/` block comments, and string literals while keeping line numbers."""
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        if src.startswith("/-", i):
            depth = 1
            i += 2
            while i < n and depth > 0:
                if src.startswith("/-", i):
                    depth += 1
                    i += 2
                elif src.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    if src[i] == "\n":
                        out.append("\n")
                    i += 1
            continue
        if src.startswith("--", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src[i] == '"':
            i += 1
            out.append('"')
            while i < n and src[i] != '"':
                if src[i] == "\\" and i + 1 < n:
                    if src[i + 1] == "\n":
                        out.append("\n")
                    i += 2
                else:
                    if src[i] == "\n":
                        out.append("\n")
                    i += 1
            out.append('"')
            if i < n:
                i += 1
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def audit_weak_statements(source: str) -> list[dict[str, Any]]:
    """Detect WeakStatement vacuous-hypothesis and tautological-conclusion hazards."""
    cleaned = strip_lean_comments_and_strings(source)
    findings: list[dict[str, Any]] = []

    for match in THEOREM_DECL_RE.finditer(cleaned):
        thm_name = match.group("name")
        header = match.group("header")
        line_no = cleaned.count("\n", 0, match.start()) + 1
        compact = re.sub(r"\s+", " ", header).strip()

        # 1. Conclusion is literal `True`
        if re.search(r":\s*True\s*$", compact):
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_TRUE_CONCLUSION",
                "message": f"theorem '{thm_name}' proves literal True instead of a substantive property",
            })

        # 2. Explicit False hypothesis (`(h : False)` or `False ->` / `False →`)
        if re.search(r":\s*False\b|\bFalse\s*(?:->|→)", compact):
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_FALSE_HYPOTHESIS",
                "message": f"theorem '{thm_name}' assumes False, making the implication vacuously true",
            })

        # 3. Impossible Nat / self-contradictory inequalities (`n < 0` on Nat, `x < x`, `x != x`)
        nat_vars = set()
        for binder in re.finditer(r"\(([^():]+):\s*Nat\)", compact):
            for tok in binder.group(1).split():
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_']*", tok):
                    nat_vars.add(tok)
        for v in sorted(nat_vars):
            if re.search(rf"\b{re.escape(v)}\s*<\s*0\b", compact):
                findings.append({
                    "line": line_no,
                    "rule": "VACUOUS_NAT_LT_ZERO",
                    "message": f"theorem '{thm_name}' assumes '{v} < 0' for Nat variable '{v}' (unsatisfiable)",
                })

        for self_lt in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_']*)\s*(?:<|≠|!=)\s*\1\b", compact):
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_SELF_CONTRADICTION",
                "message": f"theorem '{thm_name}' contains self-contradictory guard '{self_lt.group(0)}'",
            })

        # 4. Direct contradictory propositional binders `(h1 : P)` and `(h2 : ¬ P)` or `(h2 : P -> False)`
        props: list[str] = []
        neg_props: list[str] = []
        for hyp in re.finditer(r"\([^():]+:\s*([^()]+)\)", compact):
            prop = hyp.group(1).strip()
            if prop.startswith("¬"):
                neg_props.append(prop[1:].strip())
            elif prop.startswith("Not "):
                neg_props.append(prop[4:].strip())
            else:
                props.append(prop)
        overlap = set(props) & set(neg_props)
        if overlap:
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_CONTRADICTORY_HYPOTHESES",
                "message": f"theorem '{thm_name}' assumes both P and Not P ({sorted(overlap)[0]})",
            })

    return findings


def lint_lean4_source(
    source: str,
    *,
    label: str = "<lean>",
    strict_init_only: bool = True,
    allow_challenge_sorry: bool = False,
    check_vacuous: bool = True,
    require_theorem: bool = True,
) -> dict[str, Any]:
    """Run static Lean 4 source audits combining soko lean4_auditor, Proven-Commons bar rules, and WeakStatement checks."""
    soko_mod = _load_soko_lean4_auditor()
    soko_rep = soko_mod.audit_lean4_source(source, label=label, strict_init_only=strict_init_only)

    findings: list[dict[str, Any]] = []
    for f in soko_rep.get("findings", []):
        if allow_challenge_sorry and f.get("code") == "UNPROVED_SORRY":
            continue
        findings.append({
            "line": int(f.get("line", 0)),
            "rule": str(f.get("code", "SOKO_LEAN_FINDING")),
            "message": f"soko lean4_auditor flagged {f.get('detail')!r}",
        })

    stripped = strip_lean_comments_and_strings(source)
    seen_line_rules = {(item["line"], item["rule"]) for item in findings}
    for code, rx in BAR_FORBIDDEN_RULES:
        if allow_challenge_sorry and code == "UNPROVED_SORRY":
            continue
        for m in rx.finditer(stripped):
            line_no = stripped.count("\n", 0, m.start()) + 1
            if (line_no, code) not in seen_line_rules:
                seen_line_rules.add((line_no, code))
                findings.append({
                    "line": line_no,
                    "rule": code,
                    "message": f"forbidden Lean escape hatch matched {m.group(0).strip()!r}",
                })

    theorems_found = [m.group("name") for m in THEOREM_DECL_RE.finditer(stripped)]
    if require_theorem and not theorems_found:
        findings.append({
            "line": 1,
            "rule": "NO_THEOREM_DECLARED",
            "message": "Lean module declares zero `theorem` or `lemma` statements",
        })

    if check_vacuous:
        findings.extend(audit_weak_statements(source))

    return {
        "label": label,
        "passed": len(findings) == 0,
        "theorem_names": theorems_found,
        "soko_audit": soko_rep,
        "findings": findings,
    }


def _lean_env() -> dict[str, str]:
    env = dict(os.environ)
    bin_dir = str(elan_bin_dir())
    cur_path = env.get("PATH", "")
    env["PATH"] = f"{bin_dir}:{cur_path}" if cur_path else bin_dir
    return env


@dataclass(frozen=True)
class LeanVerificationResult:
    passed: bool
    toolchain: str
    theorems_checked: tuple[str, ...]
    axioms_used: tuple[str, ...]
    nonstandard_axioms: tuple[str, ...]
    sorry_declarations: tuple[str, ...]
    paranoid_kernels_run: tuple[str, ...]
    sandboxed: bool
    findings: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "toolchain": self.toolchain,
            "theorems_checked": list(self.theorems_checked),
            "axioms_used": list(self.axioms_used),
            "nonstandard_axioms": list(self.nonstandard_axioms),
            "sorry_declarations": list(self.sorry_declarations),
            "paranoid_kernels_run": list(self.paranoid_kernels_run),
            "sandboxed": self.sandboxed,
            "findings": list(self.findings),
        }


def _read_toolchain(lean_project_dir: Path) -> str:
    tc = lean_project_dir / "lean-toolchain"
    return tc.read_text(encoding="utf-8").strip() if tc.is_file() else "leanprover/lean4:v4.35.0"


def verify_lean4_source(
    source: str,
    *,
    label: str = "Candidate.lean",
    strict_init_only: bool = True,
    check_vacuous: bool = True,
    require_theorem: bool = True,
    run_paranoid_leanchecker: bool = True,
    lean_project_dir: Path | None = None,
    timeout_sec: int = 120,
) -> LeanVerificationResult:
    """Compile a Lean 4 source string, audit source escape hatches, verify kernel collectAxioms, and run leanchecker."""
    proj_dir = (lean_project_dir or (repo_root() / "lean")).resolve()
    toolchain = _read_toolchain(proj_dir)
    lint = lint_lean4_source(
        source,
        label=label,
        strict_init_only=strict_init_only,
        allow_challenge_sorry=False,
        check_vacuous=check_vacuous,
        require_theorem=require_theorem,
    )
    findings: list[dict[str, Any]] = list(lint["findings"])

    lean_bin = find_lean_tool("lean")
    lake_bin = find_lean_tool("lake")
    leanchecker_bin = find_lean_tool("leanchecker")
    env = _lean_env()

    # Ensure reference Lean library `.olean` files exist if project not yet built
    lib_olean_dir = proj_dir / ".lake" / "build" / "lib" / "lean"
    if not lib_olean_dir.is_dir():
        subprocess.run(
            [lake_bin, "build", "Mcproof"],
            cwd=proj_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )

    mod_name = "McproofCandidateCheck"
    theorems_checked: list[str] = []
    all_axioms: set[str] = set()
    nonstandard: set[str] = set()
    sorry_decls: list[str] = []
    kernels_run: list[str] = []

    with tempfile.TemporaryDirectory(prefix="mcproof_lean_") as tmp_str:
        tmp_dir = Path(tmp_str)
        cand_lean = tmp_dir / f"{mod_name}.lean"
        cand_olean = tmp_dir / f"{mod_name}.olean"
        cand_lean.write_text(source, encoding="utf-8")

        lean_path_parts = [str(tmp_dir)]
        if lib_olean_dir.is_dir():
            lean_path_parts.append(str(lib_olean_dir))
        run_env = dict(env)
        run_env["LEAN_PATH"] = os.pathsep.join(lean_path_parts)

        comp = subprocess.run(
            [lean_bin, str(cand_lean), "-o", str(cand_olean)],
            cwd=tmp_dir,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        combined_out = (comp.stdout or "") + "\n" + (comp.stderr or "")
        if comp.returncode != 0:
            tail = " | ".join(line.strip() for line in combined_out.strip().splitlines()[-6:] if line.strip())
            findings.append({
                "line": 1,
                "rule": "LEAN_COMPILE_ERROR",
                "message": f"Lean 4 kernel/elaborator rejected module: {tail}",
            })
            return LeanVerificationResult(
                passed=False,
                toolchain=toolchain,
                theorems_checked=(),
                axioms_used=(),
                nonstandard_axioms=(),
                sorry_declarations=(),
                paranoid_kernels_run=(),
                sandboxed=False,
                findings=tuple(findings),
            )

        kernels_run.append("lean-default-kernel")
        if SORRY_WARNING_RE.search(combined_out):
            findings.append({
                "line": 1,
                "rule": "LEAN_SORRY_WARNING",
                "message": "Lean compiler emitted `declaration uses 'sorry'` warning (including anonymous examples)",
            })

        # Trusted external `collectAxioms` walk in a separate driver file
        audit_driver = tmp_dir / "McproofAxiomDriver.lean"
        audit_driver.write_text(
            AXIOM_AUDIT_TEMPLATE.format(module_name=mod_name, root_json=json.dumps(mod_name)),
            encoding="utf-8",
        )
        ax_run = subprocess.run(
            [lean_bin, str(audit_driver)],
            cwd=tmp_dir,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if ax_run.returncode != 0:
            tail = " | ".join(line.strip() for line in ((ax_run.stdout or "") + "\n" + (ax_run.stderr or "")).splitlines()[-4:] if line.strip())
            findings.append({
                "line": 1,
                "rule": "AXIOM_WALK_FAILED",
                "message": f"trusted collectAxioms driver failed: {tail}",
            })
        else:
            for line in ax_run.stdout.splitlines():
                if not line.startswith("MCPROOF_AUDIT\t"):
                    continue
                parts = line.split("\t")
                if len(parts) != 5:
                    continue
                _, kind, is_src, decl_name, ax_csv = parts
                axs = {a for a in ax_csv.split(",") if a}
                all_axioms.update(axs)
                if kind == "theorem" and is_src == "src":
                    theorems_checked.append(decl_name)
                if kind in ("axiom", "opaque"):
                    findings.append({
                        "line": 1,
                        "rule": "KERNEL_EXTRA_AXIOM_OR_OPAQUE",
                        "message": f"kernel environment contains {kind} declaration '{decl_name}'",
                    })
                if "sorryAx" in axs:
                    sorry_decls.append(decl_name)
                    findings.append({
                        "line": 1,
                        "rule": "KERNEL_SORRY_AXIOM",
                        "message": f"declaration '{decl_name}' depends on 'sorryAx'",
                    })
                extra_axs = axs - STANDARD_AXIOMS - {"sorryAx"}
                if extra_axs:
                    nonstandard.update(extra_axs)
                    findings.append({
                        "line": 1,
                        "rule": "KERNEL_NONSTANDARD_AXIOM",
                        "message": f"declaration '{decl_name}' depends on non-standard axioms: {sorted(extra_axs)}",
                    })

            if require_theorem and not theorems_checked:
                findings.append({
                    "line": 1,
                    "rule": "NO_KERNEL_THEOREM_FOUND",
                    "message": "kernel environment contains zero source theorems after elaboration",
                })

        if run_paranoid_leanchecker and cand_olean.is_file():
            lc_run = subprocess.run(
                [leanchecker_bin, mod_name],
                cwd=tmp_dir,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            if lc_run.returncode != 0:
                tail = " | ".join(line.strip() for line in ((lc_run.stdout or "") + "\n" + (lc_run.stderr or "")).splitlines()[-4:] if line.strip())
                findings.append({
                    "line": 1,
                    "rule": "LEANCHECKER_PARANOID_REJECT",
                    "message": f"leanchecker rejected compiled .olean environment: {tail}",
                })
            else:
                kernels_run.append("leanchecker")

    passed = (
        len(findings) == 0
        and len(sorry_decls) == 0
        and len(nonstandard) == 0
        and (not require_theorem or len(theorems_checked) > 0)
    )
    return LeanVerificationResult(
        passed=passed,
        toolchain=toolchain,
        theorems_checked=tuple(sorted(theorems_checked)),
        axioms_used=tuple(sorted(all_axioms)),
        nonstandard_axioms=tuple(sorted(nonstandard)),
        sorry_declarations=tuple(sorted(sorry_decls)),
        paranoid_kernels_run=tuple(kernels_run),
        sandboxed=False,
        findings=tuple(findings),
    )


def verify_lean4_project_comparator(
    project_dir: Path | None = None,
    *,
    strict_init_only: bool = True,
    timeout_sec: int = 300,
) -> LeanVerificationResult:
    """Run full 6-kernel `lake comparator --paranoid` + source escape-hatch checks on a Lake project."""
    proj = (project_dir or (repo_root() / "lean")).resolve()
    toolchain = _read_toolchain(proj)
    lake_bin = find_lean_tool("lake")
    env = _lean_env()
    findings: list[dict[str, Any]] = []

    cmp_path = proj / "comparator.json"
    if not cmp_path.is_file():
        return LeanVerificationResult(
            passed=False,
            toolchain=toolchain,
            theorems_checked=(),
            axioms_used=(),
            nonstandard_axioms=(),
            sorry_declarations=(),
            paranoid_kernels_run=(),
            sandboxed=False,
            findings=({"line": 1, "rule": "MISSING_COMPARATOR_JSON", "message": f"no comparator.json in {proj}"},),
        )

    cmp_cfg = json.loads(cmp_path.read_text(encoding="utf-8"))
    challenge_mod = str(cmp_cfg.get("challenge_module", ""))
    challenge_rel = Path(*challenge_mod.split(".")).with_suffix(".lean") if challenge_mod else None
    theorem_names = tuple(str(t) for t in cmp_cfg.get("theorem_names", []))
    permitted = set(cmp_cfg.get("permitted_axioms", []))
    extra_permitted = permitted - STANDARD_AXIOMS
    if extra_permitted:
        findings.append({
            "line": 1,
            "rule": "NONSTANDARD_PERMITTED_AXIOMS",
            "message": f"comparator.json permits non-standard axioms: {sorted(extra_permitted)}",
        })

    # Static source lint on every `.lean` file in the project outside `.lake` and `.git`
    for lean_file in sorted(proj.rglob("*.lean")):
        rel = lean_file.relative_to(proj)
        if any(part in (".lake", ".git") for part in rel.parts):
            continue
        is_challenge = challenge_rel is not None and rel == challenge_rel
        lint = lint_lean4_source(
            lean_file.read_text(encoding="utf-8"),
            label=rel.as_posix(),
            strict_init_only=strict_init_only,
            allow_challenge_sorry=is_challenge,
            check_vacuous=True,
            require_theorem=False,
        )
        findings.extend(lint["findings"])

    # Run `lake build`
    build_res = subprocess.run(
        [lake_bin, "build"],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if build_res.returncode != 0:
        tail = " | ".join(line.strip() for line in ((build_res.stdout or "") + "\n" + (build_res.stderr or "")).splitlines()[-6:] if line.strip())
        findings.append({
            "line": 1,
            "rule": "LAKE_BUILD_FAILED",
            "message": f"`lake build` failed: {tail}",
        })
        return LeanVerificationResult(
            passed=False,
            toolchain=toolchain,
            theorems_checked=theorem_names,
            axioms_used=(),
            nonstandard_axioms=(),
            sorry_declarations=(),
            paranoid_kernels_run=(),
            sandboxed=False,
            findings=tuple(findings),
        )

    bwrap_available = shutil.which("bwrap") is not None and sys.platform.startswith("linux")
    cmp_cmd = [lake_bin, "comparator", "--paranoid"]
    if not bwrap_available:
        cmp_cmd.append("--inadvisably-no-sandbox")

    cmp_res = subprocess.run(
        cmp_cmd,
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    cmp_out = (cmp_res.stdout or "") + "\n" + (cmp_res.stderr or "")
    kernels_accepted: list[str] = []
    for k_label, pat in (
        ("lean-paranoid", "Lean paranoid kernel accepts the solution"),
        ("lean4lean", "lean4lean kernel accepts the solution"),
        ("nanoda", "nanoda kernel accepts the solution"),
        ("con-leche", "con-leche kernel accepts the solution"),
        ("con-ron", "con-ron kernel accepts the solution"),
        ("lean-default", "Lean default kernel accepts the solution"),
    ):
        if pat in cmp_out:
            kernels_accepted.append(k_label)

    sorry_decls: list[str] = []
    nonstd: list[str] = []
    if cmp_res.returncode != 0 or "Your solution is okay!" not in cmp_out:
        if "sorryAx" in cmp_out:
            sorry_decls.append("sorryAx")
        for ax_m in re.finditer(r"Illegal axiom detected:\s*'([^']+)'", cmp_out):
            ax_name = ax_m.group(1)
            if ax_name == "sorryAx":
                if ax_name not in sorry_decls:
                    sorry_decls.append(ax_name)
            else:
                nonstd.append(ax_name)
        tail = " | ".join(line.strip() for line in cmp_out.strip().splitlines()[-6:] if line.strip())
        findings.append({
            "line": 1,
            "rule": "COMPARATOR_PARANOID_REJECT",
            "message": f"`lake comparator --paranoid` rejected project (exit {cmp_res.returncode}): {tail}",
        })

    passed = (
        len(findings) == 0
        and cmp_res.returncode == 0
        and len(kernels_accepted) == 6
    )
    return LeanVerificationResult(
        passed=passed,
        toolchain=toolchain,
        theorems_checked=theorem_names,
        axioms_used=tuple(sorted(permitted & STANDARD_AXIOMS)),
        nonstandard_axioms=tuple(sorted(set(nonstd))),
        sorry_declarations=tuple(sorry_decls),
        paranoid_kernels_run=tuple(kernels_accepted),
        sandboxed=bwrap_available,
        findings=tuple(findings),
    )
