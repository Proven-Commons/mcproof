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
    (
        # Not only at the start of a line. A mid-line `#eval` still runs during elaboration.
        "FORBIDDEN_EVAL_COMMAND",
        re.compile(r"#(?:eval|reduce|check|print|synth)\b"),
    ),
)

COMPARATOR_ORDERED_KERNELS: tuple[tuple[str, str, str], ...] = (
    ("lean-paranoid", "Running Lean paranoid kernel on solution", "Lean paranoid kernel accepts the solution"),
    ("lean4lean", "Running lean4lean kernel on solution", "lean4lean kernel accepts the solution"),
    ("nanoda", "Running nanoda kernel on solution", "nanoda kernel accepts the solution"),
    ("con-leche", "Running con-leche kernel on solution", "con-leche kernel accepts the solution"),
    ("con-ron", "Running con-ron kernel on solution", "con-ron kernel accepts the solution"),
    ("lean-default", "Running Lean default kernel on solution", "Lean default kernel accepts the solution"),
)

THEOREM_DECL_RE = re.compile(
    rf"(?ms)^[ \t]*(?:@\[[^\]]*\][ \t]*)?(?:(?:scoped|local|private|protected|noncomputable|public)[ \t]+)*"
    r"(?P<kw>theorem|lemma)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_.']*)\b(?P<header>.*?)(?::=|\bwhere\b|\|)"
)


