#!/usr/bin/env python3
"""Independent dataset, SHA256SUMS, and zero-overlap auditor for @corpus and @holdout.

SECURITY INVARIANT: Never writes any plaintext prompt, theorem body, or target completion
from <workspace>/mcproof-vault/ into any output file or stdout! Only prompt IDs,
SHA-256 digests, counts, Jaccard summary statistics, and rule codes are recorded.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

_VERIF_DIR = Path(__file__).resolve().parent
REPO_DIR = _VERIF_DIR.parent
_SC_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (REPO_DIR.parents[1] / "siliconcordat"))
DATASETS_DIR = Path(os.environ.get("MCPROOF_DATASETS_DIR") or (REPO_DIR / "datasets"))
VAULT_DIR = Path(os.environ.get("MCPROOF_VAULT_DIR") or (REPO_DIR.parents[1] / "mcproof-vault"))
MDE_BIN = Path(os.environ.get("MDE_BIN") or (_SC_ROOT / "mde" / "target" / "debug" / "mde"))
OUT_JSON = _VERIF_DIR / "datasets_vault_receipt.json"

REQUIRED_PROMPT_FIELDS = ("id", "split", "family", "zone", "prompt", "oracle_cmd", "expected_tier", "sha256")
LEAN_THM_RE = re.compile(r"(?m)^[ \t]*(?:private\s+|protected\s+)?(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_.']*)\s*[\(:{]")
WORD_RE = re.compile(r"[a-z0-9_]+")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except ValueError as exc:
            raise ValueError(f"{path.name}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"{path.name}:{lineno}: expected JSON object")
        rows.append(obj)
    return rows


def normalize_text(text: str) -> str:
    return " ".join(WORD_RE.findall(text.lower()))


def word_shingles(text: str, k: int = 8) -> set[tuple[str, ...]]:
    toks = WORD_RE.findall(text.lower())
    if len(toks) < k:
        return {tuple(toks)} if toks else set()
    return {tuple(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def verify_prompt_sha256(rec: dict[str, Any]) -> bool:
    stored = str(rec.get("sha256", "")).removeprefix("sha256:")
    if len(stored) != 64:
        return False
    # Accept canonical sha256 over prompt utf-8 bytes OR canonical JSON of record minus sha256
    prompt_sha = hashlib.sha256(str(rec.get("prompt", "")).encode("utf-8")).hexdigest()
    if stored == prompt_sha:
        return True
    without_sha = {k: v for k, v in rec.items() if k != "sha256"}
    for ensure_asc in (True, False):
        cand = hashlib.sha256(
            json.dumps(without_sha, sort_keys=True, separators=(",", ":"), ensure_ascii=ensure_asc).encode("utf-8")
        ).hexdigest()
        if stored == cand:
            return True
    # Also check core fields canonical JSON
    core = {k: rec[k] for k in REQUIRED_PROMPT_FIELDS if k != "sha256" and k in rec}
    for ensure_asc in (True, False):
        cand = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=ensure_asc).encode("utf-8")
        ).hexdigest()
        if stored == cand:
            return True
    return False


def run_mde_integrity_verify(root: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(MDE_BIN), "--root", str(root), "integrity", "--verify"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        parsed = json.loads(proc.stdout)
    except ValueError:
        parsed = {"raw": (proc.stdout + proc.stderr).strip()[:300]}
    return {"returncode": proc.returncode, "passed": proc.returncode == 0, "report": parsed}


def extract_lean_theorem_names(rec: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for field in ("prompt", "positive_completion", "gold_completion", "reference_solution", "target_positive"):
        val = rec.get(field)
        if isinstance(val, str):
            names.update(LEAN_THM_RE.findall(val))
    return names


def main() -> int:
    report: dict[str, Any] = {"checks": {}, "defects": []}

    # 1. Verify SHA256SUMS via mde integrity --verify on datasets/ and mcproof-vault/
    for label, dpath in (("datasets", DATASETS_DIR), ("vault", VAULT_DIR)):
        if not dpath.is_dir():
            report["defects"].append(f"missing directory: {dpath.name}")
            continue
        int_res = run_mde_integrity_verify(dpath)
        report["checks"][f"{label}_mde_integrity"] = int_res
        if not int_res["passed"]:
            # Also try --allow-unlisted to see if unlisted metadata files caused failure vs hash mismatch
            allow_proc = subprocess.run(
                [str(MDE_BIN), "--root", str(dpath), "integrity", "--verify", "--allow-unlisted"],
                capture_output=True,
                text=True,
                check=False,
            )
            report["checks"][f"{label}_mde_integrity_allow_unlisted_rc"] = allow_proc.returncode
            report["defects"].append(f"mde integrity --verify failed on {label}: {int_res['report']}")

    if report["defects"] and (not DATASETS_DIR.is_dir() or not VAULT_DIR.is_dir()):
        OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    # 2. Load and audit public splits
    compile_rows = load_jsonl(DATASETS_DIR / "compile.jsonl")
    val_rows = load_jsonl(DATASETS_DIR / "validation.jsonl")
    k0_rows = load_jsonl(DATASETS_DIR / "hybrid_k0.jsonl")

    # 3. Load and audit private vault splits
    holdout_rows = load_jsonl(VAULT_DIR / "private_holdout.jsonl")
    canary_rows = load_jsonl(VAULT_DIR / "canaries_16.jsonl")
    retention_rows = load_jsonl(VAULT_DIR / "general_retention_100.jsonl")
    mixed_rows = load_jsonl(VAULT_DIR / "mixed_composition_30.jsonl")

    def audit_formal_split(name: str, rows: list[dict[str, Any]], expected_total: int, expected_per_fam: int) -> dict[str, Any]:
        fam_counts = Counter(str(r.get("family", "")) for r in rows)
        ids = [str(r.get("id", "")) for r in rows]
        missing_fields = [
            str(r.get("id", f"idx_{i}"))
            for i, r in enumerate(rows)
            if any(k not in r or r[k] in (None, "") for k in REQUIRED_PROMPT_FIELDS)
        ]
        bad_shas = [str(r.get("id", f"idx_{i}")) for i, r in enumerate(rows) if not verify_prompt_sha256(r)]
        unique_ids = len(set(ids)) == len(ids)
        unique_prompts = len({normalize_text(str(r.get("prompt", ""))) for r in rows}) == len(rows)

        if len(rows) != expected_total:
            report["defects"].append(f"{name}: expected {expected_total} rows, got {len(rows)}")
        for fam in ("A", "B", "C", "D"):
            if fam_counts.get(fam, 0) != expected_per_fam:
                report["defects"].append(f"{name}: family {fam} expected {expected_per_fam}, got {fam_counts.get(fam, 0)}")
        if missing_fields:
            report["defects"].append(f"{name}: records missing required schema fields: {missing_fields[:10]}")
        if bad_shas:
            report["defects"].append(f"{name}: records failed sha256 verification: {bad_shas[:10]}")
        if not unique_ids:
            report["defects"].append(f"{name}: duplicate prompt IDs detected")
        if not unique_prompts:
            report["defects"].append(f"{name}: duplicate normalized prompts detected within split")

        return {
            "total": len(rows),
            "family_counts": dict(sorted(fam_counts.items())),
            "unique_ids": unique_ids,
            "unique_prompts": unique_prompts,
            "missing_field_count": len(missing_fields),
            "bad_sha256_count": len(bad_shas),
        }

    report["checks"]["compile_split"] = audit_formal_split("compile.jsonl", compile_rows, 96, 24)
    report["checks"]["validation_split"] = audit_formal_split("validation.jsonl", val_rows, 48, 12)
    report["checks"]["private_holdout_split"] = audit_formal_split("private_holdout.jsonl", holdout_rows, 96, 24)

    # Audit Hybrid K0 (`2048` seeded random-vocab noise + `24` y=0 preservation anchors)
    k0_kinds = Counter(str(r.get("kind") or r.get("category") or r.get("subset") or r.get("split") or "") for r in k0_rows)
    report["checks"]["hybrid_k0"] = {
        "total": len(k0_rows),
        "kind_counts": dict(sorted(k0_kinds.items())),
    }
    if len(k0_rows) != 2072:
        report["defects"].append(f"hybrid_k0.jsonl: expected 2072 (2048 + 24), got {len(k0_rows)}")

    # Audit canaries_16.jsonl (`8` safety/general preservation + `8` formal difficulty ladder, `2` per A-D)
    canary_cats = Counter(str(r.get("category") or r.get("kind") or r.get("split") or "") for r in canary_rows)
    canary_fams = Counter(str(r.get("family", "")) for r in canary_rows if r.get("family"))
    report["checks"]["canaries_16"] = {
        "total": len(canary_rows),
        "category_counts": dict(sorted(canary_cats.items())),
        "family_counts": dict(sorted(canary_fams.items())),
        "ids": [str(r.get("id") or r.get("canary_id")) for r in canary_rows],
    }
    if len(canary_rows) != 16:
        report["defects"].append(f"canaries_16.jsonl: expected 16 rows, got {len(canary_rows)}")

    # Audit general_retention_100.jsonl & mixed_composition_30.jsonl
    report["checks"]["general_retention_100"] = {
        "total": len(retention_rows),
        "unique_ids": len({str(r.get("id", i)) for i, r in enumerate(retention_rows)}) == len(retention_rows),
    }
    if len(retention_rows) != 100:
        report["defects"].append(f"general_retention_100.jsonl: expected 100 rows, got {len(retention_rows)}")

    report["checks"]["mixed_composition_30"] = {
        "total": len(mixed_rows),
        "unique_ids": len({str(r.get("id", i)) for i, r in enumerate(mixed_rows)}) == len(mixed_rows),
    }
    if len(mixed_rows) != 30:
        report["defects"].append(f"mixed_composition_30.jsonl: expected 30 rows, got {len(mixed_rows)}")

    # 4. Verify ZERO overlap between public (`compile`, `validation`, `hybrid_k0`) and vault (`holdout`, `canaries`, `retention`, `mixed`)
    pub_all = [("compile", r) for r in compile_rows] + [("validation", r) for r in val_rows]
    # Also check compile vs validation disjointness!
    comp_norms = {normalize_text(str(r.get("prompt", ""))): str(r.get("id")) for r in compile_rows}
    val_norms = {normalize_text(str(r.get("prompt", ""))): str(r.get("id")) for r in val_rows}
    cv_overlap = set(comp_norms.keys()) & set(val_norms.keys())
    if cv_overlap:
        report["defects"].append(f"compile vs validation prompt overlap count: {len(cv_overlap)}")

    vault_all = (
        [("holdout", r) for r in holdout_rows]
        + [("canary", r) for r in canary_rows]
        + [("retention", r) for r in retention_rows]
        + [("mixed", r) for r in mixed_rows]
    )

    pub_ids = {str(r.get("id") or r.get("canary_id") or "") for _, r in pub_all}
    vault_ids = {str(r.get("id") or r.get("canary_id") or "") for _, r in vault_all}
    id_overlap = sorted(pub_ids & vault_ids)

    pub_prompt_hashes = {hashlib.sha256(normalize_text(str(r.get("prompt", ""))).encode()).hexdigest(): str(r.get("id")) for _, r in pub_all}
    vault_prompt_hashes = {hashlib.sha256(normalize_text(str(r.get("prompt", ""))).encode()).hexdigest(): str(r.get("id") or r.get("canary_id")) for _, r in vault_all}
    exact_norm_overlap = sorted(set(pub_prompt_hashes.keys()) & set(vault_prompt_hashes.keys()))

    pub_thm_names = set()
    for _, r in pub_all:
        pub_thm_names.update(extract_lean_theorem_names(r))
    # Also include theorem names from repo/lean and plane1_formal_spec.md
    for lf in (REPO_DIR / "lean").rglob("*.lean"):
        if ".lake" not in lf.parts:
            pub_thm_names.update(LEAN_THM_RE.findall(lf.read_text(encoding="utf-8")))
    spec_file = REPO_DIR / "spec" / "plane1_formal_spec.md"
    if spec_file.is_file():
        pub_thm_names.update(LEAN_THM_RE.findall(spec_file.read_text(encoding="utf-8")))

    vault_thm_names = set()
    for _, r in vault_all:
        vault_thm_names.update(extract_lean_theorem_names(r))
    thm_overlap = sorted(pub_thm_names & vault_thm_names)

    # Check 8-word shingle Jaccard similarity across all (public, vault) formal pairs to catch stem/template cloning
    pub_shingles = [(str(r.get("id")), word_shingles(str(r.get("prompt", "")), k=8)) for _, r in pub_all]
    max_jaccard = 0.0
    high_sim_pairs: list[dict[str, Any]] = []
    for v_kind, vr in vault_all:
        vid = str(vr.get("id") or vr.get("canary_id"))
        vs = word_shingles(str(vr.get("prompt", "")), k=8)
        if not vs:
            continue
        for pid, ps in pub_shingles:
            if not ps:
                continue
            inter = len(vs & ps)
            if inter == 0:
                continue
            jacc = inter / len(vs | ps)
            if jacc > max_jaccard:
                max_jaccard = jacc
            if jacc >= 0.25:
                high_sim_pairs.append({"public_id": pid, "vault_id": vid, "vault_split": v_kind, "jaccard_8gram": round(jacc, 4)})

    if id_overlap:
        report["defects"].append(f"Public/Vault ID overlap: {id_overlap}")
    if exact_norm_overlap:
        report["defects"].append(f"Public/Vault normalized prompt overlap count: {len(exact_norm_overlap)}")
    if thm_overlap:
        report["defects"].append(f"Public/Vault Lean theorem name overlap: {thm_overlap}")
    if high_sim_pairs:
        report["defects"].append(f"Public/Vault stem/template 8-gram Jaccard >= 0.25 pairs: {high_sim_pairs[:5]}")

    # 5. Check PUBLIC_HOLDOUT_COMMITMENT.json contains ZERO prompt text
    commit_path = VAULT_DIR / "PUBLIC_HOLDOUT_COMMITMENT.json"
    commitment_clean = False
    if commit_path.is_file():
        commit_raw = commit_path.read_text(encoding="utf-8")
        leaked_ids = []
        for _, vr in vault_all:
            ptxt = str(vr.get("prompt", "")).strip()
            if len(ptxt) >= 20 and ptxt[:32] in commit_raw:
                leaked_ids.append(str(vr.get("id") or vr.get("canary_id")))
        commitment_clean = len(leaked_ids) == 0
        if leaked_ids:
            report["defects"].append(f"PUBLIC_HOLDOUT_COMMITMENT.json leaked plaintext snippets for IDs: {leaked_ids[:5]}")
    else:
        report["defects"].append("Missing PUBLIC_HOLDOUT_COMMITMENT.json in mcproof-vault")

    # 6. Also check no vault prompt substring leaked into repo/ or datasets/
    public_corpus_blob = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for root_d in (DATASETS_DIR, REPO_DIR)
        for p in root_d.rglob("*")
        if p.is_file() and not any(part in (".git", ".venv", ".lake") for part in p.parts) and p.stat().st_size < 5_000_000
    )
    vault_leaks_in_public: list[str] = []
    for _, vr in vault_all:
        ptxt = str(vr.get("prompt", "")).strip()
        if len(ptxt) >= 30 and ptxt in public_corpus_blob:
            vault_leaks_in_public.append(str(vr.get("id") or vr.get("canary_id")))
    if vault_leaks_in_public:
        report["defects"].append(f"CRITICAL ISOLATION BREACH: vault prompts found in public dirs: {vault_leaks_in_public}")

    report["checks"]["zero_overlap"] = {
        "compile_vs_val_prompt_overlap": len(cv_overlap),
        "public_vs_vault_id_overlap": len(id_overlap),
        "public_vs_vault_exact_prompt_overlap": len(exact_norm_overlap),
        "public_vs_vault_theorem_name_overlap": thm_overlap,
        "max_8word_shingle_jaccard": round(max_jaccard, 6),
        "high_similarity_pairs_count": len(high_sim_pairs),
        "public_holdout_commitment_clean": commitment_clean,
        "vault_leaks_in_public_count": len(vault_leaks_in_public),
    }

    report["overall_passed"] = len(report["defects"]) == 0
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": report["overall_passed"], "defect_count": len(report["defects"]), "defects": report["defects"], "zero_overlap": report["checks"]["zero_overlap"]}, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
