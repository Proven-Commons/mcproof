"""Targeted Plane 1 section retrieval and label-free multi-turn Tier 2 repair loop (`mcproof#5`).

Implements three architectural guarantees:
1. Targeted Plane 1 section retrieval (`<= 1,500` tokens matched to Family A-D, prompt keywords,
   and prior-turn failure rules, with automatic chunk rotation when stagnation is detected).
2. Strict separation between the **label-free inference-time oracle** (`default_inference_oracle`,
   which sees ONLY `family` and `prompt` and drives Turn `1..k` diagnostics and early stopping with
   zero access to `expected_tier`, `valid_cases`, `planted_mutations`, or ground-truth harness files)
   and the **post-hoc benchmark grader** (`eval_grader_fn`, which scores deployed outputs at budgets
   `k = 1..max_turns` without ever feeding ground-truth labels or verdicts back to the model).
3. Completion/AST hash (`compute_candidate_state_hash`) and `(rule, line)` failure-signature
   (`compute_failure_signature`) stagnation detection across turns `1..k`, switching Plane 1
   reference chunks and structural framing whenever `temperature = 0.0` repeats a visited state.
"""

from __future__ import annotations

import ast
import base64
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence
import urllib.request

from .lean_harness import (
    BAR_FORBIDDEN_RULES,
    THEOREM_DECL_RE,
    CandidateSandboxUnavailable,
    _lean_env,
    linux_bwrap_functional,
    run_confined_command,
    strip_lean_comments_and_strings,
    verify_lean4_against_challenge,
    verify_lean4_project_comparator,
    verify_lean4_prompt_obligations,
    verify_pinned_lean_defs,
)
from .oracles import (
    FENCED_BLOCK_RE,
    OracleReceipt,
    SHA40_RE,
    extract_fenced_blocks,
    grade_family_completion,
    run_checker_oracle,
    run_claim_hygiene_oracle,
    run_lean4_oracle,
    run_prose_and_mixed_zone_oracle,
    run_verdicts_oracle,
    sanitize_verdict_id,
)
from .paths import dep_repo, find_lean_tool, repo_root

MAX_RETRIEVAL_TOKENS_HARD_CAP = 1500
QWEN35_STOP_TOKENS: tuple[str, ...] = ("<|im_end|>", "<|endoftext|>")
WORD_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\sA-Za-z0-9_]")
HEX_LITERAL_RE = re.compile(r"\b[0-9a-fA-F]{16,64}\b")
QUOTED_PAYLOAD_RE = re.compile(r"('[^'\n]{12,}'|\"[^\"\n]{12,}\")")
DICT_LIST_LITERAL_RE = re.compile(r"(\{[^{}\n]{8,}\}|\[[^\[\]\n]{12,}\])")
EXPECTED_COMPARISON_RE = re.compile(r"(?i)\b(!=\s*expected\b|expected[ _-]*tier\s*[:=]?\s*['\"]?[A-Z_]+|expected[ _-]*verdict\s*[:=]?\s*['\"]?[A-Z_]+)")
LEAN_THM_NAME_RE = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_.']*)\b")
PY_DEF_NAME_RE = re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


@dataclass(frozen=True)
class Plane1Chunk:
    """Single retrievable subsection of `spec/plane1_formal_spec.md`."""

    chunk_id: str
    section_num: int
    heading: str
    body: str
    est_tokens: int
    keywords: frozenset[str]


def estimate_tokens_conservative(text: str) -> int:
    """Conservative upper-bound token count safe for Qwen3.5 and cl100k_base without network calls."""
    if not text:
        return 0
    utf8_len = len(text.encode("utf-8"))
    lex_pieces = len(WORD_TOKEN_RE.findall(text))
    by_bytes = (utf8_len + 2) // 3
    est = max(lex_pieces, by_bytes)
    try:
        import tiktoken  # type: ignore[import-not-found]

        enc = tiktoken.get_encoding("cl100k_base")
        est = max(est, int(len(enc.encode(text)) * 1.08) + 4)
    except ImportError:
        est = est + 4
    return est