def linux_bwrap_functional(*, timeout_sec: float = 5.0) -> bool:
    """Return True when Linux `bwrap` runs a minimal sandbox and can create `lake comparator`'s `/run/user` session dir."""
    if not sys.platform.startswith("linux"):
        return False
    bwrap_bin = shutil.which("bwrap")
    if not bwrap_bin:
        return False
    try:
        basic = subprocess.run(
            [bwrap_bin, "--ro-bind", "/", "/", "true"],
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        if basic.returncode != 0:
            return False
        uid = os.getuid()
        lake_compat = subprocess.run(
            [
                bwrap_bin,
                "--ro-bind",
                "/",
                "/",
                "--bind",
                "/run",
                "/run",
                "--bind",
                "/tmp",
                "/tmp",
                "sh",
                "-c",
                f"mkdir -p /run/user/{uid} && test -w /run/user/{uid}",
            ],
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return lake_compat.returncode == 0


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

MODULE_AXIOM_AUDIT_TEMPLATE = """import Lean
import {module_name}

open Lean

def targetMod : Name := `{module_name}

#eval show CoreM Unit from do
  let env <- getEnv
  for (name, info) in env.constants.map₁.toList do
    let some idx := env.getModuleIdxFor? name | continue
    let mod := env.header.moduleNames[idx.toNat]!
    unless mod == targetMod do continue
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


def _is_lean_letter_like(ch: str) -> bool:
    """Lean `isLetterLike` ranges used to keep identifier tokens intact."""
    o = ord(ch)
    if 0x3B1 <= o <= 0x3C9 and o != 0x3BB:
        return True
    if 0x391 <= o <= 0x3A9 and o not in (0x3A0, 0x3A3):
        return True
    if 0x3CA <= o <= 0x3FB or 0x1F00 <= o <= 0x1FFE:
        return True
    if 0x2100 <= o <= 0x214F or 0x1D49C <= o <= 0x1D59F:
        return True
    if 0x00C0 <= o <= 0x00FF and o not in (0x00D7, 0x00F7):
        return True
    return 0x0100 <= o <= 0x017F


def _is_lean_subscript_alnum(ch: str) -> bool:
    o = ord(ch)
    return (
        0x2080 <= o <= 0x2089
        or 0x2090 <= o <= 0x209C
        or 0x1D62 <= o <= 0x1D6A
        or o == 0x2C7C
    )


def _is_lean_id_first(ch: str) -> bool:
    return ch.isalpha() or ch == "_" or _is_lean_letter_like(ch)


def _is_lean_id_rest(ch: str) -> bool:
    return (
        ch.isalnum()
        or ch in "_'!?"
        or _is_lean_letter_like(ch)
        or _is_lean_subscript_alnum(ch)
    )


def _is_hex_digit(ch: str) -> bool:
    return ch.isdigit() or "a" <= ch <= "f" or "A" <= ch <= "F"


def _lean_ident_end(src: str, i: int) -> int:
    """End index of the identifier that starts at `i`, including dotted segments and `«...»` parts."""
    n = len(src)
    while i < n:
        if src[i] == "«":
            j = src.find("»", i + 1)
            i = n if j < 0 else j + 1
        elif _is_lean_id_first(src[i]):
            i += 1
            while i < n and _is_lean_id_rest(src[i]):
                i += 1
        else:
            break
        if i < n and src[i] == "." and i + 1 < n and (src[i + 1] == "«" or _is_lean_id_first(src[i + 1])):
            i += 1
            continue
        break
    return i


def _is_raw_str_start(src: str, i: int) -> bool:
    """True when `src[i]` is `r` and the token is `r` plus zero or more `#` plus `"`."""
    if i >= len(src) or src[i] != "r":
        return False
    j = i + 1
    while j < len(src) and src[j] == "#":
        j += 1
    return j < len(src) and src[j] == '"'


def _append_raw_string(src: str, i: int, out: list[str]) -> int:
    """Blank a Lean raw string (`r"..."`, `r#"..."#`, any hash count). `\\` is not an escape."""
    n = len(src)
    j = i + 1
    hashes = 0
    while j < n and src[j] == "#":
        hashes += 1
        j += 1
    if j >= n or src[j] != '"':
        out.append(src[i])
        return i + 1
    j += 1
    out.append('"')
    while j < n:
        if src[j] == '"':
            k = j + 1
            seen = 0
            while seen < hashes and k < n and src[k] == "#":
                seen += 1
                k += 1
            if seen == hashes:
                j = k
                break
        if src[j] == "\n":
            out.append("\n")
        j += 1
    out.append('"')
    return j


def _char_lit_end(src: str, i: int) -> int | None:
    """End index of a Lean character literal at `i`, or None when `src[i:]` is not one.

    Covers `'a'`, `'"'`, and escapes (`'\\n'`, `'\\''`, `'\\"'`, `'\\\\'`, `\\xNN`, `\\uNNNN`).
    `''` is not a character literal.
    """
    n = len(src)
    if i >= n or src[i] != "'" or i + 1 >= n or src[i + 1] == "'":
        return None
    j = i + 1
    if src[j] == "\\":
        if j + 1 >= n:
            return None
        nxt = src[j + 1]
        if nxt in "\\\"'rnt":
            j += 2
        elif nxt == "x" and j + 3 < n and _is_hex_digit(src[j + 2]) and _is_hex_digit(src[j + 3]):
            j += 4
        elif nxt == "u" and j + 5 < n and all(_is_hex_digit(src[j + k]) for k in range(2, 6)):
            j += 6
        else:
            return None
    else:
        j += 1
    if j < n and src[j] == "'":
        return j + 1
    return None


def strip_lean_comments_and_strings(src: str) -> str:
    """Strip `--` line comments, nested `/- ... -/` block comments, and string literals while keeping line numbers.

    Raw strings (`r"..."`, `r#"..."#`, any number of hashes) do not treat `\\` as an escape.
    Character literals, including `'"'` and escaped forms, are kept so a following command stays visible.
    """
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
        if _is_raw_str_start(src, i):
            i = _append_raw_string(src, i, out)
            continue
        if src[i] == "«" or _is_lean_id_first(src[i]):
            j = _lean_ident_end(src, i)
            out.append(src[i:j])
            i = j
            continue
        if src[i] == "'":
            end = _char_lit_end(src, i)
            if end is not None:
                out.append(src[i:end])
                i = end
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


def _unwrap_outer_parens(expr: str) -> str:
    s = expr.strip()
    while len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        depth = 0
        wraps_all = True
        for idx, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx < len(s) - 1:
                    wraps_all = False
                    break
        if wraps_all and depth == 0:
            s = s[1:-1].strip()
        else:
            break
    return s


def _split_top_level_arrows(expr: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in "([{⟨":
            depth += 1
            i += 1
        elif ch in ")]}⟩":
            depth = max(0, depth - 1)
            i += 1
        elif depth == 0 and expr.startswith("->", i):
            parts.append(expr[start:i].strip())
            i += 2
            start = i
        elif depth == 0 and ch == "→":
            parts.append(expr[start:i].strip())
            i += 1
            start = i
        else:
            i += 1
    parts.append(expr[start:].strip())
    return [p for p in parts if p]


def _extract_binder_props(prefix: str) -> list[tuple[str, str]]:
    """Extract `(lhs_names, rhs_type)` from top-level `(...)` binders in a theorem header."""
    out: list[tuple[str, str]] = []
    i = 0
    n = len(prefix)
    while i < n:
        if prefix[i] == "(":
            depth = 1
            j = i + 1
            colon_at = -1
            while j < n and depth > 0:
                if prefix[j] in "([{⟨":
                    depth += 1
                elif prefix[j] in ")]}⟩":
                    depth -= 1
                elif prefix[j] == ":" and depth == 1 and colon_at < 0 and prefix[j : j + 2] != ":=":
                    colon_at = j
                j += 1
            if depth == 0 and colon_at > i:
                lhs = prefix[i + 1 : colon_at].strip()
                rhs = prefix[colon_at + 1 : j - 1].strip()
                out.append((lhs, rhs))
            i = j
        else:
            i += 1
    return out


def _is_vacuous_false_prop(raw_prop: str) -> bool:
    u = re.sub(r"\s+", " ", _unwrap_outer_parens(raw_prop)).strip()
    if u == "False":
        return True
    segs = _split_top_level_arrows(u)
    if len(segs) == 2 and _unwrap_outer_parens(segs[0]) == "True" and _unwrap_outer_parens(segs[1]) == "False":
        return True
    return False


def audit_weak_statements(source: str) -> list[dict[str, Any]]:
    """Detect WeakStatement vacuous-hypothesis and tautological-conclusion hazards."""
    cleaned = strip_lean_comments_and_strings(source)
    findings: list[dict[str, Any]] = []

    for match in THEOREM_DECL_RE.finditer(cleaned):
        thm_name = match.group("name")
        header = match.group("header")
        line_no = cleaned.count("\n", 0, match.start()) + 1
        compact = re.sub(r"\s+", " ", header).strip()

        depth = 0
        top_colon_idx = -1
        for idx_c, ch in enumerate(compact):
            if ch in "([{⟨":
                depth += 1
            elif ch in ")]}⟩":
                depth = max(0, depth - 1)
            elif ch == ":" and depth == 0 and compact[idx_c : idx_c + 2] != ":=":
                top_colon_idx = idx_c
                break

        binder_prefix = compact[:top_colon_idx] if top_colon_idx >= 0 else compact
        concl_expr = compact[top_colon_idx + 1 :].strip() if top_colon_idx >= 0 else ""
        arrow_segs = _split_top_level_arrows(concl_expr) if concl_expr else []
        final_concl = _unwrap_outer_parens(arrow_segs[-1]) if arrow_segs else ""
        arrow_premises = arrow_segs[:-1] if len(arrow_segs) > 1 else []
        binders = _extract_binder_props(binder_prefix)

        # 1. Conclusion is literal `True` (including parenthesized `(True)` or `P -> (True)`)
        if final_concl == "True":
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_TRUE_CONCLUSION",
                "message": f"theorem '{thm_name}' proves literal True instead of a substantive property",
            })

        # 2. Explicit False or `True -> False` hypothesis in binders or arrow premises (`(False) →`, `(h : True → False)`)
        has_false_hyp = any(_is_vacuous_false_prop(rhs) for _, rhs in binders) or any(
            _is_vacuous_false_prop(prem) for prem in arrow_premises
        )
        if has_false_hyp or re.search(r":\s*False\b|\bFalse\s*(?:->|→)", compact):
            # Exclude legitimate negation conclusion `P → False` where `False` is only the final conclusion!
            if has_false_hyp or any("False" in rhs for _, rhs in binders) or any("False" in p for p in arrow_premises):
                findings.append({
                    "line": line_no,
                    "rule": "VACUOUS_FALSE_HYPOTHESIS",
                    "message": f"theorem '{thm_name}' assumes False (or True -> False), making the implication vacuously true",
                })

        # 3. Impossible Nat / self-contradictory inequalities (`n < 0` on Nat, `x < x`, `x != x`)
        nat_vars = set()
        for lhs, rhs in binders:
            if _unwrap_outer_parens(rhs) == "Nat":
                for tok in lhs.split():
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
            prefix = compact[: self_lt.start()].rstrip()
            suffix = compact[self_lt.end() :].lstrip()
            unwrapped_prefix = prefix.rstrip("(").rstrip()
            negated_by_op = unwrapped_prefix.endswith("¬") or bool(re.search(r"\bNot$", unwrapped_prefix))
            unwrapped_suffix = suffix.lstrip(")").lstrip()
            negated_by_false_arrow = bool(
                re.match(r"^(?:->|→)\s*False\s*$", unwrapped_suffix)
                and unwrapped_prefix.endswith(":")
            )
            if negated_by_op or negated_by_false_arrow:
                continue
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_SELF_CONTRADICTION",
                "message": f"theorem '{thm_name}' contains self-contradictory guard '{self_lt.group(0)}'",
            })

        # 4. Direct contradictory propositional binders `(h1 : P)` and `(h2 : ¬ P)` or `(h2 : P -> False)`
        props: list[str] = []
        neg_props: list[str] = []
        for _, rhs in binders:
            prop = _unwrap_outer_parens(rhs)
            if prop.startswith("¬"):
                neg_props.append(_unwrap_outer_parens(prop[1:]))
            elif prop.startswith("Not "):
                neg_props.append(_unwrap_outer_parens(prop[4:]))
            else:
                segs_p = _split_top_level_arrows(prop)
                if len(segs_p) == 2 and _unwrap_outer_parens(segs_p[1]) == "False":
                    neg_props.append(_unwrap_outer_parens(segs_p[0]))
                else:
                    props.append(prop)
        overlap = set(props) & set(neg_props)
        if overlap:
            findings.append({
                "line": line_no,
                "rule": "VACUOUS_CONTRADICTORY_HYPOTHESES",
                "message": f"theorem '{thm_name}' assumes both P and Not P ({sorted(overlap)[0]})",
            })

        # 5. Circular / tautological binder premise identical to conclusion (`(h : P) : P`)
        if final_concl and final_concl != "True":
            norm_concl = re.sub(r"\s+", " ", final_concl).strip()
            for p_hyp in [*props, *[_unwrap_outer_parens(ap) for ap in arrow_premises]]:
                if re.sub(r"\s+", " ", p_hyp).strip() == norm_concl:
                    findings.append({
                        "line": line_no,
                        "rule": "VACUOUS_TAUTOLOGICAL_HYPOTHESIS",
                        "message": f"theorem '{thm_name}' assumes its exact conclusion '{norm_concl}' as a premise",
                    })
                    break

    return findings


LEAN_DEF_OR_ABBREV_RE = re.compile(
    rf"(?ms)^[ \t]*{MODIFIERS_PAT}(?P<kw>def|abbrev)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_.']*)\b(?P<rest>.*?)"
    r"(?=\n[ \t]*(?:@\[[^\]]*\][ \t]*)?(?:(?:scoped|local|private|protected|noncomputable|public)[ \t]+)*"
    r"(?:def|abbrev|theorem|lemma|structure|inductive|class|instance|axiom|opaque|example|end|namespace)\b|\Z)"
)

LEAN_TOKEN_RE = re.compile(
    r":=|=>|<=|>=|!=|==|&&|\|\||->|<-|::|[A-Za-z_][A-Za-z0-9_.']*|[0-9]+|[()\[\]{}:,;|+\-*/%<>^=¬∧∨↔∀∃≤≥≠→←⟨⟩·]|\S"
)


def normalize_lean_tokens(text: str) -> str:
    """Canonical token-spacing normalizer so `(x: Nat)` and `(x : Nat)` compare equal."""
    toks: list[str] = []
    for tok in LEAN_TOKEN_RE.findall(text):
        if tok == "->":
            toks.append("→")
        elif tok == "<-":
            toks.append("←")
        else:
            toks.append(tok)
    return " ".join(toks)


def extract_normalized_lean_defs(source: str) -> dict[str, str]:
    """Extract `(short_def_name -> normalized_kw_sig_and_body)` from non-sorry Lean `def`/`abbrev` declarations."""
    cleaned = strip_lean_comments_and_strings(source)
    defs: dict[str, str] = {}
    for m in LEAN_DEF_OR_ABBREV_RE.finditer(cleaned):
        rest = m.group("rest")
        if re.search(r"\bsorry\b", rest):
            continue
        kw = m.group("kw")
        short_name = m.group("name").split(".")[-1]
        defs[short_name] = f"{kw} {normalize_lean_tokens(rest)}"
    return defs


def verify_pinned_lean_defs(prompt_source: str, candidate_source: str) -> list[dict[str, Any]]:
    """Reject candidate Lean modules that redefine a prompt-supplied target `def` or `abbrev` (`CertiFFI` hazard)."""
    pinned = extract_normalized_lean_defs(prompt_source)
    if not pinned:
        return []
    cand_defs = extract_normalized_lean_defs(candidate_source)
    findings: list[dict[str, Any]] = []
    for def_name, expected_norm in sorted(pinned.items()):
        if def_name in cand_defs and cand_defs[def_name] != expected_norm:
            findings.append({
                "line": 1,
                "rule": "TARGET_DEF_BODY_MUTATED",
                "message": f"candidate mutated pinned target definition '{def_name}' away from prompt specification",
            })
    return findings


PROMPT_BACKTICK_THM_RE = re.compile(
    r"`(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_.']*)\s*([^`]*:[^`]+)`"
)
PROMPT_BACKTICK_DEF_RE = re.compile(
    r"`((?:def|abbrev)\s+[A-Za-z_][A-Za-z0-9_.']*[^`]+)`"
)
PROMPT_BACKTICK_TYPE_DECL_RE = re.compile(
    r"`(?:structure|inductive)\s+([A-Za-z_][A-Za-z0-9_.']*)\b[^`]*`"
)
LEAN_NAMESPACE_RE = re.compile(r"(?m)^[ \t]*namespace[ \t]+([A-Za-z_][A-Za-z0-9_.']*)")
LEAN_DECL_NAME_RE_TEMPLATE = (
    rf"(?m)^[ \t]*{MODIFIERS_PAT}(?:def|abbrev|structure|inductive)[ \t]+"
    r"(?:[A-Za-z_][A-Za-z0-9_.']*\.)?{short_name}\b"
)

CHALLENGE_CMP_DRIVER_TEMPLATE = """import Lean

open Lean Meta

def runCheck (specMod candMod : Name) : CoreM Unit := do
  let envSpec ← importModules #[{ module := specMod }] {}
  let envCand ← importModules #[{ module := candMod }] {}
  for (name, specInfo) in envSpec.constants.map₁.toList do
    let some idx := envSpec.getModuleIdxFor? name | continue
    let modName := envSpec.header.moduleNames[idx.toNat]!
    unless modName == specMod do continue
    if name.isInternal then continue
    let strName := name.toString
    if strName.endsWith ".rec" || strName.endsWith ".recOn" || strName.endsWith ".casesOn" ||
       strName.endsWith ".brecOn" || strName.endsWith ".below" || strName.endsWith ".ibelow" ||
       strName.endsWith ".noConfusion" || strName.endsWith ".noConfusionType" ||
       strName.endsWith ".ctorIdx" || strName.endsWith ".inj" || strName.endsWith ".injEq" ||
       strName.endsWith ".sizeOf_spec" || strName.endsWith ".elim" then
      continue
    let some candInfo := envCand.find? name
      | IO.println s!"MCPROOF_CMP_ERR\\tMISSING_CHALLENGE_DECLARATION\\t{name}"; continue
    match specInfo with
    | .thmInfo st =>
      match candInfo with
      | .thmInfo ct =>
        let (eqTy, _) ← (Meta.isDefEq st.type ct.type).run' {}
          |>.toIO { fileName := "<cmp>", fileMap := default } { env := envCand }
        if !eqTy then
          IO.println s!"MCPROOF_CMP_ERR\\tCHALLENGE_THEOREM_TYPE_MISMATCH\\t{name}"
      | _ =>
        IO.println s!"MCPROOF_CMP_ERR\\tCHALLENGE_NOT_A_THEOREM\\t{name}"
    | .defnInfo sd =>
      match candInfo with
      | .defnInfo cd =>
        let (eqBoth, _) ← (do
          let tOk ← Meta.isDefEq sd.type cd.type
          if !tOk then return false
          Meta.isDefEq sd.value cd.value
        ).run' {} |>.toIO { fileName := "<cmp>", fileMap := default } { env := envCand }
        if !eqBoth then
          IO.println s!"MCPROOF_CMP_ERR\\tCHALLENGE_DEF_MUTATED\\t{name}"
      | _ =>
        IO.println s!"MCPROOF_CMP_ERR\\tCHALLENGE_NOT_A_DEF\\t{name}"
    | .inductInfo si =>
      match candInfo with
      | .inductInfo ci =>
        if si.ctors != ci.ctors || si.numParams != ci.numParams then
          IO.println s!"MCPROOF_CMP_ERR\\tCHALLENGE_INDUCT_MUTATED\\t{name}"
      | _ =>
        IO.println s!"MCPROOF_CMP_ERR\\tCHALLENGE_NOT_AN_INDUCT\\t{name}"
    | _ => pure ()

#eval runCheck `McproofSpecMod `McproofCandMod
"""


def extract_prompt_lean_obligations(prompt_text: str, fenced_lean_blocks: Sequence[str] = ()) -> dict[str, Any]:
    """Extract label-free theorem & definition obligations strictly from the prompt text (`NEON-C2`)."""
    def_snippets: list[str] = list(fenced_lean_blocks)
    required_defs: list[str] = []
    theorem_specs: list[tuple[str, str]] = []
    theorem_names: list[str] = []

    for blk in fenced_lean_blocks:
        cleaned_blk = strip_lean_comments_and_strings(blk)
        for dm in LEAN_DEF_OR_ABBREV_RE.finditer(cleaned_blk):
            dn = dm.group("name").split(".")[-1]
            if dn not in required_defs:
                required_defs.append(dn)
        for tm in THEOREM_DECL_RE.finditer(cleaned_blk):
            tn = tm.group("name").split(".")[-1]
            hdr = tm.group("header").strip()
            if tn not in theorem_names:
                theorem_names.append(tn)
            if ":" in hdr:
                theorem_specs.append((tn, hdr))

    for m_def in PROMPT_BACKTICK_DEF_RE.finditer(prompt_text):
        snip = m_def.group(1).strip()
        def_snippets.append(snip)
        m_n = re.match(r"^(?:def|abbrev)\s+([A-Za-z_][A-Za-z0-9_.']*)\b", snip)
        if m_n:
            dn = m_n.group(1).split(".")[-1]
            if dn not in required_defs:
                required_defs.append(dn)

    for m_ty in PROMPT_BACKTICK_TYPE_DECL_RE.finditer(prompt_text):
        tn_ty = m_ty.group(1).split(".")[-1]
        if tn_ty not in required_defs:
            required_defs.append(tn_ty)

    for m_thm in PROMPT_BACKTICK_THM_RE.finditer(prompt_text):
        short_t = m_thm.group(1).split(".")[-1]
        hdr = re.sub(r":=\s*(?:by\s+)?sorry\s*$", "", m_thm.group(2)).strip()
        if short_t not in theorem_names:
            theorem_names.append(short_t)
        if ":" in hdr and not any(s[0] == short_t for s in theorem_specs):
            theorem_specs.append((short_t, hdr))

    for raw_t in re.findall(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_.']*)\b", prompt_text):
        st = raw_t.split(".")[-1]
        if st not in theorem_names:
            theorem_names.append(st)

    return {
        "def_snippets": def_snippets,
        "required_defs": required_defs,
        "theorem_specs": theorem_specs,
        "theorem_names": theorem_names,
    }


def verify_lean4_prompt_obligations(
    prompt_text: str,
    candidate_source: str,
    *,
    fenced_prompt_lean: Sequence[str] = (),
    lean_project_dir: Path | None = None,
    run_kernel_type_check: bool = True,
    timeout_sec: float = 60.0,
) -> list[dict[str, Any]]:
    """Verify comment-stripped declarations AND kernel `Meta.isDefEq` theorem types against prompt text (`NEON-C2`)."""
    obligations = extract_prompt_lean_obligations(prompt_text, fenced_prompt_lean)
    cleaned_cand = strip_lean_comments_and_strings(candidate_source)
    findings: list[dict[str, Any]] = []

    declared_thms = {m.group("name").split(".")[-1] for m in THEOREM_DECL_RE.finditer(cleaned_cand)}
    for req_thm in obligations["theorem_names"]:
        if req_thm not in declared_thms:
            findings.append({
                "line": 1,
                "rule": "MISSING_PROMPT_THEOREM_NAME",
                "message": f"Completion must declare and prove prompt theorem `{req_thm}` (not merely mention it in comments).",
            })

    for req_def in obligations["required_defs"]:
        pat = LEAN_DECL_NAME_RE_TEMPLATE.format(short_name=re.escape(req_def))
        if not re.search(pat, cleaned_cand):
            findings.append({
                "line": 1,
                "rule": "MISSING_PROMPT_DEF_DECL",
                "message": f"Completion omitted required prompt declaration `{req_def}`.",
            })

    for snip in obligations["def_snippets"]:
        for df in verify_pinned_lean_defs(snip, candidate_source):
            if not any(existing.get("message") == df.get("message") for existing in findings):
                findings.append(df)

    if findings or not run_kernel_type_check or not obligations["theorem_specs"]:
        return findings

    proj_dir = (lean_project_dir or (repo_root() / "lean")).resolve()
    lean_bin = find_lean_tool("lean")
    env = _lean_env()
    lib_olean_dir = proj_dir / ".lake" / "build" / "lib" / "lean"

    cand_namespaces = LEAN_NAMESPACE_RE.findall(cleaned_cand)
    open_lines = "\n".join(f"open {ns}" for ns in dict.fromkeys(cand_namespaces))
    ax_lines: list[str] = []
    pair_entries: list[str] = []
    for idx, (short_t, hdr) in enumerate(obligations["theorem_specs"]):
        ax_name = f"_mcproof_pspec_{idx}"
        ax_lines.append(f"axiom {ax_name} {hdr}")
        qual_t = f"{cand_namespaces[0]}.{short_t}" if cand_namespaces else short_t
        pair_entries.append(f"(`{ax_name}, `{qual_t}, `{short_t})")

    drv_src = (
        "import Lean\n"
        "import McproofPromptCand\n"
        "open Lean Meta\n"
        f"{open_lines}\n"
        + "\n".join(ax_lines)
        + "\n\n#eval show CoreM Unit from do\n"
        "  let env ← getEnv\n"
        f"  let pairs : List (Name × Name × Name) := [{', '.join(pair_entries)}]\n"
        "  for (axN, fullN, shortN) in pairs do\n"
        "    let some specI := env.find? axN | IO.println s!\"MCPROOF_PSPEC_ERR\\tSPEC_ELAB_FAIL\\t{shortN}\"; continue\n"
        "    let candOpt := match env.find? fullN with\n"
        "      | some ci => some ci\n"
        "      | none => env.find? shortN\n"
        "    let some candI := candOpt | IO.println s!\"MCPROOF_PSPEC_ERR\\tMISSING_PROMPT_THEOREM_NAME\\t{shortN}\"; continue\n"
        "    match candI with\n"
        "    | .thmInfo ct =>\n"
        "      let (ok, _) ← (Meta.isDefEq specI.type ct.type).run' {}\n"
        "        |>.toIO { fileName := \"<pspec>\", fileMap := default } { env := env }\n"
        "      if !ok then IO.println s!\"MCPROOF_PSPEC_ERR\\tPROMPT_THEOREM_TYPE_MISMATCH\\t{shortN}\"\n"
        "    | _ => IO.println s!\"MCPROOF_PSPEC_ERR\\tPROMPT_DECL_NOT_THEOREM\\t{shortN}\"\n"
    )

    with tempfile.TemporaryDirectory(prefix="mcproof_pspec_") as td:
        tdp = Path(td).resolve()
        cand_f = tdp / "McproofPromptCand.lean"
        cand_o = tdp / "McproofPromptCand.olean"
        drv_f = tdp / "McproofPromptSpecDriver.lean"
        cand_f.write_text(candidate_source, encoding="utf-8")
        drv_f.write_text(drv_src, encoding="utf-8")

        lean_path_parts = [str(tdp)]
        if lib_olean_dir.is_dir():
            lean_path_parts.append(str(lib_olean_dir))
        sysroot_proc = subprocess.run([lean_bin, "--print-libdir"], capture_output=True, text=True, check=False)
        if sysroot_proc.returncode == 0 and sysroot_proc.stdout.strip():
            lean_path_parts.append(sysroot_proc.stdout.strip())
        run_env = dict(env)
        run_env["LEAN_PATH"] = os.pathsep.join(lean_path_parts)

        c_proc = subprocess.run(
            [lean_bin, "-j", "1", "-D", "Elab.async=false", str(cand_f), "-o", str(cand_o)],
            cwd=tdp,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if c_proc.returncode != 0:
            return findings

        d_proc = subprocess.run(
            [lean_bin, "-j", "1", "-D", "Elab.async=false", str(drv_f)],
            cwd=tdp,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if d_proc.returncode != 0:
            tail = " | ".join(ln.strip() for ln in ((d_proc.stdout or "") + "\n" + (d_proc.stderr or "")).splitlines()[-4:] if ln.strip())
            findings.append({
                "line": 1,
                "rule": "PROMPT_THEOREM_TYPE_MISMATCH",
                "message": f"Candidate theorem environment failed prompt statement check: {tail}",
            })
        else:
            for ln in (d_proc.stdout or "").splitlines():
                if ln.startswith("MCPROOF_PSPEC_ERR\t"):
                    parts = ln.split("\t")
                    rule_code = parts[1] if len(parts) > 1 else "PROMPT_THEOREM_TYPE_MISMATCH"
                    thm_id = parts[2] if len(parts) > 2 else "unknown"
                    findings.append({
                        "line": 1,
                        "rule": rule_code,
                        "message": f"Candidate declaration `{thm_id}` does not match prompt theorem statement (`{rule_code}`).",
                    })
    return findings


def verify_lean4_against_challenge(
    challenge_lean: str,
    candidate_source: str,
    *,
    lean_project_dir: Path | None = None,
    timeout_sec: float = 60.0,
) -> list[dict[str, Any]]:
    """Verify via Lean `Meta.isDefEq` that `candidate_source` implements every def/inductive/theorem in `challenge_lean`."""
    proj_dir = (lean_project_dir or (repo_root() / "lean")).resolve()
    lean_bin = find_lean_tool("lean")
    env = _lean_env()
    lib_olean_dir = proj_dir / ".lake" / "build" / "lib" / "lean"
    findings: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="mcproof_chalcmp_") as td:
        tdp = Path(td).resolve()
        spec_f = tdp / "McproofSpecMod.lean"
        spec_o = tdp / "McproofSpecMod.olean"
        cand_f = tdp / "McproofCandMod.lean"
        cand_o = tdp / "McproofCandMod.olean"
        drv_f = tdp / "McproofChalCmpDriver.lean"

        spec_f.write_text(challenge_lean, encoding="utf-8")
        cand_f.write_text(candidate_source, encoding="utf-8")
        drv_f.write_text(CHALLENGE_CMP_DRIVER_TEMPLATE, encoding="utf-8")

        lean_path_parts = [str(tdp)]
        if lib_olean_dir.is_dir():
            lean_path_parts.append(str(lib_olean_dir))
        sysroot_proc = subprocess.run([lean_bin, "--print-libdir"], capture_output=True, text=True, check=False)
        if sysroot_proc.returncode == 0 and sysroot_proc.stdout.strip():
            lean_path_parts.append(sysroot_proc.stdout.strip())
        run_env = dict(env)
        run_env["LEAN_PATH"] = os.pathsep.join(lean_path_parts)

        s_proc = subprocess.run(
            [lean_bin, "-j", "1", "-D", "Elab.async=false", str(spec_f), "-o", str(spec_o)],
            cwd=tdp,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        c_proc = subprocess.run(
            [lean_bin, "-j", "1", "-D", "Elab.async=false", str(cand_f), "-o", str(cand_o)],
            cwd=tdp,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if s_proc.returncode != 0 or c_proc.returncode != 0:
            findings.append({
                "line": 1,
                "rule": "CHALLENGE_COMPARE_BUILD_FAILED",
                "message": "Failed to compile challenge or candidate module for kernel statement comparison.",
            })
            return findings

        cmp_proc = subprocess.run(
            [lean_bin, "-j", "1", "-D", "Elab.async=false", str(drv_f)],
            cwd=tdp,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if cmp_proc.returncode != 0:
            tail = " | ".join(ln.strip() for ln in ((cmp_proc.stdout or "") + "\n" + (cmp_proc.stderr or "")).splitlines()[-4:] if ln.strip())
            findings.append({
                "line": 1,
                "rule": "CHALLENGE_COMPARE_DRIVER_FAILED",
                "message": f"Kernel challenge comparison driver failed: {tail}",
            })
            return findings

        for ln in (cmp_proc.stdout or "").splitlines():
            if ln.startswith("MCPROOF_CMP_ERR\t"):
                parts = ln.split("\t")
                rule_code = parts[1] if len(parts) > 1 else "CHALLENGE_THEOREM_TYPE_MISMATCH"
                decl_name = parts[2] if len(parts) > 2 else "unknown"
                findings.append({
                    "line": 1,
                    "rule": rule_code,
                    "message": f"Candidate failed challenge specification check on `{decl_name}` (`{rule_code}`).",
                })
    return findings


def build_capped_lean_args(
    lean_bin: str,
    target_lean: Path,
    *,
    out_olean: Path | None = None,
    max_memory_mib: int | None = 1400,
) -> list[str]:
    """Construct single-threaded, synchronous, `--trust=0`, memory-capped Lean 4.35 invocation."""
    cmd = [lean_bin, "--trust=0", "-j", "1", "-D", "Elab.async=false"]
    if max_memory_mib is not None and max_memory_mib > 0:
        cmd.extend(["-M", str(int(max_memory_mib))])
    cmd.append(str(target_lean))
    if out_olean is not None:
        cmd.extend(["-o", str(out_olean)])
    return cmd


def classify_host_resource_failure(returncode: int, combined_output: str) -> str | None:
    """Return host-limit diagnostic reason when a Lean failure is OOM/signal/disk rather than mathematical."""
    low = combined_output.lower()
    if returncode in (-9, 137):
        return f"process killed by SIGKILL/OOM (rc={returncode})"
    for marker in (
        "excessive memory consumption",
        "memory allocation failed",
        "out of memory",
        "no space left on device",
        "cannot allocate memory",
    ):
        if marker in low:
            return f"host resource limit triggered ({marker})"
    return None


def scrub_challenge_artifacts(project_dir: Path, challenge_module: str) -> list[str]:
    """Unlink compiled `.olean`/`.ir` artifacts for `challenge_module` so `Spec` always compiles fresh."""
    if not challenge_module:
        return []
    rel_parts = challenge_module.split(".")
    removed: list[str] = []
    for base_sub in (Path(".lake/build/lib/lean"), Path(".lake/build/ir")):
        stem_dir = project_dir / base_sub / Path(*rel_parts[:-1]) if len(rel_parts) > 1 else project_dir / base_sub
        if not stem_dir.is_dir():
            continue
        prefix = rel_parts[-1] + "."
        for item in sorted(stem_dir.iterdir()):
            if item.is_file() and item.name.startswith(prefix):
                item.unlink()
                removed.append(item.relative_to(project_dir).as_posix())
    return removed


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
    env["PATH"] = f"{bin_dir}{os.pathsep}{cur_path}" if cur_path else bin_dir
    return env


def parse_comparator_stdout(
    stdout_text: str,
    solution_module: str,
) -> tuple[list[str], bool, list[dict[str, Any]]]:
    """Parse `lake comparator --paranoid` stdout strictly after the post-build export boundary.

    Prevents candidate `#eval IO.println` spoofing during elaboration from inflating `kernels_accepted`:
    1. Any kernel-acceptance line before `Exporting #[...] from <solution_module>` triggers
       `COMPARATOR_STDOUT_SPOOF_ATTEMPT`.
    2. Only exact full-line `Running ...` followed by exact full-line `... accepts the solution`
       strictly after the export boundary are counted (deduplicated, in order).
    3. Final non-empty stdout line must equal `Your solution is okay!`.
    """
    raw_lines = [ln.strip() for ln in (stdout_text or "").splitlines()]
    export_pat = re.compile(rf"^Exporting #\[.*\] from {re.escape(solution_module)}$")
    accept_set = {acc for _, _, acc in COMPARATOR_ORDERED_KERNELS}

    export_idx = -1
    for idx, ln in enumerate(raw_lines):
        if export_pat.match(ln):
            export_idx = idx

    spoof_findings: list[dict[str, Any]] = []
    pre_export = raw_lines if export_idx < 0 else raw_lines[:export_idx]
    for ln in pre_export:
        if ln in accept_set or ln == "Your solution is okay!":
            spoof_findings.append({
                "line": 1,
                "rule": "COMPARATOR_STDOUT_SPOOF_ATTEMPT",
                "message": f"comparator output marker {ln!r} appeared prior to solution export boundary",
            })
            break

    if export_idx < 0:
        return [], False, spoof_findings

    post_lines = [ln for ln in raw_lines[export_idx + 1 :] if ln]
    kernels_accepted: list[str] = []
    cursor = 0
    for k_label, run_marker, accept_marker in COMPARATOR_ORDERED_KERNELS:
        saw_run = False
        while cursor < len(post_lines):
            cur = post_lines[cursor]
            cursor += 1
            if not saw_run and cur == run_marker:
                saw_run = True
            elif saw_run and cur == accept_marker:
                if k_label not in kernels_accepted:
                    kernels_accepted.append(k_label)
                break

    solution_ok = bool(post_lines) and post_lines[-1] == "Your solution is okay!" and not spoof_findings
    return kernels_accepted, solution_ok, spoof_findings


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
    caveats: tuple[str, ...] = ()
    challenge_sorry_whitelisted_module: str | None = None
    host_resource_exhausted: bool = False

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
            "caveats": list(self.caveats),
            "challenge_sorry_whitelisted_module": self.challenge_sorry_whitelisted_module,
            "host_resource_exhausted": self.host_resource_exhausted,
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
    timeout_sec: float = 120,
    max_memory_mib: int | None = 1400,
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

        comp_cmd = build_capped_lean_args(
            lean_bin,
            cand_lean,
            out_olean=cand_olean,
            max_memory_mib=max_memory_mib,
        )
        try:
            comp = subprocess.run(
                comp_cmd,
                cwd=tmp_dir,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            findings.append({
                "line": 1,
                "rule": "HOST_RESOURCE_EXHAUSTED",
                "message": f"Lean elaboration timed out after {timeout_sec}s ({exc})",
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
                host_resource_exhausted=True,
            )
        combined_out = (comp.stdout or "") + "\n" + (comp.stderr or "")
        if comp.returncode != 0:
            host_reason = classify_host_resource_failure(comp.returncode, combined_out)
            if host_reason is not None:
                findings.append({
                    "line": 1,
                    "rule": "HOST_RESOURCE_EXHAUSTED",
                    "message": host_reason,
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
                    host_resource_exhausted=True,
                )
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
    allow_unsandboxed: bool = False,
    timeout_sec: int = 300,
) -> LeanVerificationResult:
    """Run full 6-kernel `lake comparator --paranoid` + `collectAxioms` + source escape-hatch checks on a Lake project."""
    proj = (project_dir or (repo_root() / "lean")).resolve()
    toolchain = _read_toolchain(proj)
    lean_bin = find_lean_tool("lean")
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
    solution_mod = str(cmp_cfg.get("solution_module", "Mcproof.Proofs"))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", solution_mod):
        return LeanVerificationResult(
            passed=False,
            toolchain=toolchain,
            theorems_checked=(),
            axioms_used=(),
            nonstandard_axioms=(),
            sorry_declarations=(),
            paranoid_kernels_run=(),
            sandboxed=False,
            findings=({"line": 1, "rule": "INVALID_SOLUTION_MODULE", "message": f"invalid solution_module {solution_mod!r}"},),
        )
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

    # Fail closed before compiling untrusted Lean code when Linux bubblewrap is unavailable unless explicitly opted in
    bwrap_available = linux_bwrap_functional()
    caveats: list[str] = []
    if not bwrap_available:
        if not allow_unsandboxed:
            findings.append({
                "line": 1,
                "rule": "SANDBOX_UNAVAILABLE",
                "message": (
                    "Linux bubblewrap (`bwrap`) is unavailable on this host; "
                    "pass allow_unsandboxed=True or `--allow-unsandboxed` to explicitly authorize unsandboxed execution"
                ),
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
                caveats=(),
                challenge_sorry_whitelisted_module=challenge_mod or None,
            )
        caveats.append("UNSANDBOXED_EXECUTION")

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

    # Scrub challenge `.olean`/`.ir` before `lake build` so `Spec` always compiles fresh from disk
    scrub_challenge_artifacts(proj, challenge_mod)

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
            sandboxed=bwrap_available,
            findings=tuple(findings),
            caveats=tuple(caveats),
            challenge_sorry_whitelisted_module=challenge_mod or None,
        )

    # Measure actual transitive kernel axioms and sorry dependencies on solution_module via `collectAxioms`
    measured_axioms: set[str] = set()
    sorry_decls: list[str] = []
    nonstd: list[str] = []
    lib_olean_dir = proj / ".lake" / "build" / "lib" / "lean"
    with tempfile.TemporaryDirectory(prefix="mcproof_proj_ax_") as ax_tmp_str:
        ax_tmp = Path(ax_tmp_str)
        audit_driver = ax_tmp / "McproofProjectAxiomDriver.lean"
        audit_driver.write_text(
            MODULE_AXIOM_AUDIT_TEMPLATE.format(module_name=solution_mod),
            encoding="utf-8",
        )
        ax_env = dict(env)
        lean_path_parts = [str(ax_tmp)]
        if lib_olean_dir.is_dir():
            lean_path_parts.append(str(lib_olean_dir))
        ax_env["LEAN_PATH"] = os.pathsep.join(lean_path_parts)
        ax_run = subprocess.run(
            [lean_bin, str(audit_driver)],
            cwd=ax_tmp,
            env=ax_env,
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
                "message": f"trusted collectAxioms driver failed on {solution_mod}: {tail}",
            })
        else:
            for line in (ax_run.stdout or "").splitlines():
                if not line.startswith("MCPROOF_AUDIT\t"):
                    continue
                parts = line.split("\t")
                if len(parts) != 5:
                    continue
                _, kind, _, decl_name, ax_csv = parts
                axs = {a for a in ax_csv.split(",") if a}
                measured_axioms.update(axs)
                if kind in ("axiom", "opaque"):
                    findings.append({
                        "line": 1,
                        "rule": "KERNEL_EXTRA_AXIOM_OR_OPAQUE",
                        "message": f"solution module {solution_mod} contains {kind} declaration '{decl_name}'",
                    })
                if "sorryAx" in axs:
                    sorry_decls.append(decl_name)
                    findings.append({
                        "line": 1,
                        "rule": "KERNEL_SORRY_AXIOM",
                        "message": f"solution declaration '{decl_name}' depends on 'sorryAx'",
                    })
                extra_axs = axs - (permitted & STANDARD_AXIOMS) - {"sorryAx"}
                if extra_axs:
                    nonstd.extend(sorted(extra_axs))
                    findings.append({
                        "line": 1,
                        "rule": "KERNEL_NONSTANDARD_AXIOM",
                        "message": f"solution declaration '{decl_name}' uses unpermitted axioms: {sorted(extra_axs)}",
                    })

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
    kernels_accepted, solution_ok, spoof_findings = parse_comparator_stdout(cmp_res.stdout or "", solution_mod)
    findings.extend(spoof_findings)

    cmp_out = (cmp_res.stdout or "") + "\n" + (cmp_res.stderr or "")
    if cmp_res.returncode != 0 or not solution_ok:
        if "sorryAx" in cmp_out and "sorryAx" not in sorry_decls:
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
        and solution_ok
        and len(kernels_accepted) == 6
    )
    return LeanVerificationResult(
        passed=passed,
        toolchain=toolchain,
        theorems_checked=theorem_names,
        axioms_used=tuple(sorted(measured_axioms - {"sorryAx"})),
        nonstandard_axioms=tuple(sorted(set(nonstd))),
        sorry_declarations=tuple(sorted(set(sorry_decls))),
        paranoid_kernels_run=tuple(kernels_accepted),
        sandboxed=bwrap_available,
        findings=tuple(findings),
        caveats=tuple(caveats),
        challenge_sorry_whitelisted_module=challenge_mod or None,
    )
