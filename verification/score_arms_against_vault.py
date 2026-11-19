#!/usr/bin/env python3
"""Independent sealed-vault evaluator for Phase 5 & Phase 6 gates.

SECURITY INVARIANT:
- Reads `<workspace>/mcproof-vault/` strictly in-memory.
- NEVER writes any prompt text, gold completion, or raw model completion from
  `<workspace>/mcproof-vault/` into `verification/`
  or stdout!
- Persists ONLY prompt IDs, family/domain/hazard labels, SHA-256 response digests,
  sanitized error rule prefixes, pass counts, latencies, and aggregate gate verdicts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, Sequence

VERIF_DIR = Path(__file__).resolve().parent
REPO_ROOT = VERIF_DIR.parent
_SC_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (REPO_ROOT.parents[1] / "siliconcordat"))
VAULT_ROOT = Path(os.environ.get("MCPROOF_VAULT_DIR") or (REPO_ROOT.parents[1] / "mcproof-vault"))
COMPILE_DIR = Path(os.environ.get("MCPROOF_COMPILE_DIR") or (REPO_ROOT / "compile"))
WEFT_SRC = Path(os.environ.get("WEFT_SRC") or (_SC_ROOT / "weft" / "src"))
EXO_SRC = Path(os.environ.get("EXO_SRC") or (_SC_ROOT / "exo" / "src"))
BASE_GGUF = (
    (COMPILE_DIR / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf")
    if (COMPILE_DIR / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf").is_file()
    else (REPO_ROOT.parent / "compile" / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf")
)
SAFETENSORS_DIR = (
    (COMPILE_DIR / "checkpoints" / "Qwen3.5-4B")
    if (COMPILE_DIR / "checkpoints" / "Qwen3.5-4B").is_dir()
    else (REPO_ROOT.parent / "compile" / "checkpoints" / "Qwen3.5-4B")
)
LLAMA_BIN = Path(os.environ.get("LLAMA_SERVER_BIN") or shutil.which("llama-server") or "llama-server")

for p in (str(VERIF_DIR / "graders"), str(VERIF_DIR), str(WEFT_SRC), str(EXO_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import grade_canaries  # noqa: E402
import grade_holdout  # noqa: E402
import grade_mixed  # noqa: E402
import grade_retention  # noqa: E402
from leak_audit import load_vault_prompts, verify_zero_vault_leak_text  # noqa: E402
from weft.gguf_lora import build_llama_server_lora_flags  # noqa: E402

STOP_TOKENS = ["<|im_end|>", "<|endoftext|>"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def sanitize_err(err: str) -> str:
    # Keep deterministic rule category while stripping any embedded content snippet
    return err.split(":", 1)[0][:80]


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def http_post(url: str, payload: Any, timeout: float = 300.0) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def start_llama_server(cmd: list[str], port: int, log_path: Path, timeout_s: float = 120.0) -> subprocess.Popen[str]:
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT, text=True)
    proc._log_fh = log_fh  # type: ignore[attr-defined]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_fh.flush()
            log_fh.close()
            raise RuntimeError(f"llama-server exited early ({proc.returncode}): {log_path.read_text()[-1200:]}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as r:
                if r.status == 200:
                    return proc
        except urllib.error.HTTPError as he:
            he.close()
            time.sleep(0.15)
        except OSError:
            time.sleep(0.15)
    proc.terminate()
    proc.wait(timeout=5)
    log_fh.close()
    raise RuntimeError(f"Timed out waiting for llama-server /health: {log_path.read_text()[-1200:]}")


def stop_llama_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    fh = getattr(proc, "_log_fh", None)
    if fh is not None:
        fh.close()


def format_qwen35_chat(user_prompt: str, system_prompt: str | None = None) -> str:
    # Exact Qwen3.5 chat_template.jinja with enable_thinking=False:
    # <|im_start|>system\n{sys}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n
    parts: list[str] = []
    if system_prompt:
        parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")
    parts.append(f"<|im_start|>user\n{user_prompt}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    return "".join(parts)


def surface_hygiene_flags(text: str) -> dict[str, bool]:
    low = text.lower()
    return {
        "zero_sorry_admit_native_decide": not any(
            w in text for w in ("sorry", "admit", "native_decide", "implemented_by")
        ),
        "has_what_is_not_proved": "what is not proved" in low,
        "has_what_you_must_trust": "what you must trust" in low,
        "uses_fraction_or_exact_int": ("Fraction" in text) or ("fractions" in text),
        "zero_float_call": "float(" not in text,
        "has_data_eido_skip": "data-eido-skip" in text,
        "zero_em_dash": "\u2014" not in text,
    }


def query_split(
    base_url: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    lora: Sequence[Mapping[str, Any]] = (),
    logit_bias: list[Any] | None = None,
    system_prompt: str | None = None,
    cache_prompt: bool = False,
    erase_each: bool = True,
    max_tokens: int = 512,
) -> tuple[dict[str, str], dict[str, float]]:
    responses: dict[str, str] = {}
    latencies_ms: dict[str, float] = {}
    for rec in rows:
        iid = str(rec["id"])
        if erase_each and not cache_prompt:
            http_post(f"{base_url}/slots/0?action=erase", {})
        rendered = format_qwen35_chat(str(rec["prompt"]), system_prompt=system_prompt)
        req: dict[str, Any] = {
            "prompt": rendered,
            "n_predict": max_tokens,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "cache_prompt": cache_prompt,
            "stop": STOP_TOKENS,
            "lora": list(lora),
            "id_slot": 0,
        }
        if logit_bias is not None:
            req["logit_bias"] = logit_bias
        t0 = time.perf_counter()
        resp = http_post(f"{base_url}/completion", req, timeout=300.0)
        latencies_ms[iid] = round((time.perf_counter() - t0) * 1000.0, 2)
        responses[iid] = str(resp.get("content", ""))
    return responses, latencies_ms


def summarize_holdout_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
    *,
    sop_tokens: int = 0,
) -> dict[str, Any]:
    raw_rep = grade_holdout.grade_batch(responses, max_workers=8)
    error_hist: dict[str, int] = {}
    hygiene_totals: dict[str, int] = {}
    per_item_sanitized = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        hyg = surface_hygiene_flags(txt)
        for hk, hv in hyg.items():
            if hv:
                hygiene_totals[hk] = hygiene_totals.get(hk, 0) + 1
        san_errs = [sanitize_err(e) for e in o["errors"]]
        for se in san_errs:
            error_hist[se] = error_hist.get(se, 0) + 1
        per_item_sanitized.append(
            {
                "id": iid,
                "family": o["family"],
                "passed": o["passed"],
                "error_categories": san_errs,
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    n = max(1, raw_rep["total_count"])
    return {
        "split": "private_holdout_96",
        "total_passed": raw_rep["total_passed"],
        "total_count": raw_rep["total_count"],
        "pass_rate": raw_rep["pass_rate"],
        "failure_rate": raw_rep["failure_rate"],
        "sop_injected_tokens": sop_tokens,
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / n, 2),
        "by_family": raw_rep["by_family"],
        "surface_hygiene_rates": {k: round(v / n, 4) for k, v in sorted(hygiene_totals.items())},
        "top_error_categories": dict(sorted(error_hist.items(), key=lambda kv: -kv[1])[:15]),
        "failed_ids": raw_rep["failed_ids"],
        "items": per_item_sanitized,
    }


def summarize_retention_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    raw_rep = grade_retention.grade_batch(responses, max_workers=8)
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        items.append(
            {
                "id": iid,
                "domain": o["domain"],
                "passed": o["passed"],
                "error_categories": [sanitize_err(e) for e in o["errors"]],
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    return {
        "split": "general_retention_100",
        "total_passed": raw_rep["total_passed"],
        "total_count": raw_rep["total_count"],
        "accuracy_pct": raw_rep["accuracy_pct"],
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / max(1, raw_rep["total_count"]), 2),
        "by_domain": raw_rep["by_domain"],
        "failed_ids": raw_rep["failed_ids"],
        "items": items,
    }


def summarize_mixed_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    raw_rep = grade_mixed.grade_batch(responses, max_workers=8)
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        items.append(
            {
                "id": iid,
                "hazard_id": o["hazard_id"],
                "zone": o["zone"],
                "passed": o["passed"],
                "formal_corruption_categories": [sanitize_err(e) for e in o["formal_block_corruptions"]],
                "prose_or_zone_leak_categories": [sanitize_err(e) for e in o["prose_or_zone_leaks"]],
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    return {
        "split": "mixed_composition_30",
        "total_passed": raw_rep["total_passed"],
        "total_count": raw_rep["total_count"],
        "corrupted_formal_blocks": raw_rep["corrupted_formal_blocks"],
        "prose_or_zone_leaks": raw_rep["prose_or_zone_leaks"],
        "phase5_mixed_integrity_gate": raw_rep["phase5_mixed_integrity_gate"],
        "phase6_tc2_isolation_gate": raw_rep["phase6_tc2_isolation_gate"],
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / max(1, raw_rep["total_count"]), 2),
        "by_hazard": raw_rep["by_hazard"],
        "failed_ids": raw_rep["failed_ids"],
        "items": items,
    }


def summarize_canaries_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    raw_rep = grade_canaries.grade_canary_map(responses)
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        items.append(
            {
                "id": iid,
                "category": o["category"],
                "family": o["family"],
                "difficulty_rung": o["difficulty_rung"],
                "passed": o["passed"],
                "failure_categories": [sanitize_err(e) for e in o["failure_codes"]],
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    return {
        "split": "canaries_16",
        "verdict": raw_rep["verdict"],
        "preservation_passed": raw_rep["preservation_passed"],
        "preservation_total": raw_rep["preservation_total"],
        "formal_passed": raw_rep["formal_passed"],
        "formal_total": raw_rep["formal_total"],
        "total_passed": raw_rep["total_passed"],
        "total_count": raw_rep["total_count"],
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / max(1, raw_rep["total_count"]), 2),
        "failed_ids": raw_rep["failed_ids"],
        "items": items,
    }


def run_b0_baseline() -> dict[str, Any]:
    holdout_rows = load_jsonl(VAULT_ROOT / "private_holdout.jsonl")
    ret_rows = load_jsonl(VAULT_ROOT / "general_retention_100.jsonl")
    mixed_rows = load_jsonl(VAULT_ROOT / "mixed_composition_30.jsonl")
    canary_rows = load_jsonl(VAULT_ROOT / "canaries_16.jsonl")

    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="verif_b0_") as td:
        slot_dir = Path(td) / "slots"
        slot_dir.mkdir()
        cmd = [
            str(LLAMA_BIN),
            "-m",
            str(BASE_GGUF),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-c",
            "4096",
            "-ngl",
            "99",
            "--parallel",
            "1",
            "--slots",
            "--slot-save-path",
            str(slot_dir),
            "--no-cache-idle-slots",
            "--slot-prompt-similarity",
            "0.0",
            "--ctx-checkpoints",
            "0",
            "--chat-template-kwargs",
            '{"enable_thinking":false}',
        ]
        proc = start_llama_server(cmd, port, Path(td) / "llama_b0.log")
        try:
            h_resp, h_lat = query_split(base_url, holdout_rows, max_tokens=512)
            r_resp, r_lat = query_split(base_url, ret_rows, max_tokens=384)
            m_resp, m_lat = query_split(base_url, mixed_rows, max_tokens=512)
            c_resp, c_lat = query_split(base_url, canary_rows, max_tokens=192)
        finally:
            stop_llama_server(proc)

    out = {
        "schema": "verifier-vault-arm-receipt/v0.1",
        "arm": "B0",
        "checkpoint_gguf": BASE_GGUF.name,
        "checkpoint_sha256": "10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1",
        "decoding": {"temperature": 0.0, "top_p": 1.0, "seed": 42, "enable_thinking": False},
        "private_holdout": summarize_holdout_sanitized(h_resp, h_lat, sop_tokens=0),
        "general_retention": summarize_retention_sanitized(r_resp, r_lat),
        "mixed_composition": summarize_mixed_sanitized(m_resp, m_lat),
        "canaries_16": summarize_canaries_sanitized(c_resp, c_lat),
    }
    (VERIF_DIR / "vault_arm_b0.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def run_b1_ceiling() -> dict[str, Any]:
    spec_path = REPO_ROOT / "spec" / "plane1_formal_spec.md"
    spec_bytes = spec_path.read_bytes()
    if any(b < 32 and b not in (9, 10, 13) for b in spec_bytes):
        raise RuntimeError("Refusing B1 run until spec/plane1_formal_spec.md has 0 control/NUL bytes!")
    spec_text = spec_bytes.decode("utf-8")
    spec_sha = hashlib.sha256(spec_bytes).hexdigest()

    # Exact Qwen3.5 token count via llama-tokenize or HF tokenizer in compile/.venv
    tok_py = COMPILE_DIR / ".venv" / "bin" / "python"
    tok_cnt_str = subprocess.check_output(
        [
            str(tok_py),
            "-c",
            f"from transformers import AutoTokenizer; t=AutoTokenizer.from_pretrained({str(SAFETENSORS_DIR)!r}); "
            f"from pathlib import Path; s=Path({str(spec_path)!r}).read_text(); print(len(t.encode(s, add_special_tokens=False)))",
        ],
        text=True,
    ).strip()
    spec_tokens = int(tok_cnt_str)

    holdout_rows = load_jsonl(VAULT_ROOT / "private_holdout.jsonl")
    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    ctx_b1 = max(40960, spec_tokens + 4096)
    cmd = [
        str(LLAMA_BIN),
        "-m",
        str(BASE_GGUF),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-c",
        str(ctx_b1),
        "-ngl",
        "99",
        "--parallel",
        "1",
        "--chat-template-kwargs",
        '{"enable_thinking":false}',
    ]
    with tempfile.TemporaryDirectory(prefix="verif_b1_") as td_b1:
        proc = start_llama_server(cmd, port, Path(td_b1) / "llama_b1.log", timeout_s=150.0)
        try:
            # Check prefix-cache parity on first prompt before using cache_prompt=True across all 96
            p0 = format_qwen35_chat(str(holdout_rows[0]["prompt"]), system_prompt=spec_text)
            r_uncached = http_post(
                f"{base_url}/completion",
                {
                    "prompt": p0,
                    "n_predict": 32,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "seed": 42,
                    "cache_prompt": False,
                    "stop": STOP_TOKENS,
                    "id_slot": 0,
                },
                timeout=300.0,
            )
            r_cached = http_post(
                f"{base_url}/completion",
                {
                    "prompt": p0,
                    "n_predict": 32,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "seed": 42,
                    "cache_prompt": True,
                    "stop": STOP_TOKENS,
                    "id_slot": 0,
                },
                timeout=300.0,
            )
            prefix_parity = str(r_uncached.get("content", ""))[:64] == str(r_cached.get("content", ""))[:64]

            h_resp, h_lat = query_split(
                base_url,
                holdout_rows,
                system_prompt=spec_text,
                cache_prompt=True,
                erase_each=False,
                max_tokens=512,
            )
        finally:
            stop_llama_server(proc)

    out = {
        "schema": "verifier-vault-arm-receipt/v0.1",
        "arm": "B1",
        "plane1_spec_sha256": spec_sha,
        "plane1_spec_qwen35_tokens": spec_tokens,
        "prefix_cache_parity_verified": prefix_parity,
        "decoding": {"temperature": 0.0, "top_p": 1.0, "seed": 42, "enable_thinking": False},
        "private_holdout": summarize_holdout_sanitized(h_resp, h_lat, sop_tokens=spec_tokens),
    }
    (VERIF_DIR / "vault_arm_b1.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def run_compiled_adapters(p2b_scale: float = 1.0) -> dict[str, Any]:
    art_dir = COMPILE_DIR / "artifacts"
    p2a_gguf = art_dir / "p2a" / "formal-verification.p2a.f16.gguf"
    p2b_gguf = art_dir / "p2b" / "formal-verification.p2b.f16.gguf"
    sab_gguf = art_dir / "controls" / "formal-verification.sabotage.f16.gguf"
    gh_gguf = art_dir / "controls" / "formal-verification.goodhart.f16.gguf"
    lb_json = art_dir / "controls" / "constant_logit_bias.json"

    comp_dir = art_dir / "composition"
    corpus_gguf = comp_dir / "corpus.f16.gguf"
    eido_gguf = comp_dir / "weft-eido.f16.gguf"

    logit_bias_payload = json.loads(lb_json.read_text(encoding="utf-8"))["llama_server_logit_bias"]

    holdout_rows = load_jsonl(VAULT_ROOT / "private_holdout.jsonl")
    ret_rows = load_jsonl(VAULT_ROOT / "general_retention_100.jsonl")
    mixed_rows = load_jsonl(VAULT_ROOT / "mixed_composition_30.jsonl")
    canary_rows = load_jsonl(VAULT_ROOT / "canaries_16.jsonl")
    mixed_specs = grade_mixed.load_specs()

    adapter_list = [p2a_gguf, p2b_gguf, sab_gguf, gh_gguf]
    has_companion = corpus_gguf.is_file() and eido_gguf.is_file()
    if has_companion:
        # id 4 = corpus, id 5 = weft-eido
        adapter_list.extend([corpus_gguf, eido_gguf])

    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    results: dict[str, Any] = {
        "schema": "verifier-vault-adapters-receipt/v0.1",
        "p2b_scale": p2b_scale,
        "adapter_sha256s": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in adapter_list},
        "arms": {},
    }

    with tempfile.TemporaryDirectory(prefix="verif_adapters_") as td:
        slot_dir = Path(td) / "slots"
        slot_dir.mkdir()
        lora_flags = build_llama_server_lora_flags(adapter_list, initial_scale=0.0, slot_save_path=slot_dir)
        cmd = [
            str(LLAMA_BIN),
            "-m",
            str(BASE_GGUF),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-c",
            "4096",
            "-ngl",
            "99",
            "--parallel",
            "1",
            "--chat-template-kwargs",
            '{"enable_thinking":false}',
            *lora_flags,
        ]
        proc = start_llama_server(cmd, port, Path(td) / "llama_b0.log")
        try:
            # 1. P2-A on holdout + canaries
            p2a_h, p2a_hl = query_split(base_url, holdout_rows, lora=[{"id": 0, "scale": p2b_scale}], max_tokens=512)
            p2a_c, p2a_cl = query_split(base_url, canary_rows, lora=[{"id": 0, "scale": p2b_scale}], max_tokens=192)
            results["arms"]["P2-A"] = {
                "private_holdout": summarize_holdout_sanitized(p2a_h, p2a_hl),
                "canaries_16": summarize_canaries_sanitized(p2a_c, p2a_cl),
            }

            # 2. P2-B on ALL FOUR vault splits (holdout, retention, mixed, canaries)
            p2b_h, p2b_hl = query_split(base_url, holdout_rows, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=512)
            p2b_r, p2b_rl = query_split(base_url, ret_rows, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=384)
            p2b_m, p2b_ml = query_split(base_url, mixed_rows, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=512)
            p2b_c, p2b_cl = query_split(base_url, canary_rows, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=192)
            results["arms"]["P2-B"] = {
                "private_holdout": summarize_holdout_sanitized(p2b_h, p2b_hl),
                "general_retention": summarize_retention_sanitized(p2b_r, p2b_rl),
                "mixed_composition": summarize_mixed_sanitized(p2b_m, p2b_ml),
                "canaries_16": summarize_canaries_sanitized(p2b_c, p2b_cl),
            }

            # 3. Constant logit-bias control on holdout + canaries
            lb_h, lb_hl = query_split(base_url, holdout_rows, lora=[], logit_bias=logit_bias_payload, max_tokens=512)
            lb_c, lb_cl = query_split(base_url, canary_rows, lora=[], logit_bias=logit_bias_payload, max_tokens=192)
            results["arms"]["logit_bias"] = {
                "private_holdout": summarize_holdout_sanitized(lb_h, lb_hl),
                "canaries_16": summarize_canaries_sanitized(lb_c, lb_cl),
            }

            # 4. Sabotage patch on canaries + holdout
            sab_c, sab_cl = query_split(base_url, canary_rows, lora=[{"id": 2, "scale": 1.0}], max_tokens=192)
            sab_h, sab_hl = query_split(base_url, holdout_rows, lora=[{"id": 2, "scale": 1.0}], max_tokens=512)
            results["arms"]["sabotage"] = {
                "canaries_16": summarize_canaries_sanitized(sab_c, sab_cl),
                "private_holdout": summarize_holdout_sanitized(sab_h, sab_hl),
            }

            # 5. In-nullspace Goodhart overfit patch on canaries + holdout
            gh_c, gh_cl = query_split(base_url, canary_rows, lora=[{"id": 3, "scale": p2b_scale}], max_tokens=192)
            gh_h, gh_hl = query_split(base_url, holdout_rows, lora=[{"id": 3, "scale": p2b_scale}], max_tokens=512)
            results["arms"]["goodhart"] = {
                "canaries_16": summarize_canaries_sanitized(gh_c, gh_cl),
                "private_holdout": summarize_holdout_sanitized(gh_h, gh_hl),
            }

            # 6. Phase 6 composed stacks on vault (if companion packs present)
            if has_companion:
                # Triple simultaneous stack (corpus=1, eido=1, fv=1) on retention (T-C3) & holdout (T-C1)
                tri_lora = [{"id": 4, "scale": 1.0}, {"id": 5, "scale": 1.0}, {"id": 1, "scale": p2b_scale}]
                tri_r, tri_rl = query_split(base_url, ret_rows, lora=tri_lora, max_tokens=384)
                tri_h, tri_hl = query_split(base_url, holdout_rows, lora=tri_lora, max_tokens=512)

                # Zone-routed 3-pack stack on mixed_composition_30.jsonl (T-C2) & holdout (T-C1)
                import exo.policy as exo_policy
                import exo.router as exo_router

                zm_path = REPO_ROOT / "schemas" / "zone-manifest.v0.1.json"
                z_router_manifest = exo_router.ZoneRouter.from_zone_manifest_file(zm_path)
                z_router_dyn = exo_router.ZoneRouter()

                zr_m_resp: dict[str, str] = {}
                zr_m_lat: dict[str, float] = {}
                dom_to_id = {"corpus": 4, "weft-eido": 5, "formal-verification": 1}
                for mrec in mixed_rows:
                    iid = str(mrec["id"])
                    mspec = mixed_specs[iid]
                    rcfg = mspec["router_check"]
                    pol = exo_policy.RepoPolicy.from_dict(rcfg["repo_policy"])
                    rtr = z_router_manifest if rcfg.get("use_zone_manifest") else z_router_dyn
                    rreq = exo_router.RouteRequest(
                        zone=rcfg["zone"],
                        active_domains=tuple(rcfg["active_domains"]),
                        repo_policy=pol,
                        file_path=rcfg.get("file_path"),
                        contains_formal_claims=bool(rcfg.get("contains_formal_claims", False)),
                        contains_certified_plot=bool(rcfg.get("contains_certified_plot", False)),
                        contains_illustrative_toy=bool(rcfg.get("contains_illustrative_toy", False)),
                        data_eido_skip_marked=bool(rcfg.get("data_eido_skip_marked", False)),
                    )
                    try:
                        dec = rtr.route(rreq)
                        smap = dec.scale_map()
                        dyn_lora = [
                            {"id": dom_to_id[d], "scale": (s * p2b_scale if d == "formal-verification" else s)}
                            for d, s in smap.items()
                            if s > 0.0 and d in dom_to_id
                        ]
                        http_post(f"{base_url}/slots/0?action=erase", {})
                        rendered = format_qwen35_chat(str(mrec["prompt"]))
                        t0 = time.perf_counter()
                        resp = http_post(
                            f"{base_url}/completion",
                            {
                                "prompt": rendered,
                                "n_predict": 512,
                                "temperature": 0.0,
                                "top_p": 1.0,
                                "seed": 42,
                                "cache_prompt": False,
                                "stop": STOP_TOKENS,
                                "lora": dyn_lora,
                                "id_slot": 0,
                            },
                        )
                        zr_m_lat[iid] = round((time.perf_counter() - t0) * 1000.0, 2)
                        zr_m_resp[iid] = str(resp.get("content", ""))
                    except exo_router.ContestedPreferenceError as cpe:
                        # Hard Veto 2 deterministic fail-closed router escalation!
                        zr_m_lat[iid] = 0.05
                        zr_m_resp[iid] = (
                            f"ContestedPreferenceError ({cpe.conflict_key}): Hard Veto 2 fail-closed escalation. "
                            f"Set explicit Plane 1 precedence_overrides or data-eido-skip protection before routing."
                        )

                results["arms"]["phase6_triple_simultaneous"] = {
                    "general_retention": summarize_retention_sanitized(tri_r, tri_rl),
                    "private_holdout": summarize_holdout_sanitized(tri_h, tri_hl),
                }
                results["arms"]["phase6_zone_routed_3pack"] = {
                    "mixed_composition": summarize_mixed_sanitized(zr_m_resp, zr_m_lat),
                }
        finally:
            stop_llama_server(proc)

    serialized_ad = json.dumps(results, indent=2, sort_keys=True) + "\n"
    verify_zero_vault_leak_text(serialized_ad, load_vault_prompts(VAULT_ROOT), label="vault_arms_adapters.json")
    (VERIF_DIR / "vault_arms_adapters.json").write_text(serialized_ad, encoding="utf-8")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["b0", "b1", "adapters", "all"], required=True)
    ap.add_argument("--p2b-scale", type=float, default=1.0)
    args = ap.parse_args()

    if args.mode in ("b0", "all"):
        b0 = run_b0_baseline()
        print(
            json.dumps(
                {
                    "arm": "B0",
                    "holdout_pass": f"{b0['private_holdout']['total_passed']}/{b0['private_holdout']['total_count']}",
                    "holdout_by_family": b0["private_holdout"]["by_family"],
                    "retention_acc_pct": b0["general_retention"]["accuracy_pct"],
                    "mixed_pass": f"{b0['mixed_composition']['total_passed']}/{b0['mixed_composition']['total_count']}",
                    "canaries_verdict": b0["canaries_16"]["verdict"],
                },
                indent=2,
            )
        )
    if args.mode in ("b1", "all"):
        b1 = run_b1_ceiling()
        print(
            json.dumps(
                {
                    "arm": "B1",
                    "plane1_spec_tokens": b1["plane1_spec_qwen35_tokens"],
                    "prefix_cache_parity": b1["prefix_cache_parity_verified"],
                    "holdout_pass": f"{b1['private_holdout']['total_passed']}/{b1['private_holdout']['total_count']}",
                    "holdout_by_family": b1["private_holdout"]["by_family"],
                },
                indent=2,
            )
        )
    if args.mode in ("adapters", "all"):
        ad = run_compiled_adapters(p2b_scale=args.p2b_scale)
        summary = {}
        for k, v in ad["arms"].items():
            summary[k] = {
                sk: (sv.get("total_passed"), sv.get("total_count"))
                for sk, sv in v.items()
            }
        print(json.dumps({"adapters_summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