def parse_plane1_chunks(spec_path: Path | None = None) -> list[Plane1Chunk]:
    """Split `spec/plane1_formal_spec.md` along `##` / `###` / `####` headings into retrievable chunks."""
    target = spec_path or (repo_root() / "spec" / "plane1_formal_spec.md")
    raw_lines = target.read_text(encoding="utf-8").splitlines()

    chunks: list[Plane1Chunk] = []
    cur_sec_num = 0
    cur_h2 = ""
    cur_heading = "Overview"
    cur_buf: list[str] = []

    def _flush() -> None:
        text = "\n".join(cur_buf).strip()
        if not text:
            return
        full_text = f"{cur_heading}\n{text}" if not text.startswith("#") else text
        words = {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", full_text)}
        cid = f"sec{cur_sec_num}_{len(chunks):02d}"
        chunks.append(
            Plane1Chunk(
                chunk_id=cid,
                section_num=cur_sec_num,
                heading=f"{cur_h2} / {cur_heading}".strip(" /"),
                body=full_text,
                est_tokens=estimate_tokens_conservative(full_text),
                keywords=frozenset(words),
            )
        )

    for line in raw_lines:
        m2 = re.match(r"^##\s+(\d+)\.\s+(.*)$", line)
        if m2:
            _flush()
            cur_buf = [line]
            cur_sec_num = int(m2.group(1))
            cur_h2 = f"{cur_sec_num}. {m2.group(2).strip()}"
            cur_heading = cur_h2
            continue
        if line.startswith("### ") or line.startswith("#### "):
            _flush()
            cur_buf = [line]
            cur_heading = line.lstrip("#").strip()
            continue
        cur_buf.append(line)
    _flush()
    return chunks


FAMILY_PRIMARY_SECTIONS: dict[str, tuple[int, ...]] = {
    "A": (9, 4, 12, 13),
    "B": (5, 6, 11, 12),
    "C": (8, 7, 3),
    "D": (10, 7, 9),
}

RULE_TO_SECTION_BOOST: dict[str, tuple[int, ...]] = {
    "FORBIDDEN_SORRY": (9,),
    "FORBIDDEN_ADMIT": (9,),
    "FORBIDDEN_AXIOM": (9,),
    "FORBIDDEN_NATIVE_DECIDE": (9,),
    "LEAN_COMPILE": (9, 12, 13),
    "WEAK_STATEMENT": (4,),
    "VACUOUS": (4,),
    "MISSING_THEOREM": (9, 4),
    "FLOAT": (6,),
    "BARE_ASSERT": (5, 6),
    "SKELETON": (5,),
    "NON_VACUOUS": (5, 11),
    "MISSING_SECTION": (7, 10),
    "CLAIM_TIER": (8, 7),
    "INFLATED": (8,),
    "PROMPT_EVIDENCE_CONTRADICTION": (8, 7),
    "VERDICT": (8,),
    "F0_": (8, 3),
    "MISSING_DATA_EIDO_SKIP": (10,),
    "PROSE": (10, 7),
}


def retrieve_plane1_excerpt(
    *,
    family: str,
    prompt_text: str,
    prior_findings: Sequence[Mapping[str, Any]] = (),
    max_tokens: int = 1250,
    spec_path: Path | None = None,
    exclude_chunk_ids: Sequence[str] = (),
    prefer_worked_examples: bool = False,
) -> dict[str, Any]:
    """Retrieve a focused `<= 1,500`-token Plane 1 excerpt tailored to `family`, prompt, and errors."""
    budget = min(max(250, int(max_tokens)), MAX_RETRIEVAL_TOKENS_HARD_CAP)
    fam = family.strip().upper()
    if fam not in FAMILY_PRIMARY_SECTIONS:
        raise ValueError(f"unsupported family {family!r} (expected A, B, C, or D)")

    excluded = set(exclude_chunk_ids)
    chunks = parse_plane1_chunks(spec_path)
    prompt_words = {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", prompt_text)}

    boosted_sections: dict[int, int] = {}
    for rank_idx, sec in enumerate(FAMILY_PRIMARY_SECTIONS[fam]):
        boosted_sections[sec] = max(boosted_sections.get(sec, 0), 40 - rank_idx * 8)

    if prefer_worked_examples:
        boosted_sections[12] = boosted_sections.get(12, 0) + 32
        boosted_sections[13] = boosted_sections.get(13, 0) + 32

    error_words: set[str] = set()
    for f in prior_findings:
        rule_up = str(f.get("rule", "")).upper()
        error_words.update(w.lower() for w in re.findall(r"[A-Za-z]{3,}", rule_up))
        for pat, secs in RULE_TO_SECTION_BOOST.items():
            if pat in rule_up:
                for s_num in secs:
                    boosted_sections[s_num] = boosted_sections.get(s_num, 0) + 35

    scored: list[tuple[int, int, Plane1Chunk]] = []
    for idx, ch in enumerate(chunks):
        if ch.est_tokens > budget:
            continue
        sec_score = boosted_sections.get(ch.section_num, 0)
        kw_overlap = len(prompt_words & ch.keywords) * 4 + len(error_words & ch.keywords) * 6
        if prefer_worked_examples:
            style_bonus = 18 if any(w in ch.heading for w in ("Reference Proof", "Pattern", "Worked", "Algorithm")) else 0
            repeat_penalty = -30 if ch.chunk_id in excluded else 0
        else:
            style_bonus = 12 if any(w in ch.heading for w in ("Checklist", "Template", "Forbidden", "Rules", "Playbook", "Matrix")) else 0
            repeat_penalty = -10 if ch.chunk_id in excluded else 0
        total_score = sec_score + kw_overlap + style_bonus + repeat_penalty
        if total_score > 0:
            scored.append((total_score, -idx, ch))

    scored.sort(reverse=True)
    candidate_pool = (
        [entry for entry in scored if entry[2].chunk_id not in excluded]
        if excluded
        else list(scored)
    )
    if not candidate_pool:
        candidate_pool = list(scored)

    header = f"### Plane 1 Reference Rules (Family {fam})\n"
    used_tokens = estimate_tokens_conservative(header) + 12
    selected: list[Plane1Chunk] = []
    seen_ids: set[str] = set()

    for _score, _neg_idx, ch in candidate_pool:
        if ch.chunk_id in seen_ids:
            continue
        sep_cost = 4
        if used_tokens + ch.est_tokens + sep_cost > budget:
            continue
        selected.append(ch)
        seen_ids.add(ch.chunk_id)
        used_tokens += ch.est_tokens + sep_cost

    selected.sort(key=lambda c: c.chunk_id)
    excerpt_body = header + "\n\n".join(c.body for c in selected)
    final_est = estimate_tokens_conservative(excerpt_body)

    while final_est > MAX_RETRIEVAL_TOKENS_HARD_CAP and selected:
        selected.pop()
        excerpt_body = header + "\n\n".join(c.body for c in selected)
        final_est = estimate_tokens_conservative(excerpt_body)

    return {
        "family": fam,
        "excerpt": excerpt_body,
        "text": excerpt_body,
        "context": excerpt_body,
        "estimated_tokens": final_est,
        "max_tokens_cap": MAX_RETRIEVAL_TOKENS_HARD_CAP,
        "chunk_ids": [c.chunk_id for c in selected],
        "headings": [c.heading for c in selected],
        "rotated_for_stagnation": prefer_worked_examples,
    }


def retrieve_plane1_sections(
    family: str,
    prompt: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    spec_path: Path | None = None,
    max_tokens: int = 1250,
    exclude_chunk_ids: Sequence[str] = (),
    prefer_worked_examples: bool = False,
) -> dict[str, Any]:
    """Bridge-compatible Plane 1 retriever (`<= 1,500` tokens) returning `text` and metadata."""
    return retrieve_plane1_excerpt(
        family=family,
        prompt_text=prompt,
        prior_findings=findings,
        max_tokens=max_tokens,
        spec_path=spec_path,
        exclude_chunk_ids=exclude_chunk_ids,
        prefer_worked_examples=prefer_worked_examples,
    )


# Stagnation State Deduplication (AST / Normalized Hash + Failure Signature) --

def _strip_lean_comments(src: str) -> str:
    return " ".join(strip_lean_comments_and_strings(src).split())


def compute_candidate_state_hash(family: str, completion_text: str) -> str:
    """Compute a formatting-invariant AST or token-normalized SHA-256 for stagnation detection."""
    fam = family.strip().upper()
    if fam == "B":
        py_blocks = extract_fenced_blocks(completion_text, ("python", "py"))
        py_src = py_blocks[-1] if py_blocks else completion_text
        try:
            tree = ast.parse(py_src)
            norm = ast.dump(tree, include_attributes=False)
            return hashlib.sha256(norm.encode("utf-8")).hexdigest()
        except SyntaxError:
            return hashlib.sha256(" ".join(py_src.split()).encode("utf-8")).hexdigest()

    if fam in ("A", "D"):
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        if lean_blocks:
            lean_norm = "\n".join(_strip_lean_comments(b) for b in lean_blocks)
            prose_norm = " ".join(completion_text.split()) if fam == "D" else ""
            return hashlib.sha256((lean_norm + "\n" + prose_norm).encode("utf-8")).hexdigest()

    return hashlib.sha256(" ".join(completion_text.split()).encode("utf-8")).hexdigest()


def compute_failure_signature(findings: Sequence[Mapping[str, Any]]) -> str:
    """Canonical SHA-256 over sorted `(rule, line)` pairs to detect deterministic error plateaus."""
    if not findings:
        return "PASS"
    pairs = sorted(
        {
            (str(f.get("rule", "FINDING")).upper(), int(f["line"]) if ("line" in f and f["line"] is not None) else -1)
            for f in findings
        }
    )
    raw = json.dumps(pairs, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


# Zero-Leakage Diagnostic Sanitizer & Label-Free Inference Oracle -------------

def sanitize_oracle_diagnostics(
    family: str,
    findings: Sequence[Mapping[str, Any]],
    *,
    max_items: int = 8,
) -> list[dict[str, str]]:
    """Extract minimal structured Tier 2 diagnostics while scrubbing fixtures and expected labels."""
    fam = family.strip().upper()
    cleaned: list[dict[str, str]] = []

    for raw in list(findings)[:max_items]:
        rule = str(raw.get("rule", "ORACLE_FINDING")).strip() or "ORACLE_FINDING"
        if rule.upper() in ("EXPECTED_TIER_MISMATCH", "VERDICT_MISMATCH", "F0_TIER_BUCKET_MISMATCH"):
            # Defense in depth: never surface ground-truth expected label comparisons even if passed in
            continue
        msg = str(raw.get("message", "")).strip()
        line_no = raw.get("line")

        # Strip any accidental `!= expected '...'` substring and prompt-injection fences/mentions
        msg = EXPECTED_COMPARISON_RE.sub("<redacted-expected>", msg)
        msg = msg.replace("```", "'''")
        msg = re.sub(r"@([A-Za-z0-9_-]+)", r"at_\1", msg)
        msg = msg.replace("<script", "[script").replace("</script", "[/script")

        if fam == "B":
            msg = DICT_LIST_LITERAL_RE.sub("<redacted-fixture>", msg)
            msg = QUOTED_PAYLOAD_RE.sub("<redacted-literal>", msg)
            msg = HEX_LITERAL_RE.sub("<redacted-hex>", msg)
            if "valid_case" in rule.lower() or "valid case" in msg.lower():
                m_cnt = re.search(r"(\d+\s*/\s*\d+)", msg)
                ratio_note = f" ({m_cnt.group(1)})" if m_cnt else ""
                msg = f"Checker rejected valid specification test case{ratio_note}; check exact integer/Fraction invariants."
            elif "mutation" in rule.lower() or "planted" in msg.lower() or "kill" in msg.lower():
                m_cnt = re.search(r"(\d+\s*/\s*\d+)", msg)
                ratio_note = f" ({m_cnt.group(1)})" if m_cnt else ""
                msg = f"Checker failed >=80% planted-bug mutation kill floor{ratio_note}; verify all certificate conditions independently."
        else:
            msg = re.sub(r"(/[A-Za-z0-9._-]+){2,}/([A-Za-z0-9._-]+\.(?:lean|py|md|json))", r"\2", msg)

        msg_one_line = " ".join(msg.split())[:260]
        entry: dict[str, str] = {"rule": rule, "diagnostic": msg_one_line}
        if line_no is not None:
            entry["line"] = str(line_no)
        cleaned.append(entry)

    return cleaned


def format_diagnostics(
    findings: Sequence[Mapping[str, Any]],
    *,
    family: str = "",
) -> str:
    """Format sanitized, zero-fixture-leak Tier 2 diagnostics into compact multi-turn repair text."""
    inferred_fam = family.strip().upper()
    if not inferred_fam:
        joined_rules = " ".join(str(f.get("rule", "")) for f in findings).upper()
        if any(k in joined_rules for k in ("MUTATION", "VALID_CASE", "FLOAT", "SKELETON", "CHECKER", "ENTRY_FN")):
            inferred_fam = "B"
        elif "EIDO_SKIP" in joined_rules or "EMBEDDED_LEAN" in joined_rules:
            inferred_fam = "D"
        elif any(k in joined_rules for k in ("CLAIM", "VERDICT", "F0_", "BAR_", "PROMPT_EVIDENCE")):
            inferred_fam = "C"
        else:
            inferred_fam = "A"
    sanitized = sanitize_oracle_diagnostics(inferred_fam, findings)
    if not sanitized:
        return "Tier 2 deterministic oracle rejected the candidate with unspecified error."
    lines = [f"Tier 2 deterministic oracle diagnostics (Family {inferred_fam}, {len(sanitized)} item(s)):"]
    for idx, d in enumerate(sanitized, start=1):
        loc = f" (line {d['line']})" if "line" in d else ""
        lines.append(f"{idx}. [{d['rule']}]{loc}: {d['diagnostic']}")
    return "\n".join(lines)


def _check_prompt_shas_preserved(prompt_text: str, completion_text: str) -> list[dict[str, Any]]:
    """Verify any 40-char commit SHA stated in the prompt is not truncated or dropped when SHAs are required."""
    prompt_shas = sorted({m.lower() for m in SHA40_RE.findall(prompt_text)})
    if not prompt_shas:
        return []
    comp_shas = {m.lower() for m in SHA40_RE.findall(completion_text)}
    missing = [s for s in prompt_shas if s not in comp_shas]
    if missing:
        return [
            {
                "rule": "MISSING_PROMPT_COMMIT_SHA40",
                "message": "Completion omitted or truncated the 40-hex source commit SHA given in the prompt.",
            }
        ]
    return []


def _audit_family_c_inference_only(prompt_text: str, completion_text: str) -> dict[str, Any]:
    """100% label-free Family C inference check using ONLY prompt text and public schema validators."""
    lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
    has_valid_lean = False
    findings: list[dict[str, Any]] = []
    if lean_blocks:
        l_rec = run_lean4_oracle("\n\n".join(lean_blocks), strict_init_only=True)
        has_valid_lean = l_rec.passed
        if not l_rec.passed:
            findings.extend(l_rec.findings)

    # Label-free claim hygiene (`expected_tier=None`)
    hyg = run_claim_hygiene_oracle(
        completion_text,
        expected_tier=None,
        has_kernel_proof=has_valid_lean,
    )
    findings.extend(hyg.findings)
    declared_tier = str(hyg.checks.get("declared_tier") or "").upper()

    # Check prompt-visible epistemic contradictions without reading `expected_tier`
    p_low = prompt_text.lower()
    prompt_signals_unproved = any(
        sig in p_low
        for sig in (
            "uses `sorry`",
            "contains `sorry`",
            "with `sorry`",
            "admit",
            "native_decide",
            "no formal proof",
            "without a proof",
            "heuristic",
            "conjecture",
            "sampled",
            "monte carlo",
        )
    )
    if prompt_signals_unproved and declared_tier == "PROVEN" and not has_valid_lean:
        findings.append(
            {
                "rule": "PROMPT_EVIDENCE_CONTRADICTION",
                "message": "Prompt describes unproved, heuristic, or sorry-containing evidence; cannot claim PROVEN.",
            }
        )
    if ('"stale": true' in p_low or "status = \"in-progress\"" in p_low or "no specification approval" in p_low) and re.search(
        r"(?im)^status\s*:\s*verified\b", completion_text
    ):
        findings.append(
            {
                "rule": "PROMPT_STATUS_INFLATION",
                "message": "Prompt indicates in-progress or stale status without approval; cannot declare 'Status: verified'.",
            }
        )

    # Validate any fenced JSON block against public verdict / F0 schemas (zero expected-value lookup)
    json_blocks = extract_fenced_blocks(completion_text, ("json",))
    if ("```json" in prompt_text or "verdict" in p_low or "chart_bucket" in p_low) and not json_blocks:
        if "json" in p_low:
            findings.append(
                {
                    "rule": "MISSING_REQUIRED_JSON_BLOCK",
                    "message": "Prompt requests a structured ```json block.",
                }
            )
    for jb in json_blocks:
        try:
            parsed = json.loads(jb)
        except ValueError as exc:
            findings.append({"rule": "INVALID_JSON_BLOCK", "message": str(exc)})
            continue
        if not isinstance(parsed, dict):
            continue
        if "verdict" in parsed and "source_commit" in parsed:
            raw_id = parsed.get("id", "verdict_01")
            vid = sanitize_verdict_id(raw_id)
            if vid is None:
                findings.append({"rule": "INVALID_VERDICT_ID", "message": f"unsafe verdict id: {raw_id!r}"})
            else:
                with tempfile.TemporaryDirectory(prefix="mcproof_inf_v_") as td:
                    vf = Path(td).resolve() / f"{vid}.json"
                    vf.write_text(jb, encoding="utf-8", newline="\n")
                    v_rep = run_verdicts_oracle(vf)
                    if not v_rep.passed:
                        findings.extend(v_rep.findings)
            findings.extend(_check_prompt_shas_preserved(prompt_text, jb))
        elif "record" in parsed or "chart_bucket" in parsed:
            rec_d = parsed.get("record")
            bucket = parsed.get("chart_bucket")
            if not isinstance(rec_d, dict) or bucket not in ("claimed", "verified"):
                findings.append(
                    {
                        "rule": "F0_SCHEMA_ERROR",
                        "message": "F0 JSON wrapper requires 'record' object and 'chart_bucket' in {'claimed', 'verified'}.",
                    }
                )
            else:
                if bucket == "claimed" and rec_d.get("verify") is not None:
                    findings.append(
                        {
                            "rule": "F0_CLAIMED_HAS_VERIFY_BLOCK",
                            "message": "chart_bucket='claimed' records must not carry an unverified 'verify' block.",
                        }
                    )
                if bucket == "verified" and rec_d.get("stale") is True:
                    findings.append(
                        {
                            "rule": "F0_STALE_IN_VERIFIED_BUCKET",
                            "message": "stale=True records belong in quarantine, never chart_bucket='verified'.",
                        }
                    )
                kn = rec_d.get("kappa_num")
                kd = rec_d.get("kappa_den")
                kdec = rec_d.get("kappa_decimal")
                if isinstance(kn, int) and isinstance(kd, int) and kd > 0 and isinstance(kdec, str):
                    exact_rat = Decimal(kn) / Decimal(kd)
                    try:
                        given_dec = Decimal(kdec)
                        if abs(exact_rat - given_dec) > Decimal("1e-14"):
                            findings.append(
                                {
                                    "rule": "F0_KAPPA_DECIMAL_MISMATCH",
                                    "message": "kappa_decimal does not match exact kappa_num / kappa_den to 15 significant digits.",
                                }
                            )
                    except ArithmeticError:
                        findings.append({"rule": "F0_INVALID_KAPPA_DECIMAL", "message": "unparseable kappa_decimal"})

    passed = len(findings) == 0
    return {
        "passed": passed,
        "epistemic_status": declared_tier if (passed and declared_tier) else ("VERIFIED" if passed else "REJECTED"),
        "findings": findings,
    }


def default_inference_oracle(
    item_public_view: Mapping[str, Any],
    completion_text: str,
) -> dict[str, Any]:
    """100% label-free inference-time Tier 2 oracle (`mcproof#5`).

    Reads ONLY `item_public_view['family']` and `item_public_view['prompt']`.
    Never accesses `expected_tier`, `valid_cases`, `planted_mutations`, `harness_path`,
    `target_path`, `expected_verdict`, or `expected_f0_tier`.
    """
    fam = str(item_public_view["family"]).strip().upper()
    prompt_text = str(item_public_view.get("prompt", ""))

    if fam == "A":
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        lean_src = "\n\n".join(lean_blocks) if lean_blocks else completion_text
        rec = run_lean4_oracle(
            lean_src,
            strict_init_only=True,
            check_vacuous=True,
            require_theorem=True,
        )
        findings = [dict(f) for f in rec.findings]
        prompt_lean_blocks = extract_fenced_blocks(prompt_text, ("lean", "lean4"))
        if prompt_lean_blocks:
            findings.extend(verify_pinned_lean_defs("\n\n".join(prompt_lean_blocks), lean_src))
        findings.extend(
            verify_lean4_prompt_obligations(
                prompt_text,
                lean_src,
                fenced_prompt_lean=prompt_lean_blocks,
                run_kernel_type_check=rec.passed,
            )
        )
        passed = rec.passed and len(findings) == 0
        return {
            "passed": passed,
            "epistemic_status": "PROVEN" if passed else "REJECTED",
            "findings": findings,
        }

    if fam == "B":
        py_blocks = extract_fenced_blocks(completion_text, ("python", "py"))
        py_src = py_blocks[-1] if py_blocks else completion_text
        prompt_py_blocks = extract_fenced_blocks(prompt_text, ("python", "py"))
        gen_spec_src = prompt_py_blocks[0] if prompt_py_blocks else None

        prose_outside_fences = FENCED_BLOCK_RE.sub("", prompt_text)
        verify_cands = re.findall(r"\b(verify[A-Za-z0-9_]*)\s*\(", prose_outside_fences)
        check_cands = re.findall(r"\b(check[A-Za-z0-9_]*)\s*\(", prose_outside_fences)
        expected_fn = verify_cands[0] if verify_cands else (check_cands[0] if check_cands else "verify")

        rec_b = run_checker_oracle(
            py_src,
            generator_or_spec_source=gen_spec_src,
            entry_fn=expected_fn,
            valid_cases=(),
            planted_mutations=None,
            strict_exact_math=True,
            allow_static_lint_only=True,
        )
        findings_b = [dict(f) for f in rec_b.findings]
        if not re.search(rf"\bdef\s+{re.escape(expected_fn)}\s*\(", py_src):
            findings_b.append(
                {
                    "rule": "MISSING_ENTRY_FUNCTION",
                    "message": f"Python checker must define entry function `def {expected_fn}(...):`.",
                }
            )
        passed_b = rec_b.passed and len(findings_b) == 0
        return {
            "passed": passed_b,
            "epistemic_status": "LINT_PASS" if passed_b else "REJECTED",
            "findings": findings_b,
        }

    if fam == "C":
        return _audit_family_c_inference_only(prompt_text, completion_text)

    if fam == "D":
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        if not lean_blocks:
            return {
                "passed": False,
                "epistemic_status": "REJECTED",
                "findings": [{"rule": "MISSING_EMBEDDED_LEAN_BLOCK", "message": "Family D response must include a fenced ```lean block."}],
            }
        mixed = run_prose_and_mixed_zone_oracle(
            completion_text,
            require_formal_sections=True,
            require_data_eido_skip=True,
            verify_embedded_lean=True,
            verify_verdict_shas=True,
        )
        findings_d = [dict(f) for f in mixed.findings]
        findings_d.extend(_check_prompt_shas_preserved(prompt_text, completion_text))
        passed_d = mixed.passed and len(findings_d) == 0
        return {
            "passed": passed_d,
            "epistemic_status": mixed.epistemic_status if passed_d else "REJECTED",
            "findings": findings_d,
        }

    raise ValueError(f"unsupported prompt family {fam!r} (expected A, B, C, or D)")


def build_repair_turn_prompt(
    *,
    family: str,
    original_prompt: str,
    plane1_excerpt: str,
    turn_index: int,
    prior_completion: str | None = None,
    sanitized_diagnostics: Sequence[Mapping[str, str]] = (),
    stagnation_detected: bool = False,
    refuted_routes: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Construct the bounded user prompt for turn `turn_index` (`1`-indexed)."""
    fam = family.strip().upper()
    format_directive = {
        "A": "Return a complete stock-`Init` Lean 4.35.0 solution inside a ```lean fenced block with zero `sorry`, `admit`, `axiom`, or `native_decide`.",
        "B": "Return a standalone Python 3 exact-math checker inside a ```python fenced block using `int`/`fractions.Fraction` only, zero `float`, zero `/` true-division, and zero bare `assert`.",
        "C": "Return the audited formal response with explicit honest tier (`PROVEN`, `VERIFIED`, `KNOWN`, `CONJECTURE`, or `REFUSED`) and non-empty `## What is not proved` and `## What you must trust` sections.",
        "D": "Return the mixed-register Markdown document keeping `<div data-eido-skip=\"true\">...</div>` intact, a valid ```lean proof block, plain-language prose (no em dashes, no outcome forecasts, paragraphs <=420 chars), and `## What is not proved` + `## What you must trust`.",
    }[fam]

    if turn_index <= 1 or not sanitized_diagnostics:
        return (
            f"{plane1_excerpt}\n\n"
            f"### Task\n{original_prompt.strip()}\n\n"
            f"### Output Contract\n{format_directive}"
        )

    diag_lines = "\n".join(
        f"- [{d['rule']}" + (f":L{d['line']}" if "line" in d else "") + f"] {d['diagnostic']}"
        for d in sanitized_diagnostics
    )

    if stagnation_detected:
        # State-deduplication escape: omit verbatim broken draft so deterministic decoding does not copy it back!
        reset_strategy = {
            "A": "Do NOT repeat the previous proof script. State explicit helper lemmas over `Nat`/`Int` using structural `induction` + `omega` + `Nat.mul_add`/`Int.add_assoc` instead of unavailable Mathlib tactics.",
            "B": "Do NOT repeat the previous checker skeleton. Construct a clean, independent certificate verifier checking types (`isinstance(v, int) and not isinstance(v, bool)`), domain bounds, and exact `Fraction` equations from scratch.",
            "C": "Do NOT repeat the previous draft. Re-derive the claim tier directly from the evidence in the prompt, verify every 40-hex SHA and JSON field verbatim, and write concrete `## What is not proved` and `## What you must trust` bullets.",
            "D": "Do NOT repeat the previous draft. Emit short plain paragraphs (<=350 chars, zero em dashes or semicolons), `<div data-eido-skip=\"true\">` around formal metadata, a self-contained stock-`Init` ```lean proof, and both boundary sections.",
        }[fam]
        obstruction_note = ""
        if refuted_routes:
            ob_lines = "\n".join(
                f"- Turn {r['turn']} (`state={r['state_hash']}`, primary rule `{r['primary_rule']}`)"
                for r in list(refuted_routes)[-4:]
            )
            obstruction_note = f"### Refuted Routes (Do Not Re-Explore)\n{ob_lines}\n\n"
        return (
            f"{plane1_excerpt}\n\n"
            f"### Task\n{original_prompt.strip()}\n\n"
            f"### Stagnation Escape Alert (Turn {turn_index})\n"
            f"Your previous attempt reproduced an already-rejected AST or identical error signature:\n{diag_lines}\n\n"
            f"{obstruction_note}"
            f"### Fresh Structural Synthesis Plan\n{reset_strategy} {format_directive}"
        )

    prev_trimmed = (prior_completion or "").strip()
    if len(prev_trimmed) > 2200:
        prev_trimmed = prev_trimmed[:2200] + "\n...<truncated>"

    return (
        f"{plane1_excerpt}\n\n"
        f"### Task\n{original_prompt.strip()}\n\n"
        f"### Previous Attempt (Turn {turn_index - 1})\n{prev_trimmed}\n\n"
        f"### Deterministic Tier 2 Oracle Diagnostics\n{diag_lines}\n\n"
        f"### Repair Instructions\nFix every Tier 2 diagnostic above and emit the complete corrected response. {format_directive}"
    )


def format_qwen35_chat_prompt(user_prompt: str, system_prompt: str | None = None) -> str:
    """Render deterministic Qwen3.5 chat template (`enable_thinking = False`)."""
    parts: list[str] = []
    if system_prompt:
        parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")
    parts.append(f"<|im_start|>user\n{user_prompt}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    return "".join(parts)


def make_llama_server_generator(
    server_url: str,
    *,
    lora: Sequence[Mapping[str, Any]] = (),
    max_tokens: int = 768,
    seed: int = 42,
    slot_id: int = 0,
    timeout_s: float = 300.0,
) -> Callable[[str, int], dict[str, Any]]:
    """Create a deterministic `temperature = 0.0, top_p = 1.0` generator backed by `llama-server`."""
    base = server_url.rstrip("/")

    def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(dict(payload)).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}

    def _generate(user_prompt: str, _turn_idx: int) -> dict[str, Any]:
        slot_erase_err: str | None = None
        try:
            _post_json(f"{base}/slots/{slot_id}?action=erase", {})
        except OSError as exc:
            slot_erase_err = str(exc)
        rendered = format_qwen35_chat_prompt(user_prompt)
        req_body: dict[str, Any] = {
            "prompt": rendered,
            "n_predict": max_tokens,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": seed,
            "cache_prompt": False,
            "stop": list(QWEN35_STOP_TOKENS),
            "lora": [dict(x) for x in lora],
            "id_slot": slot_id,
        }
        t0 = time.perf_counter()
        resp = _post_json(f"{base}/completion", req_body)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        content = str(resp.get("content", ""))
        prompt_toks = int(resp.get("tokens_evaluated") or estimate_tokens_conservative(rendered))
        comp_toks = int(resp.get("tokens_predicted") or estimate_tokens_conservative(content))
        out: dict[str, Any] = {
            "content": content,
            "prompt_tokens": prompt_toks,
            "completion_tokens": comp_toks,
            "elapsed_ms": elapsed_ms,
        }
        if slot_erase_err is not None:
            out["slot_erase_warning"] = slot_erase_err
        return out

    return _generate


# Post-Hoc Benchmark Grader (`eval_grader_fn`, NEVER fed back to model) -------

def _extract_first_json_block(text: str) -> str | None:
    blocks = extract_fenced_blocks(text, ("json",))
    return blocks[0].strip() if blocks else None


_FAMILY_C_STATUS_VERIFIED_RE = re.compile(r"(?im)^status\s*:\s*verified\b")
_FAMILY_C_STATUS_NOT_VERIFIED_RE = re.compile(r"(?im)^status\s*:.*not verified")
_FAMILY_C_SORRY_OR_ADMIT_RE = re.compile(r"\b(sorry|admit)\b")
# Lean atomic names include `«quoted»` forms and non-ASCII letters such as `α` and `café`.
_LEAN_NAME_ATOM = r"(?:«[^»]*»|_*(?:[^\W\d_])[\w!?']*)"
_LEAN_NAME = rf"{_LEAN_NAME_ATOM}(?:\.{_LEAN_NAME_ATOM})*"
_FAMILY_C_DECL_NAME_RE = re.compile(
    rf"\b(?:theorem|lemma)\b[ \t]+(?P<name>{_LEAN_NAME})"
)
_FAMILY_C_OTHER_DECL_RE = re.compile(
    rf"(?<![\w@\[])(?:"
    rf"instance\b(?:[ \t]+(?P<inst>{_LEAN_NAME}))?(?=[ \t]*:)"
    rf"|example\b(?:[ \t]+(?P<ex>{_LEAN_NAME}))?(?=[ \t]*:)"
    rf"|abbrev\b[ \t]+(?P<abbrev>{_LEAN_NAME})"
    rf")"
)


def _normalize_family_c_statement(text: str) -> str:
    """Collapse whitespace so statement hashes are layout-insensitive."""
    return re.sub(r"\s+", " ", text).strip()


def _family_c_candidate_statements(candidate_lean: str) -> dict[str, str]:
    """Map each fully-qualified theorem name to the sha256 of its normalized statement."""
    cleaned = strip_lean_comments_and_strings(candidate_lean)
    stmts: dict[str, str] = {}
    for match in THEOREM_DECL_RE.finditer(cleaned):
        full = str(match.group("name"))
        stmt = _normalize_family_c_statement(f"{full} {match.group('header')}")
        stmts[full] = hashlib.sha256(stmt.encode("utf-8")).hexdigest()
    return stmts


def _family_c_all_decl_names(candidate_lean: str) -> set[str]:
    """Declaration names the line-start ASCII theorem regex does not keep.

    Includes a mid-line `theorem`, a `«quoted»` or non-ASCII name, and
    `instance`, `example`, and `abbrev`. An unnamed `example` or `instance`
    is recorded under that keyword.
    """
    cleaned = strip_lean_comments_and_strings(candidate_lean)
    names = {str(match.group("name")) for match in _FAMILY_C_DECL_NAME_RE.finditer(cleaned)}
    for match in _FAMILY_C_OTHER_DECL_RE.finditer(cleaned):
        if match.group(0).startswith("instance"):
            names.add(str(match.group("inst") or "instance"))
        elif match.group(0).startswith("example"):
            names.add(str(match.group("ex") or "example"))
        elif match.group("abbrev"):
            names.add(str(match.group("abbrev")))
    return names


def _family_c_forbidden_eval_findings(candidate_lean: str) -> list[dict[str, Any]]:
    """Reject every command in the `FORBIDDEN_EVAL_COMMAND` lint, including mid-line.

    The scan uses that lint's own pattern on comment-stripped and string-stripped
    source. A hit returns before `lake build`, because those commands run candidate
    code during elaboration.
    """
    cleaned = strip_lean_comments_and_strings(candidate_lean)
    rx = dict(BAR_FORBIDDEN_RULES)["FORBIDDEN_EVAL_COMMAND"]
    found: list[str] = []
    for match in rx.finditer(cleaned):
        cmd = match.group(0)
        if cmd not in found:
            found.append(cmd)
    if not found:
        return []
    return [
        {
            "rule": "FORBIDDEN_EVAL_COMMAND",
            "message": (
                "candidate contains a Lean command that runs during elaboration: "
                + ", ".join(found)
                + "."
            ),
        }
    ]


# `initialize` / `builtin_initialize` and the `@[init]` / `@[builtin_init]` attributes run IO
# during `lake build`. `run_cmd`, `run_elab`, `run_tac`, and `elab` do too, before the
# comparator's own lint. Identifier characters include `'`, `.`, and `«»`, which are not
# `\w`, so the boundary is explicit: `elab'`, `x.elab`, and `«elab»` stay legal names.
_FAMILY_C_NAME_EDGE = r"\w.'»«"
_FAMILY_C_INITIALIZER_RE = re.compile(
    rf"(?<![{_FAMILY_C_NAME_EDGE}])(?:builtin_initialize|initialize)(?![{_FAMILY_C_NAME_EDGE}])"
    r"|@\[[^\]]*?\b(?:builtin_init|init)\b"
)
_FAMILY_C_ELAB_COMMAND_RE = re.compile(
    rf"\b(?:run_cmd|run_elab|run_tac)\b|(?<![{_FAMILY_C_NAME_EDGE}])elab(?![{_FAMILY_C_NAME_EDGE}])"
)
# These run during the build or the later import. They are recorded, and the build still
# runs inside the sandbox. Returning here would hide a sandbox that no longer confines.
_FAMILY_C_BUILD_SIDE_EFFECT_RE = re.compile(
    r"(?m)^[ \t]*attribute[ \t]*\[[^\]]*\b(?:builtin_init|init)\b"
    r"|\brun_meta\b"
    r"|\belab_rules\b"
)


def _family_c_unique_matches(rx: re.Pattern[str], cleaned: str) -> list[str]:
    found: list[str] = []
    for match in rx.finditer(cleaned):
        cmd = match.group(0)
        if cmd not in found:
            found.append(cmd)
    return found


def _family_c_initializer_findings(candidate_lean: str) -> list[dict[str, Any]]:
    """Reject initializers before `lake build`. They execute IO while the project builds."""
    cleaned = strip_lean_comments_and_strings(candidate_lean)
    found = _family_c_unique_matches(_FAMILY_C_INITIALIZER_RE, cleaned)
    if not found:
        return []
    return [
        {
            "rule": "FORBIDDEN_INITIALIZER",
            "message": (
                "candidate contains a Lean initializer that runs during lake build: "
                + ", ".join(found)
                + "."
            ),
        }
    ]


def _family_c_elab_command_findings(candidate_lean: str) -> list[dict[str, Any]]:
    """Reject elaboration commands before the first `lake build`, not only in the comparator."""
    cleaned = strip_lean_comments_and_strings(candidate_lean)
    found = _family_c_unique_matches(_FAMILY_C_ELAB_COMMAND_RE, cleaned)
    if not found:
        return []
    return [
        {
            "rule": "FORBIDDEN_ELAB_COMMAND",
            "message": (
                "candidate contains a Lean elaboration command that runs during lake build: "
                + ", ".join(found)
                + "."
            ),
        }
    ]


def _family_c_build_side_effect_findings(candidate_lean: str) -> list[dict[str, Any]]:
    """Record `attribute [init]`, `run_meta`, and `elab_rules` without skipping the build.

    The sandbox is what stops the write. These findings stay on the result either way.
    """
    cleaned = strip_lean_comments_and_strings(candidate_lean)
    found = _family_c_unique_matches(_FAMILY_C_BUILD_SIDE_EFFECT_RE, cleaned)
    if not found:
        return []
    return [
        {
            "rule": "FORBIDDEN_BUILD_SIDE_EFFECT",
            "message": (
                "candidate contains a command that runs during compilation or import: "
                + ", ".join(found)
                + "."
            ),
        }
    ]


def _family_c_statement_headers(
    meta: Mapping[str, Any], theorem_names: Sequence[str]
) -> dict[str, str] | None:
    """Return the pinned header of every challenge theorem, or None if any pin is missing.

    A header is the text after the fully-qualified theorem name, the same span
    `THEOREM_DECL_RE` captures. Callers hash that text. Nothing here invents `op x = x`.
    """
    raw = meta.get("statements")
    if not isinstance(raw, Mapping):
        return None
    headers: dict[str, str] = {}
    for name in theorem_names:
        full = str(name)
        header = raw.get(full)
        if not isinstance(header, str) or not header.strip():
            return None
        headers[full] = header.strip()
    return headers


def _family_c_expected_statements(headers: Mapping[str, str]) -> dict[str, str]:
    """Map each fully-qualified name to the sha256 of its pinned, whitespace-normalized statement."""
    expected: dict[str, str] = {}
    for full, header in headers.items():
        stmt = _normalize_family_c_statement(f"{full} {header}")
        expected[str(full)] = hashlib.sha256(stmt.encode("utf-8")).hexdigest()
    return expected


def _family_c_root_source(pkg: str, meta: Mapping[str, Any]) -> str:
    """Library module for the generated project. Uses caller-supplied defs, never an identity `op`."""
    defs = meta.get("definitions")
    if isinstance(defs, str) and defs.strip():
        return defs.strip() + "\n"
    return f"namespace {pkg}\nend {pkg}\n"


def _family_c_spec_source(pkg: str, headers: Mapping[str, str]) -> str:
    """Challenge module: each pinned header, proved with `sorry` so the solution file is what `lake` checks."""
    lines = [f"import {pkg}", f"namespace {pkg}.Spec"]
    for full, header in headers.items():
        short = str(full).split(".")[-1]
        lines.append(f"theorem {short} {header} := by sorry")
    lines.append(f"end {pkg}.Spec")
    return "\n".join(lines) + "\n"


def _family_c_lakefile(pkg: str) -> str:
    """Build the library, the challenge, and the candidate proofs. `["{pkg}"]` alone skips the proofs."""
    return (
        f'name = "{pkg.lower()}"\nversion = "0.1.0"\n'
        f'defaultTargets = ["{pkg}", "{pkg}.Spec", "{pkg}.Proofs"]\n\n'
        f'[[lean_lib]]\nname = "{pkg}"\n\n[[lean_lib]]\nname = "{pkg}.Spec"\n\n'
        f'[[lean_lib]]\nname = "{pkg}.Proofs"\n\n[[lean_exe]]\nname = "{pkg.lower()}"\nroot = "Main"\n'
    )


def _family_c_code_under_proof(pkg: str, meta: Mapping[str, Any]) -> list[str]:
    raw = meta.get("code_under_proof")
    if isinstance(raw, list) and raw and all(isinstance(item, str) and item.strip() for item in raw):
        return [str(item) for item in raw]
    return [pkg]


def _family_c_toolchain_pin() -> str:
    return (repo_root() / "lean" / "lean-toolchain").read_text(encoding="utf-8").strip() + "\n"


def _check_family_c_statement_match(
    meta: Mapping[str, Any],
    theorem_names: Sequence[str],
    candidate_lean: str,
) -> list[dict[str, Any]]:
    """Statement-match guard: names plus hashes of the pinned target statements."""
    findings: list[dict[str, Any]] = []
    headers = _family_c_statement_headers(meta, theorem_names)
    if headers is None:
        findings.append(
            {
                "rule": "FAMILY_C_TARGET_STATEMENT_ABSENT",
                "message": (
                    "spec_meta.statements must pin the header of every theorem_names entry. "
                    "The turn does not invent an identity statement."
                ),
            }
        )
        return findings
    cand = _family_c_candidate_statements(candidate_lean)
    exp = _family_c_expected_statements(headers)
    hidden = _family_c_all_decl_names(candidate_lean) - set(cand)
    if hidden or set(cand) != set(exp):
        findings.append(
            {
                "rule": "FAMILY_C_THEOREM_NAME_MISMATCH",
                "message": (
                    "candidate theorem names do not equal challenge meta: "
                    f"missing={sorted(set(exp) - set(cand))} "
                    f"extra={sorted((set(cand) - set(exp)) | hidden)}."
                ),
            }
        )
        return findings
    for name in sorted(exp):
        if cand[name] != exp[name]:
            findings.append(
                {
                    "rule": "FAMILY_C_STATEMENT_MISMATCH",
                    "message": (
                        f"candidate statement hash for '{name}' does not equal challenge meta; "
                        "statements must match exactly."
                    ),
                }
            )
    return findings


def _family_c_lake_failure_message(stdout: str, stderr: str) -> str:
    """Keep the compiler `file:line:column` lines, then the short lake tail."""
    lines = [line.strip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()]
    located = [line for line in lines if re.search(r"\.lean:\d+:\d+", line)]
    tail = lines[-6:]
    kept: list[str] = []
    for line in located + tail:
        if line not in kept:
            kept.append(line)
    return " | ".join(kept[-8:])


def _family_c_sandbox_unavailable_finding() -> dict[str, Any]:
    return {
        "rule": "SANDBOX_UNAVAILABLE",
        "message": (
            "Linux bubblewrap (`bwrap`) is unavailable; "
            "refusing to compile or import candidate Lean unsandboxed."
        ),
    }


def _family_c_direct_lake_build(root: Path) -> list[dict[str, Any]]:
    """Run `lake build` on candidate text inside the bubblewrap sandbox.

    A missing `soko` tree must not hide a Lean error. A missing `lean`/`lake` still fails closed.
    A missing sandbox refuses the build. There is no unsandboxed fallback.
    """
    if not linux_bwrap_functional():
        return [_family_c_sandbox_unavailable_finding()]
    try:
        lake_bin = find_lean_tool("lake")
        env = _lean_env()
    except (OSError, RuntimeError) as exc:
        return [
            {
                "rule": "FAMILY_C_LEAN_TOOLCHAIN_UNAVAILABLE",
                "message": f"Lean toolchain unavailable; turn fails closed: {exc}",
            }
        ]
    try:
        build_res = run_confined_command(
            [lake_bin, "build"],
            cwd=root,
            env=env,
            timeout_sec=300,
        )
    except CandidateSandboxUnavailable:
        return [_family_c_sandbox_unavailable_finding()]
    if build_res.returncode != 0:
        return [
            {
                "rule": "LAKE_BUILD_FAILED",
                "message": f"`lake build` failed: {_family_c_lake_failure_message(build_res.stdout or '', build_res.stderr or '')}",
            }
        ]
    return []


def _lean_exception_is_missing_toolchain(exc: BaseException) -> bool:
    message = str(exc)
    return "Lean tool" in message or "elan bin" in message


def _run_family_c_real_lean_turn(harness: Mapping[str, Any], completion_text: str) -> list[dict[str, Any]]:
    """Real-Lean Family C turn for `oracle_type: bar_check` only.

    `bar_status` comes from harness meta. The challenge statements come from
    `spec_meta.statements`. The solution file is the candidate's fenced lean.
    `verdict_audit` items never enter this function. `lake build` still runs when
    the mission template or the soko auditor checkout is absent. It does not run
    when `lean` and `lake` themselves are absent.
    """
    meta = harness.get("spec_meta") or {}
    pkg = str(meta.get("pkg", "")).strip()
    thms = [str(t) for t in (meta.get("theorem_names") or [])]
    # Bar status comes from harness meta exclusively; candidate prose can never promote it.
    bar_status = str(meta.get("bar_status", "")).strip()
    if not pkg or not thms:
        return [
            {
                "rule": "FAMILY_C_MALFORMED_HARNESS",
                "message": "harness spec_meta must define pkg and theorem_names.",
            }
        ]
    findings: list[dict[str, Any]] = []
    readme_body = re.sub(r"(?im)^Claim-Tier:[^\n]*\n+", "", completion_text, count=1)
    if (
        _FAMILY_C_STATUS_VERIFIED_RE.search(readme_body)
        and not _FAMILY_C_STATUS_NOT_VERIFIED_RE.search(readme_body)
        and bar_status.lower() != "verified"
    ):
        findings.append(
            {
                "rule": "FAMILY_C_STATUS_SELF_ATTESTATION",
                "message": (
                    f"candidate declares 'Status: verified' but harness meta bar_status is {bar_status!r}; "
                    "bar status comes from harness meta exclusively."
                ),
            }
        )
    lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
    candidate_lean = "\n\n".join(block.strip() for block in lean_blocks if block.strip())
    if not candidate_lean:
        findings.append(
            {
                "rule": "FAMILY_C_MISSING_CANDIDATE_LEAN",
                "message": "no ```lean code blocks found; the checked project is built from the candidate's lean blocks.",
            }
        )
        return findings
    if _FAMILY_C_SORRY_OR_ADMIT_RE.search(strip_lean_comments_and_strings(candidate_lean)):
        findings.append(
            {
                "rule": "FAMILY_C_SOLUTION_USES_SORRY_OR_ADMIT",
                "message": "solution module uses 'sorry' or 'admit'; the turn fails.",
            }
        )
    findings.extend(_family_c_forbidden_eval_findings(candidate_lean))
    findings.extend(_family_c_initializer_findings(candidate_lean))
    findings.extend(_family_c_elab_command_findings(candidate_lean))
    findings.extend(_check_family_c_statement_match(meta, thms, candidate_lean))
    if findings:
        return findings
    headers = _family_c_statement_headers(meta, thms)
    if headers is None:
        return [
            {
                "rule": "FAMILY_C_TARGET_STATEMENT_ABSENT",
                "message": (
                    "spec_meta.statements must pin the header of every theorem_names entry. "
                    "The turn does not invent an identity statement."
                ),
            }
        ]
    mission_bar: tuple[Path, Path] | None = None
    try:
        mission = dep_repo("mission")
    except FileNotFoundError as exc:
        findings.append(
            {
                "rule": "FAMILY_C_MISSION_BAR_UNAVAILABLE",
                "message": (
                    "mission bar template is unavailable, so the structural bar replay was not run. "
                    f"{exc}"
                ),
            }
        )
    else:
        bar_tpl = mission / "bar" / "template"
        bar_chk = mission / "bar" / "check.py"
        if bar_tpl.is_dir() and bar_chk.is_file():
            mission_bar = (bar_tpl, bar_chk)
        else:
            findings.append(
                {
                    "rule": "FAMILY_C_MISSION_BAR_UNAVAILABLE",
                    "message": f"mission checkout at {mission} has no bar/template or bar/check.py.",
                }
            )
    code_toml = ", ".join(json.dumps(name) for name in _family_c_code_under_proof(pkg, meta))
    test_cmd = str(meta.get("test_cmd") or "python3 tests/run_tests.py")
    with tempfile.TemporaryDirectory(prefix="mcproof_rep_bar_") as td:
        root = Path(td)
        if mission_bar is not None:
            shutil.copytree(mission_bar[0], root, dirs_exist_ok=True)
            (root / "Clamp.lean").unlink(missing_ok=True)
            shutil.rmtree(root / "Clamp", ignore_errors=True)
            # Keep lake-manifest.json. bar/check.py item 3 fails closed when it is
            # absent, including under --no-lean, so deleting it rejects a correct proof.
        else:
            (root / "lean-toolchain").write_text(_family_c_toolchain_pin(), encoding="utf-8")
        (root / f"{pkg}.lean").write_text(_family_c_root_source(pkg, meta), encoding="utf-8")
        (root / pkg).mkdir(exist_ok=True)
        (root / pkg / "Spec.lean").write_text(_family_c_spec_source(pkg, headers), encoding="utf-8")
        # Solution module is the candidate's lean blocks verbatim. Theorems must use
        # the fully-qualified challenge name (for example `theorem CrtPair.Spec.crt_mod_left ...`).
        (root / pkg / "Proofs.lean").write_text(
            f"import {pkg}\n\n{candidate_lean}\n",
            encoding="utf-8",
        )
        (root / "Main.lean").write_text(
            f'import {pkg}\ndef main : IO Unit := IO.println "ok"\n',
            encoding="utf-8",
        )
        (root / "lakefile.toml").write_text(_family_c_lakefile(pkg), encoding="utf-8")
        (root / "comparator.json").write_text(
            json.dumps(
                {
                    "challenge_module": f"{pkg}.Spec",
                    "solution_module": f"{pkg}.Proofs",
                    "theorem_names": thms,
                    "permitted_axioms": ["propext", "Quot.sound", "Classical.choice"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if mission_bar is not None:
            (root / "bar.toml").write_text(
                f'[project]\nname = "{pkg.lower()}"\nstatus = "{bar_status}"\npage = "README.md"\n'
                f'spec_authors = ["example-author"]\nentry_points = ["Main.lean"]\n\n'
                f'[spec]\nfiles = ["SPEC.md", "{pkg}/Spec.lean"]\ncode = [{code_toml}]\n\n'
                f'[tests]\nresults = "tests/TEST-RESULTS.md"\ncommand = "{test_cmd}"\nfiles = ["tests/run_tests.py"]\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(readme_body, encoding="utf-8")
            out_json = root / "bar_out.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-O",
                    "-B",
                    "-W",
                    "error",
                    str(mission_bar[1]),
                    str(root),
                    "--no-lean",
                    "--offline",
                    "--json",
                    str(out_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                findings.append({"rule": "BAR_CHECK_FAILED", "message": "bar check failed"})
            elif out_json.is_file():
                rep = json.loads(out_json.read_text(encoding="utf-8"))
                by_item = {r["item"]: r["status"] for r in rep.get("items", [])}
                for req_i in (2, 4, 5, 6):
                    if by_item.get(req_i) != "PASS":
                        findings.append({"rule": "BAR_CHECK_ITEM_FAIL", "message": f"bar item {req_i} did not pass"})
        # `lake build` is the formal signal. Its message keeps `.lean:line:column` lines.
        # The comparator's own tail keeps only the last 6 lines, which can drop that error.
        # Kernel checks run only after this build succeeds.
        findings.extend(_family_c_build_side_effect_findings(candidate_lean))
        findings.extend(_family_c_direct_lake_build(root))
        if any(
            f.get("rule") in {"LAKE_BUILD_FAILED", "FAMILY_C_LEAN_TOOLCHAIN_UNAVAILABLE", "SANDBOX_UNAVAILABLE"}
            for f in findings
        ):
            return findings
        try:
            lean_res = verify_lean4_project_comparator(root, allow_unsandboxed=False)
        except FileNotFoundError as exc:
            if _lean_exception_is_missing_toolchain(exc):
                findings.append(
                    {
                        "rule": "FAMILY_C_LEAN_TOOLCHAIN_UNAVAILABLE",
                        "message": f"Lean toolchain unavailable; turn fails closed: {exc}",
                    }
                )
                return findings
            findings.append(
                {
                    "rule": "FAMILY_C_LEAN_AUDIT_DEPS_UNAVAILABLE",
                    "message": f"lake build passed, but the comparator auditor checkout is missing: {exc}",
                }
            )
            return findings
        except (OSError, RuntimeError) as exc:
            findings.append(
                {
                    "rule": "FAMILY_C_LEAN_TOOLCHAIN_UNAVAILABLE",
                    "message": f"Lean toolchain unavailable; turn fails closed: {exc}",
                }
            )
            return findings
        for finding in lean_res.findings:
            findings.append(dict(finding))
    return findings


def _run_public_family_c_harness(harness: Mapping[str, Any], completion_text: str) -> list[dict[str, Any]]:
    """Post-hoc Family C ground-truth scorer matching `datasets/scripts/grade_item.py`."""
    otype = harness.get("oracle_type")

    if otype == "bar_check":
        return _run_family_c_real_lean_turn(harness, completion_text)

    meta = harness.get("spec_meta") or {}
    findings: list[dict[str, Any]] = []

    if otype == "verdict_audit":
        jb = _extract_first_json_block(completion_text)
        if jb is None:
            return [{"rule": "MISSING_VERDICT_JSON", "message": "missing ```json verdict block"}]
        try:
            obj = json.loads(jb)
        except ValueError as exc:
            return [{"rule": "INVALID_VERDICT_JSON", "message": str(exc)}]
        if obj.get("verdict") != meta.get("expected_verdict"):
            findings.append({"rule": "VERDICT_MISMATCH", "message": "verdict value mismatch"})
        if obj.get("source_commit") != meta.get("source_commit"):
            findings.append({"rule": "SOURCE_COMMIT_MISMATCH", "message": "source_commit does not match pinned 40-char SHA"})
        if obj.get("axioms") != meta.get("expected_axioms"):
            findings.append({"rule": "AXIOMS_LIST_MISMATCH", "message": "axioms list mismatch"})
        return findings

    if otype == "f0_claim_gate":
        jb = _extract_first_json_block(completion_text)
        if jb is None:
            return [{"rule": "MISSING_F0_JSON", "message": "missing ```json F0 claim wrapper"}]
        try:
            payload = json.loads(jb)
        except ValueError as exc:
            return [{"rule": "INVALID_F0_JSON", "message": str(exc)}]
        rec = payload.get("record")
        bucket = payload.get("chart_bucket")
        if not isinstance(rec, dict) or bucket not in ("claimed", "verified"):
            return [{"rule": "INVALID_F0_WRAPPER", "message": "invalid F0 wrapper"}]
        f0_src = dep_repo("f0")
        with tempfile.TemporaryDirectory(prefix="mcproof_rep_f0_") as td:
            rdir = Path(td)
            (rdir / "data").mkdir()
            (rdir / "docs").mkdir()
            shutil.copytree(f0_src / "scripts", rdir / "scripts")
            shutil.copyfile(f0_src / "feed.schema.json", rdir / "feed.schema.json")
            shutil.copyfile(f0_src / "feed.schema.json", rdir / "docs" / "feed.schema.json")
            art_bytes = str(meta["cert_artifact_bytes_utf8"]).encode("utf-8")
            art_sha = str(meta["cert_artifact_sha256"])
            (rdir / "data" / "certificate.artifact.json").write_bytes(art_bytes)
            mirror_obj = {
                "kappa": "90446448750933/125000000000000000",
                "decimal": "0.000723571590007464",
                "certificate": "certificates/selected-result.json",
                "certificate_sha256": art_sha,
            }
            mirror_bytes = (json.dumps(mirror_obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
            (rdir / "data" / "selected-result.json").write_bytes(mirror_bytes)
            blob_sha1 = hashlib.sha1(b"blob %d\x00" % len(mirror_bytes) + mirror_bytes).hexdigest()
            raw_cap = {
                "path": "certificates/selected-result.json",
                "sha": blob_sha1,
                "size": len(mirror_bytes),
                "content": base64.b64encode(mirror_bytes).decode("ascii"),
            }
            (rdir / "data" / "selected-result.raw.json").write_text(json.dumps(raw_cap, indent=2) + "\n", encoding="utf-8")
            (rdir / "data" / "records.json").write_text(json.dumps({"records": [rec]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            gen_at = "2026-11-19T00:00:00Z"
            main_sha = hashlib.sha256(b"upstream-main-anchor").hexdigest()[:40]
            feed_obj = {
                "feed_version": 1,
                "generated_at": gen_at,
                "upstream_main_sha": main_sha,
                "selected_result": {
                    "kappa": mirror_obj["kappa"],
                    "decimal": mirror_obj["decimal"],
                    "certificate_sha256": art_sha,
                    "selected_result_sha256": hashlib.sha256(mirror_bytes).hexdigest(),
                    "source_blob_sha": blob_sha1,
                    "source_path": "certificates/selected-result.json",
                },
                "records": [rec] if not rec.get("stale") else [],
                "quarantined": [rec] if rec.get("stale") else [],
            }
            c_claimed = {
                "pr": rec.get("pr"),
                "head_sha": rec.get("head_sha"),
                "kappa_decimal": rec.get("kappa_decimal"),
                "draft": rec.get("draft", False),
                "pr_updated_at": rec.get("pr_updated_at"),
                "pr_url": (rec.get("source_refs") or {}).get("pr_url"),
            }
            c_ver = {
                "pr": rec.get("pr"),
                "head_sha": rec.get("head_sha"),
                "kappa_decimal": rec.get("kappa_decimal"),
                "tier": rec.get("tier"),
                "pr_updated_at": rec.get("pr_updated_at"),
                "pr_url": (rec.get("source_refs") or {}).get("pr_url"),
            }
            chart_obj = {
                "generated_at": gen_at,
                "claimed": [c_claimed] if bucket == "claimed" else [],
                "verified": [c_ver] if bucket == "verified" else [],
            }
            (rdir / "docs" / "feed.json").write_text(json.dumps(feed_obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (rdir / "docs" / "chart-data.json").write_text(json.dumps(chart_obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-O", "-B", "-W", "error", str(rdir / "scripts" / "gate.py"), "--root", str(rdir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                findings.append({"rule": "F0_GATE_FAILED", "message": "f0 gate check failed"})
            if rec.get("tier") != meta.get("expected_f0_tier") or bucket != meta.get("expected_chart_bucket"):
                findings.append({"rule": "F0_TIER_BUCKET_MISMATCH", "message": "f0 tier or bucket mismatch"})
        return findings

    return findings


def default_dataset_item_grader(
    item: Mapping[str, Any],
    completion_text: str,
    *,
    datasets_root: Path | None = None,
) -> dict[str, Any]:
    """Post-hoc ground-truth Tier 2 benchmark scorer (`eval_grader_fn`)."""
    ds_root = datasets_root or (repo_root() / "datasets")
    fam = str(item["family"]).strip().upper()
    exp_tier = item.get("expected_tier")
    harness_rel = item.get("harness_path")
    harness: dict[str, Any] = {}
    if harness_rel and (ds_root / str(harness_rel)).is_file():
        harness = json.loads((ds_root / str(harness_rel)).read_text(encoding="utf-8"))

    gen_src = harness.get("generator_source") if fam == "B" else None
    valid_cases = list(harness.get("valid_cases", [])) if fam == "B" else []
    planted = list(harness.get("planted_mutations")) if (fam == "B" and "planted_mutations" in harness) else None

    rec: OracleReceipt = grade_family_completion(
        fam,
        completion_text,
        expected_tier=str(exp_tier) if exp_tier else None,
        generator_source=gen_src,
        valid_cases=valid_cases,
        planted_mutations=planted,
    )
    passed = rec.passed
    findings = [dict(f) for f in rec.findings]

    if fam == "A":
        lean_blocks = extract_fenced_blocks(completion_text, ("lean", "lean4"))
        lean_src = "\n\n".join(lean_blocks) if lean_blocks else completion_text
        cleaned_lean = strip_lean_comments_and_strings(lean_src)
        declared_thms = {m.group("name").split(".")[-1] for m in THEOREM_DECL_RE.finditer(cleaned_lean)}
        if harness.get("theorem_name"):
            thm_name = str(harness["theorem_name"])
            short_name = thm_name.split(".")[-1]
            if short_name not in declared_thms:
                passed = False
                findings.append(
                    {
                        "rule": "MISSING_REQUIRED_THEOREM_NAME",
                        "message": f"Completion must declare and prove theorem `{thm_name}` without renaming it.",
                    }
                )
        if passed and harness.get("challenge_lean"):
            chal_findings = verify_lean4_against_challenge(str(harness["challenge_lean"]), lean_src)
            if chal_findings:
                passed = False
                findings.extend(chal_findings)
        elif item.get("prompt"):
            p_findings = verify_lean4_prompt_obligations(
                str(item["prompt"]),
                lean_src,
                run_kernel_type_check=passed,
            )
            if p_findings:
                passed = False
                findings.extend(p_findings)

    if fam == "C" and harness:
        c_findings = _run_public_family_c_harness(harness, completion_text)
        if c_findings:
            passed = False
            findings.extend(c_findings)

    return {
        "passed": passed,
        "epistemic_status": rec.epistemic_status if passed else "REJECTED",
        "findings": findings,
    }


def run_repair_item(
    item: Mapping[str, Any],
    generator_fn: Callable[[str, int], dict[str, Any] | str],
    *,
    max_turns: int = 4,
    retrieval_max_tokens: int = 1250,
    inference_oracle_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    eval_grader_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    grader_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    datasets_root: Path | None = None,
    spec_path: Path | None = None,
    include_plane1_retrieval: bool = True,
) -> dict[str, Any]:
    """Execute bounded `k`-turn label-free inference repair + post-hoc benchmark scoring on one item.

    - `inference_oracle_fn` (default: `default_inference_oracle`) sees ONLY `{'id', 'family', 'prompt'}`
      and drives Turn `1..k` diagnostics and early stopping (`inference_certified_at_turn`).
    - `eval_grader_fn` (or `grader_fn` alias; default: `default_dataset_item_grader`) scores each
      deployed candidate post-hoc for `pass_at_1..k` without ever leaking ground-truth labels or
      private fixture verdicts back into the repair prompt or stopping rule.
    """
    if max_turns < 1:
        raise ValueError("max_turns must be >= 1")

    item_id = str(item["id"])
    fam = str(item["family"]).strip().upper()
    prompt_text = str(item["prompt"])
    public_view: dict[str, Any] = {"id": item_id, "family": fam, "prompt": prompt_text}

    active_inf_oracle = inference_oracle_fn or default_inference_oracle
    active_eval_grader = eval_grader_fn or grader_fn or (
        lambda it, comp: default_dataset_item_grader(it, comp, datasets_root=datasets_root)
    )

    prior_inf_findings: list[dict[str, Any]] = []
    prior_sanitized: list[dict[str, str]] = []
    prior_completion: str | None = None
    seen_state_hashes: set[str] = set()
    seen_fail_sigs: set[str] = set()
    seen_chunk_ids: list[str] = []
    refuted_routes: list[dict[str, Any]] = []
    stagnation_next = False
    stagnation_events = 0

    turn_records: list[dict[str, Any]] = []
    eval_pass_by_turn: dict[int, bool] = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_retrieved_tokens = 0
    total_elapsed_ms = 0.0
    inference_certified_at_turn: int | None = None
    deployed_eval_passed_when_certified: bool | None = None

    for turn_idx in range(1, max_turns + 1):
        if include_plane1_retrieval:
            ret = retrieve_plane1_excerpt(
                family=fam,
                prompt_text=prompt_text,
                prior_findings=prior_inf_findings,
                max_tokens=retrieval_max_tokens,
                spec_path=spec_path,
                exclude_chunk_ids=seen_chunk_ids if stagnation_next else (),
                prefer_worked_examples=stagnation_next,
            )
            excerpt = str(ret["excerpt"])
            ret_toks = int(ret["estimated_tokens"])
            chunk_ids = list(ret["chunk_ids"])
            for cid in chunk_ids:
                if cid not in seen_chunk_ids:
                    seen_chunk_ids.append(cid)
        else:
            excerpt = ""
            ret_toks = 0
            chunk_ids = []

        user_prompt = build_repair_turn_prompt(
            family=fam,
            original_prompt=prompt_text,
            plane1_excerpt=excerpt,
            turn_index=turn_idx,
            prior_completion=prior_completion,
            sanitized_diagnostics=prior_sanitized,
            stagnation_detected=stagnation_next,
            refuted_routes=refuted_routes,
        )

        gen_raw = generator_fn(user_prompt, turn_idx)
        if isinstance(gen_raw, str):
            comp_text = gen_raw
            p_toks = estimate_tokens_conservative(user_prompt)
            c_toks = estimate_tokens_conservative(comp_text)
            gen_ms = 0.0
        else:
            comp_text = str(gen_raw.get("content", ""))
            p_toks = int(gen_raw.get("prompt_tokens") or estimate_tokens_conservative(user_prompt))
            c_toks = int(gen_raw.get("completion_tokens") or estimate_tokens_conservative(comp_text))
            gen_ms = float(gen_raw.get("elapsed_ms") or 0.0)

        # 1. Label-free inference-time oracle (drives diagnostics & stopping)
        t_inf = time.perf_counter()
        inf_res = active_inf_oracle(public_view, comp_text)
        inf_ms = round((time.perf_counter() - t_inf) * 1000.0, 2)
        inf_passed = bool(inf_res.get("passed", False))
        inf_findings = [dict(f) for f in inf_res.get("findings", ())]
        sanitized = sanitize_oracle_diagnostics(fam, inf_findings)

        # 2. Post-hoc ground-truth evaluation (NEVER fed back into diagnostics or stopping!)
        t_eval = time.perf_counter()
        eval_res = active_eval_grader(item, comp_text)
        eval_ms = round((time.perf_counter() - t_eval) * 1000.0, 2)
        eval_passed = bool(eval_res.get("passed", False))
        eval_pass_by_turn[turn_idx] = eval_passed

        # 3. Candidate AST / state deduplication & failure-signature plateau check
        state_hash = compute_candidate_state_hash(fam, comp_text)
        fail_sig = compute_failure_signature(inf_findings)
        repeated_state = state_hash in seen_state_hashes
        repeated_fail_sig = (not inf_passed) and (fail_sig in seen_fail_sigs)
        stagnation_hit = (not inf_passed) and (repeated_state or repeated_fail_sig)
        if stagnation_hit:
            stagnation_events += 1
        seen_state_hashes.add(state_hash)
        if not inf_passed:
            seen_fail_sigs.add(fail_sig)

        total_prompt_tokens += p_toks
        total_completion_tokens += c_toks
        total_retrieved_tokens += ret_toks
        total_elapsed_ms += gen_ms + inf_ms

        turn_records.append(
            {
                "turn": turn_idx,
                "inference_passed": inf_passed,
                "eval_passed": eval_passed,
                "passed": eval_passed,
                "stagnation_prompt_mode": stagnation_next,
                "stagnation_detected_after_turn": stagnation_hit,
                "candidate_state_hash": state_hash[:24],
                "failure_signature": fail_sig,
                "retrieved_plane1_tokens": ret_toks,
                "retrieved_chunk_ids": chunk_ids,
                "prompt_tokens": p_toks,
                "completion_tokens": c_toks,
                "generation_ms": round(gen_ms, 2),
                "inference_oracle_ms": inf_ms,
                "eval_grader_ms": eval_ms,
                "response_sha256": hashlib.sha256(comp_text.encode("utf-8")).hexdigest(),
                "diagnostic_rules": [d["rule"] for d in sanitized],
                "diagnostic_count": len(inf_findings),
            }
        )

        # Stopping rule depends ONLY on label-free `inf_passed`!
        if inf_passed:
            inference_certified_at_turn = turn_idx
            deployed_eval_passed_when_certified = eval_passed
            break

        primary_rule = sanitized[0]["rule"] if sanitized else "ORACLE_REJECTED"
        refuted_routes.append(
            {
                "turn": turn_idx,
                "state_hash": state_hash[:12],
                "primary_rule": primary_rule,
            }
        )
        prior_completion = comp_text
        prior_inf_findings = inf_findings
        prior_sanitized = sanitized
        stagnation_next = stagnation_hit

    # Deployed output at budget k (1..max_turns):
    # - If inference oracle certified at turn t <= k, the deployed output at budget k is turn t's output!
    # - Otherwise the loop ran through turn k, so the deployed output at budget k is turn k's output.
    pass_by_k: dict[str, bool] = {}
    first_eval_pass_turn: int | None = None
    for k in range(1, max_turns + 1):
        if inference_certified_at_turn is not None and inference_certified_at_turn <= k:
            deployed_ok = bool(deployed_eval_passed_when_certified)
        else:
            deployed_ok = bool(eval_pass_by_turn.get(min(k, len(turn_records)), False))
        pass_by_k[f"pass_at_{k}"] = deployed_ok
        if deployed_ok and first_eval_pass_turn is None:
            first_eval_pass_turn = k

    final_deployed_passed = pass_by_k[f"pass_at_{max_turns}"]
    return {
        "id": item_id,
        "family": fam,
        "max_turns": max_turns,
        "label_free_inference_stopping": True,
        "passed": final_deployed_passed,
        "inference_certified": inference_certified_at_turn is not None,
        "inference_certified_at_turn": inference_certified_at_turn,
        "solved_at_turn": first_eval_pass_turn,
        "turns_used": len(turn_records),
        "oracle_calls": len(turn_records),
        "stagnation_events": stagnation_events,
        "refuted_routes": refuted_routes,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "total_retrieved_plane1_tokens": total_retrieved_tokens,
        "total_elapsed_ms": round(total_elapsed_ms, 2),
        **pass_by_k,
        "turns": turn_records,
    }


def run_repair_split(
    items: Sequence[Mapping[str, Any]],
    generator_fn: Callable[[str, int], dict[str, Any] | str],
    *,
    max_turns: int = 4,
    retrieval_max_tokens: int = 1250,
    inference_oracle_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    eval_grader_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    grader_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    datasets_root: Path | None = None,
    spec_path: Path | None = None,
    include_plane1_retrieval: bool = True,
    checkpoint_jsonl: Path | None = None,
) -> dict[str, Any]:
    """Run bounded label-free closed-loop repair across a dataset split with crash-safe checkpointing."""
    completed_by_id: dict[str, dict[str, Any]] = {}
    if checkpoint_jsonl is not None and checkpoint_jsonl.is_file():
        for ln in checkpoint_jsonl.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rec = json.loads(ln)
                completed_by_id[str(rec["id"])] = rec

    results: list[dict[str, Any]] = []
    for item in items:
        iid = str(item["id"])
        if iid in completed_by_id:
            results.append(completed_by_id[iid])
            continue
        res = run_repair_item(
            item,
            generator_fn,
            max_turns=max_turns,
            retrieval_max_tokens=retrieval_max_tokens,
            inference_oracle_fn=inference_oracle_fn,
            eval_grader_fn=eval_grader_fn,
            grader_fn=grader_fn,
            datasets_root=datasets_root,
            spec_path=spec_path,
            include_plane1_retrieval=include_plane1_retrieval,
        )
        results.append(res)
        if checkpoint_jsonl is not None:
            checkpoint_jsonl.parent.mkdir(parents=True, exist_ok=True)
            with checkpoint_jsonl.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(res, sort_keys=True) + "\n")

    n_total = len(results)
    pass_curve: dict[str, dict[str, Any]] = {}
    for k in range(1, max_turns + 1):
        cnt = sum(1 for r in results if r.get(f"pass_at_{k}", False))
        pass_curve[f"k={k}"] = {
            "passed": cnt,
            "total": n_total,
            "pass_rate_bps": int(Fraction(cnt * 10000, n_total)) if n_total else 0,
            "pass_rate_pct": round((cnt / n_total) * 100.0, 2) if n_total else 0.0,
        }

    by_family: dict[str, dict[str, Any]] = {}
    for fam in ("A", "B", "C", "D"):
        fam_rows = [r for r in results if r["family"] == fam]
        if not fam_rows:
            continue
        by_family[fam] = {
            f"k={k}": {
                "passed": sum(1 for r in fam_rows if r.get(f"pass_at_{k}", False)),
                "total": len(fam_rows),
            }
            for k in range(1, max_turns + 1)
        }

    return {
        "schema": "mcproof-repair-loop-receipt/v0.2",
        "label_free_inference_stopping": True,
        "max_turns": max_turns,
        "retrieval_max_tokens": retrieval_max_tokens,
        "include_plane1_retrieval": include_plane1_retrieval,
        "total_items": n_total,
        "pass_curve": pass_curve,
        "by_family": by_family,
        "budget_totals": {
            "replies_used": sum(int(r["turns_used"]) for r in results),
            "oracle_calls": sum(int(r["oracle_calls"]) for r in results),
            "stagnation_events": sum(int(r.get("stagnation_events", 0)) for r in results),
            "inference_certified_items": sum(1 for r in results if r.get("inference_certified", False)),
            "prompt_tokens": sum(int(r["total_prompt_tokens"]) for r in results),
            "completion_tokens": sum(int(r["total_completion_tokens"]) for r in results),
            "total_tokens": sum(int(r["total_tokens"]) for r in results),
            "mean_retrieved_plane1_tokens_per_turn": round(
                sum(int(r["total_retrieved_plane1_tokens"]) for r in results)
                / max(1, sum(int(r["turns_used"]) for r in results)),
                1,
            ),
        },
        "items": results,
    }
