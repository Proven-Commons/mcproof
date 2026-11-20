"""Shared multi-window (head/middle/tail) and normalized 8-gram zero-leak audit for mcproof."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Sequence

PRIVATE_PATH_OR_IP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile("/" + "Users/"),
    re.compile("/" + "home/"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
    re.compile("ci@" + r"example\.invalid", re.IGNORECASE),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
)


def load_vault_prompts(vault_root: Path) -> list[str]:
    prompts: list[str] = []
    for fn in (
        "private_holdout.jsonl",
        "general_retention_100.jsonl",
        "mixed_composition_30.jsonl",
        "canaries_16.jsonl",
    ):
        fpath = vault_root / fn
        if not fpath.is_file():
            continue
        for ln in fpath.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                prompts.append(str(json.loads(ln).get("prompt", "")).strip())
    return prompts


def _prompt_windows(prompt: str, width: int = 32) -> list[str]:
    p = prompt.strip()
    if len(p) < 24:
        return []
    if len(p) <= width:
        return [p]
    mid = max(0, (len(p) - width) // 2)
    candidates = [p[:width], p[mid : mid + width], p[-width:]]
    out: list[str] = []
    for c in candidates:
        if len(c) >= 24 and c not in out:
            out.append(c)
    return out


def _word_ngrams(text: str, n: int = 8) -> set[tuple[str, ...]]:
    toks = re.findall(r"[a-z0-9_]+", text.lower())
    if len(toks) < n:
        return set()
    return {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}


def verify_zero_vault_leak_text(
    target_text: str,
    vault_prompts: Sequence[str],
    *,
    label: str = "<text>",
    public_spec_text: str = "",
) -> dict[str, Any]:
    """Verify zero head/middle/tail prompt window leaks and zero 12-word contiguous phrase leaks."""
    windows_checked = 0
    for pr in vault_prompts:
        for win in _prompt_windows(pr, width=32):
            if public_spec_text and win in public_spec_text:
                continue
            windows_checked += 1
            if win in target_text:
                raise RuntimeError(f"SECURITY VIOLATION: vault prompt window leaked in {label}")

    target_12grams = _word_ngrams(target_text, n=12)
    spec_12grams = _word_ngrams(public_spec_text, n=12) if public_spec_text else set()
    if target_12grams:
        for pr in vault_prompts:
            overlap = (target_12grams & _word_ngrams(pr, n=12)) - spec_12grams
            if overlap:
                raise RuntimeError(f"SECURITY VIOLATION: 12-word normalized vault phrase leaked in {label}")

    return {"windows_checked": windows_checked, "prompts_checked": len(vault_prompts)}


def audit_directory_zero_leaks(
    target_dir: Path,
    vault_prompts: Sequence[str],
    *,
    public_datasets_dir: Path | None = None,
    public_spec_path: Path | None = None,
    max_8gram_jaccard_cap: float = 0.15,
) -> dict[str, Any]:
    """Audit all text/JSON files in `target_dir` for head/middle/tail + 12-gram vault leaks and private paths."""
    spec_candidates = [
        public_spec_path,
        target_dir / "spec" / "plane1_formal_spec.md",
        target_dir.parent / "spec" / "plane1_formal_spec.md",
    ]
    resolved_spec: Path | None = None
    for cand in spec_candidates:
        if cand is not None and cand.is_file():
            resolved_spec = cand.resolve()
            break
    public_spec_text = resolved_spec.read_text(encoding="utf-8") if resolved_spec is not None else ""

    files_checked = 0
    windows_per_file = 0
    for p in sorted(target_dir.rglob("*")):
        if not p.is_file():
            continue
        if any(
            part in (".git", ".lake", ".venv", ".pytest_cache", "__pycache__", "rederived_p2b")
            for part in p.parts
        ):
            continue
        if p.name == "leak_audit.py":
            continue
        if p.suffix not in (".json", ".md", ".txt"):
            continue
        raw = p.read_text(encoding="utf-8")
        for rx in PRIVATE_PATH_OR_IP_PATTERNS:
            m = rx.search(raw)
            if m:
                raise RuntimeError(f"HYGIENE VIOLATION: private path/IP {m.group(0)!r} in {p.name}")
        if vault_prompts and (resolved_spec is None or p.resolve() != resolved_spec):
            res = verify_zero_vault_leak_text(
                raw,
                vault_prompts,
                label=p.name,
                public_spec_text=public_spec_text,
            )
            windows_per_file = res["windows_checked"]
        files_checked += 1

    max_jaccard = 0.0
    if vault_prompts and public_datasets_dir is not None and public_datasets_dir.is_dir():
        vault_8 = [_word_ngrams(pr, n=8) for pr in vault_prompts]
        for split in ("compile.jsonl", "validation.jsonl"):
            sp = public_datasets_dir / split
            if not sp.is_file():
                continue
            for ln in sp.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                pub_pr = str(json.loads(ln).get("prompt", ""))
                pub_8 = _word_ngrams(pub_pr, n=8)
                if not pub_8:
                    continue
                for v8 in vault_8:
                    if not v8:
                        continue
                    inter = len(pub_8 & v8)
                    if inter > 0:
                        jac = inter / float(len(pub_8 | v8))
                        if jac > max_jaccard:
                            max_jaccard = jac
        if max_jaccard > max_8gram_jaccard_cap:
            raise RuntimeError(
                f"SECURITY VIOLATION: public vs vault 8-gram Jaccard {max_jaccard:.6f} > {max_8gram_jaccard_cap}"
            )

    summary = {
        "files_checked": files_checked,
        "vault_prompts_checked": len(vault_prompts),
        "head_mid_tail_windows_per_file": windows_per_file,
        "max_public_vs_vault_8gram_jaccard": round(max_jaccard, 6),
    }
    if not vault_prompts:
        summary["vault_comparison"] = "not_performed_no_vault_dir"
    return summary


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    vault_env = os.environ.get("MCPROOF_VAULT_DIR")
    vault_prompts = (
        load_vault_prompts(Path(vault_env).expanduser().resolve())
        if vault_env and Path(vault_env).expanduser().is_dir()
        else []
    )
    summary = audit_directory_zero_leaks(
        repo_root,
        vault_prompts,
        public_datasets_dir=repo_root / "datasets",
    )
    result = {"passed": True, **summary}
    if not vault_prompts:
        result["vault_comparison"] = "not_performed_no_vault_dir"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
