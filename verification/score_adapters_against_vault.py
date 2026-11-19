#!/usr/bin/env python3
"""Independent 8-slot parallel sealed-vault evaluator for compiled Phase 3 & Phase 6 arms.

SECURITY INVARIANT:
- Reads `<workspace>/mcproof-vault/` strictly in-memory.
- NEVER writes any prompt text, gold completion, or raw model completion from
  `<workspace>/mcproof-vault/` into `verification/`
  or stdout.
- Verifies zero 32+ char vault prompt leakage before writing `vault_arms_adapters.json`.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.request

VERIF_DIR = Path(__file__).resolve().parent
REPO_ROOT = VERIF_DIR.parent
_SC_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (REPO_ROOT.parents[1] / "siliconcordat"))
VAULT_ROOT = Path(os.environ.get("MCPROOF_VAULT_DIR") or (REPO_ROOT.parents[1] / "mcproof-vault"))
COMPILE_DIR = Path(os.environ.get("MCPROOF_COMPILE_DIR") or (REPO_ROOT / "compile"))
WEFT_SRC = Path(os.environ.get("WEFT_SRC") or (_SC_ROOT / "weft" / "src"))
EXO_SRC = Path(os.environ.get("EXO_SRC") or (_SC_ROOT / "exo" / "src"))
ZONE_MANIFEST_PATH = REPO_ROOT / "schemas" / "zone-manifest.v0.1.json"
BASE_GGUF = COMPILE_DIR / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf"
LLAMA_BIN = Path(os.environ.get("LLAMA_SERVER_BIN") or "/opt/homebrew/bin/llama-server")

for p in (str(VAULT_ROOT / "harnesses"), str(WEFT_SRC), str(EXO_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import exo.policy as exo_policy  # noqa: E402
import exo.router as exo_router  # noqa: E402
import grade_canaries  # type: ignore[import-not-found]  # noqa: E402
import grade_holdout  # type: ignore[import-not-found]  # noqa: E402
import grade_mixed  # type: ignore[import-not-found]  # noqa: E402
import grade_retention  # type: ignore[import-not-found]  # noqa: E402
from weft.gguf_lora import build_llama_server_lora_flags  # noqa: E402

STOP_TOKENS = ["<|im_end|>", "<|endoftext|>"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def sanitize_err(err: str) -> str:
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


def start_llama_server(cmd: list[str], port: int, log_path: Path, timeout_s: float = 150.0) -> subprocess.Popen[str]:
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


def query_split_parallel(
    base_url: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    parallel_slots: int = 8,
    lora: Sequence[Mapping[str, Any]] = (),
    logit_bias: list[Any] | None = None,
    max_tokens: int = 512,
) -> tuple[dict[str, str], dict[str, float]]:
    slot_q: queue.Queue[int] = queue.Queue()
    for sid in range(parallel_slots):
        slot_q.put(sid)

    lora_list = list(lora)

    def _run_one(rec: Mapping[str, Any]) -> tuple[str, str, float]:
        iid = str(rec["id"])
        sid = slot_q.get()
        try:
            http_post(f"{base_url}/slots/{sid}?action=erase", {})
            rendered = format_qwen35_chat(str(rec["prompt"]))
            req: dict[str, Any] = {
                "prompt": rendered,
                "n_predict": max_tokens,
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 42,
                "cache_prompt": False,
                "stop": STOP_TOKENS,
                "lora": lora_list,
                "id_slot": sid,
            }
            if logit_bias is not None:
                req["logit_bias"] = logit_bias
            t0 = time.perf_counter()
            resp = http_post(f"{base_url}/completion", req, timeout=300.0)
            ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return iid, str(resp.get("content", "")), ms
        finally:
            slot_q.put(sid)

    responses: dict[str, str] = {}
    latencies_ms: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=parallel_slots) as pool:
        futs = [pool.submit(_run_one, r) for r in rows]
        for fut in as_completed(futs):
            iid, content, ms = fut.result()
            responses[iid] = content
            latencies_ms[iid] = ms
    return responses, latencies_ms


def _clean_null_bytes(responses: Mapping[str, str]) -> tuple[dict[str, str], set[str]]:
    cleaned: dict[str, str] = {}
    had_null: set[str] = set()
    for k, v in responses.items():
        if "\x00" in v:
            had_null.add(k)
            cleaned[k] = v.replace("\x00", "\ufffd")
        else:
            cleaned[k] = v
    return cleaned, had_null


def summarize_holdout_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    cleaned_resp, had_null = _clean_null_bytes(responses)
    raw_rep = grade_holdout.grade_batch(cleaned_resp, max_workers=8)
    error_hist: dict[str, int] = {}
    hygiene_totals: dict[str, int] = {}
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        hyg = surface_hygiene_flags(txt)
        for hk, hv in hyg.items():
            if hv:
                hygiene_totals[hk] = hygiene_totals.get(hk, 0) + 1
        san_errs = [sanitize_err(e) for e in o["errors"]]
        if iid in had_null:
            san_errs.append("embedded_null_byte")
        for se in san_errs:
            error_hist[se] = error_hist.get(se, 0) + 1
        items.append(
            {
                "id": iid,
                "family": o["family"],
                "passed": bool(o["passed"] and iid not in had_null),
                "error_categories": san_errs,
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    n = max(1, raw_rep["total_count"])
    passed_cnt = sum(1 for it in items if it["passed"])
    return {
        "split": "private_holdout_96",
        "total_passed": passed_cnt,
        "total_count": raw_rep["total_count"],
        "pass_rate": round(passed_cnt / n, 4),
        "failure_rate": round(1.0 - (passed_cnt / n), 4),
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / n, 2),
        "by_family": raw_rep["by_family"],
        "surface_hygiene_rates": {k: round(v / n, 4) for k, v in sorted(hygiene_totals.items())},
        "top_error_categories": dict(sorted(error_hist.items(), key=lambda kv: -kv[1])[:15]),
        "failed_ids": sorted(it["id"] for it in items if not it["passed"]),
        "items": items,
    }


def summarize_retention_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    cleaned_resp, had_null = _clean_null_bytes(responses)
    raw_rep = grade_retention.grade_batch(cleaned_resp, max_workers=8)
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        errs = [sanitize_err(e) for e in o["errors"]]
        if iid in had_null:
            errs.append("embedded_null_byte")
        items.append(
            {
                "id": iid,
                "domain": o["domain"],
                "passed": bool(o["passed"] and iid not in had_null),
                "error_categories": errs,
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    passed_cnt = sum(1 for it in items if it["passed"])
    n = max(1, raw_rep["total_count"])
    return {
        "split": "general_retention_100",
        "total_passed": passed_cnt,
        "total_count": raw_rep["total_count"],
        "accuracy_pct": round((passed_cnt / n) * 100.0, 2),
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / n, 2),
        "by_domain": raw_rep["by_domain"],
        "failed_ids": sorted(it["id"] for it in items if not it["passed"]),
        "items": items,
    }


def summarize_mixed_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    cleaned_resp, had_null = _clean_null_bytes(responses)
    raw_rep = grade_mixed.grade_batch(cleaned_resp, max_workers=8)
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        fc = [sanitize_err(e) for e in o["formal_block_corruptions"]]
        pl = [sanitize_err(e) for e in o["prose_or_zone_leaks"]]
        if iid in had_null:
            fc.append("embedded_null_byte")
        items.append(
            {
                "id": iid,
                "hazard_id": o["hazard_id"],
                "zone": o["zone"],
                "passed": bool(o["passed"] and iid not in had_null),
                "formal_corruption_categories": fc,
                "prose_or_zone_leak_categories": pl,
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    return {
        "split": "mixed_composition_30",
        "total_passed": sum(1 for it in items if it["passed"]),
        "total_count": raw_rep["total_count"],
        "corrupted_formal_blocks": raw_rep["corrupted_formal_blocks"] + len(had_null),
        "prose_or_zone_leaks": raw_rep["prose_or_zone_leaks"],
        "phase5_mixed_integrity_gate": bool(raw_rep["phase5_mixed_integrity_gate"] and not had_null),
        "phase6_tc2_isolation_gate": bool(raw_rep["phase6_tc2_isolation_gate"] and not had_null),
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / max(1, raw_rep["total_count"]), 2),
        "by_hazard": raw_rep["by_hazard"],
        "failed_ids": sorted(it["id"] for it in items if not it["passed"]),
        "items": items,
    }


def summarize_canaries_sanitized(
    responses: Mapping[str, str],
    latencies_ms: Mapping[str, float],
) -> dict[str, Any]:
    cleaned_resp, had_null = _clean_null_bytes(responses)
    raw_rep = grade_canaries.grade_canary_map(cleaned_resp)
    items = []
    for o in raw_rep["outcomes"]:
        iid = o["id"]
        txt = responses.get(iid, "")
        fc = [sanitize_err(e) for e in o["failure_codes"]]
        if iid in had_null:
            fc.append("embedded_null_byte")
        items.append(
            {
                "id": iid,
                "category": o["category"],
                "family": o["family"],
                "difficulty_rung": o["difficulty_rung"],
                "passed": bool(o["passed"] and iid not in had_null),
                "failure_categories": fc,
                "response_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "elapsed_ms": latencies_ms.get(iid, 0.0),
            }
        )
    return {
        "split": "canaries_16",
        "verdict": "reject" if had_null else raw_rep["verdict"],
        "preservation_passed": raw_rep["preservation_passed"],
        "preservation_total": raw_rep["preservation_total"],
        "formal_passed": raw_rep["formal_passed"],
        "formal_total": raw_rep["formal_total"],
        "total_passed": sum(1 for it in items if it["passed"]),
        "total_count": raw_rep["total_count"],
        "mean_elapsed_ms": round(sum(latencies_ms.values()) / max(1, raw_rep["total_count"]), 2),
        "failed_ids": sorted(it["id"] for it in items if not it["passed"]),
        "items": items,
    }


def verify_zero_vault_leak(serialized_json: str, all_vault_rows: Sequence[Mapping[str, Any]]) -> None:
    for row in all_vault_rows:
        prompt_s = str(row.get("prompt", "")).strip()
        probe = prompt_s[:48]
        if len(probe) >= 24 and probe in serialized_json:
            raise RuntimeError(f"SECURITY VIOLATION: vault prompt substring leaked for {row.get('id')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p2b-scale", type=float, default=1.0)
    ap.add_argument("--parallel-slots", type=int, default=8)
    args = ap.parse_args()

    art_dir = COMPILE_DIR / "artifacts"
    p2a_gguf = art_dir / "p2a" / "formal-verification.p2a.f16.gguf"
    p2b_gguf = art_dir / "p2b" / "formal-verification.p2b.f16.gguf"
    sab_gguf = art_dir / "controls" / "formal-verification.sabotage.f16.gguf"
    gh_gguf = art_dir / "controls" / "formal-verification.goodhart.f16.gguf"
    lb_json = art_dir / "ablations" / "constant_logit_bias.json"
    if not lb_json.is_file():
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

    # Adapter IDs: 0=p2a, 1=p2b, 2=sabotage, 3=goodhart, 4=corpus, 5=weft-eido
    adapter_list = [p2a_gguf, p2b_gguf, sab_gguf, gh_gguf, corpus_gguf, eido_gguf]
    for p in adapter_list:
        if not p.is_file():
            raise FileNotFoundError(f"Missing compiled adapter: {p}")

    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    p2b_scale = float(args.p2b_scale)
    pslots = int(args.parallel_slots)

    results: dict[str, Any] = {
        "schema": "verifier-vault-adapters-receipt/v0.1",
        "p2b_scale": p2b_scale,
        "parallel_slots": pslots,
        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "cache_prompt": False,
            "enable_thinking": False,
            "slot_erased_before_every_prompt": True,
        },
        "adapter_sha256s": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in adapter_list},
        "constant_logit_bias_sha256": hashlib.sha256(lb_json.read_bytes()).hexdigest(),
        "arms": {},
    }

    with tempfile.TemporaryDirectory(prefix="verif_adapters_8slot_") as td:
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
            str(max(8192, pslots * 3072)),
            "-ngl",
            "99",
            "--parallel",
            str(pslots),
            "--chat-template-kwargs",
            '{"enable_thinking":false}',
            *lora_flags,
        ]
        proc = start_llama_server(cmd, port, Path(td) / "llama_adapters.log")
        all_vault_rows = [*holdout_rows, *ret_rows, *mixed_rows, *canary_rows]
        out_json_path = VERIF_DIR / "vault_arms_adapters.json"

        def _checkpoint_arm(arm_key: str) -> None:
            s_blob = json.dumps(results, indent=2, sort_keys=True) + "\n"
            verify_zero_vault_leak(s_blob, all_vault_rows)
            out_json_path.write_text(s_blob, encoding="utf-8")
            arm_sub = {
                sk: (
                    f"{sv.get('total_passed')}/{sv.get('total_count')}"
                    if isinstance(sv, Mapping) and "total_passed" in sv
                    else sv
                )
                for sk, sv in results["arms"][arm_key].items()
            }
            print(json.dumps({"checkpointed_arm": arm_key, "scores": arm_sub}), flush=True)

        try:
            # 1. P2-B on ALL FOUR vault splits
            p2b_h, p2b_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=512
            )
            p2b_r, p2b_rl = query_split_parallel(
                base_url, ret_rows, parallel_slots=pslots, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=384
            )
            p2b_m, p2b_ml = query_split_parallel(
                base_url, mixed_rows, parallel_slots=pslots, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=512
            )
            p2b_c, p2b_cl = query_split_parallel(
                base_url, canary_rows, parallel_slots=pslots, lora=[{"id": 1, "scale": p2b_scale}], max_tokens=192
            )
            results["arms"]["P2-B"] = {
                "private_holdout": summarize_holdout_sanitized(p2b_h, p2b_hl),
                "general_retention": summarize_retention_sanitized(p2b_r, p2b_rl),
                "mixed_composition": summarize_mixed_sanitized(p2b_m, p2b_ml),
                "canaries_16": summarize_canaries_sanitized(p2b_c, p2b_cl),
            }
            _checkpoint_arm("P2-B")

            # 2. P2-A (unprojected LoRA) on ALL FOUR vault splits
            p2a_h, p2a_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=[{"id": 0, "scale": p2b_scale}], max_tokens=512
            )
            p2a_r, p2a_rl = query_split_parallel(
                base_url, ret_rows, parallel_slots=pslots, lora=[{"id": 0, "scale": p2b_scale}], max_tokens=384
            )
            p2a_m, p2a_ml = query_split_parallel(
                base_url, mixed_rows, parallel_slots=pslots, lora=[{"id": 0, "scale": p2b_scale}], max_tokens=512
            )
            p2a_c, p2a_cl = query_split_parallel(
                base_url, canary_rows, parallel_slots=pslots, lora=[{"id": 0, "scale": p2b_scale}], max_tokens=192
            )
            results["arms"]["P2-A"] = {
                "private_holdout": summarize_holdout_sanitized(p2a_h, p2a_hl),
                "general_retention": summarize_retention_sanitized(p2a_r, p2a_rl),
                "mixed_composition": summarize_mixed_sanitized(p2a_m, p2a_ml),
                "canaries_16": summarize_canaries_sanitized(p2a_c, p2a_cl),
            }
            _checkpoint_arm("P2-A")

            # 3. Constant logit-bias control on holdout + canaries
            lb_h, lb_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=[], logit_bias=logit_bias_payload, max_tokens=512
            )
            lb_c, lb_cl = query_split_parallel(
                base_url, canary_rows, parallel_slots=pslots, lora=[], logit_bias=logit_bias_payload, max_tokens=192
            )
            results["arms"]["logit_bias"] = {
                "private_holdout": summarize_holdout_sanitized(lb_h, lb_hl),
                "canaries_16": summarize_canaries_sanitized(lb_c, lb_cl),
            }
            _checkpoint_arm("logit_bias")

            # 4. Sabotage patch on canaries + holdout
            sab_c, sab_cl = query_split_parallel(
                base_url, canary_rows, parallel_slots=pslots, lora=[{"id": 2, "scale": 1.0}], max_tokens=192
            )
            sab_h, sab_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=[{"id": 2, "scale": 1.0}], max_tokens=512
            )
            results["arms"]["sabotage"] = {
                "canaries_16": summarize_canaries_sanitized(sab_c, sab_cl),
                "private_holdout": summarize_holdout_sanitized(sab_h, sab_hl),
            }
            _checkpoint_arm("sabotage")

            # 5. In-nullspace Goodhart overfit patch on canaries + holdout
            gh_c, gh_cl = query_split_parallel(
                base_url, canary_rows, parallel_slots=pslots, lora=[{"id": 3, "scale": p2b_scale}], max_tokens=192
            )
            gh_h, gh_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=[{"id": 3, "scale": p2b_scale}], max_tokens=512
            )
            results["arms"]["goodhart"] = {
                "canaries_16": summarize_canaries_sanitized(gh_c, gh_cl),
                "private_holdout": summarize_holdout_sanitized(gh_h, gh_hl),
            }
            _checkpoint_arm("goodhart")

            # 6. Phase 6 Zone-Routed 3-Pack Stack (T-C1, T-C2, T-C3) vs Naive Unprojected Sum
            routed_code_lora = [{"id": 4, "scale": 0.4}, {"id": 1, "scale": 0.5 * p2b_scale}]
            rt_r, rt_rl = query_split_parallel(
                base_url, ret_rows, parallel_slots=pslots, lora=routed_code_lora, max_tokens=384
            )

            sim_ef_lora = [{"id": 5, "scale": 1.0}, {"id": 1, "scale": p2b_scale}]
            sim_h, sim_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=sim_ef_lora, max_tokens=512
            )

            naive_sum_lora = [{"id": 4, "scale": 1.0}, {"id": 5, "scale": 1.0}, {"id": 0, "scale": 1.0}]
            nv_r, nv_rl = query_split_parallel(
                base_url, ret_rows, parallel_slots=pslots, lora=naive_sum_lora, max_tokens=384
            )
            nv_h, nv_hl = query_split_parallel(
                base_url, holdout_rows, parallel_slots=pslots, lora=naive_sum_lora, max_tokens=512
            )

            # Per-item ZoneRouter + Hard Veto 2 fail-closed escalation on mixed_composition_30
            z_router_manifest = exo_router.ZoneRouter.from_zone_manifest_file(ZONE_MANIFEST_PATH)
            z_router_dyn = exo_router.ZoneRouter()
            dom_to_id = {"corpus": 4, "weft-eido": 5, "formal-verification": 1}

            slot_q_mix: queue.Queue[int] = queue.Queue()
            for sid in range(pslots):
                slot_q_mix.put(sid)

            def _run_mixed_routed(mrec: Mapping[str, Any]) -> tuple[str, str, float, str | None]:
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
                except exo_router.ContestedPreferenceError as cpe:
                    msg = (
                        f"ContestedPreferenceError ({cpe.conflict_key}): Hard Veto 2 fail-closed escalation. "
                        f"Set explicit Plane 1 precedence_overrides or data-eido-skip protection before routing."
                    )
                    return iid, msg, 0.05, cpe.conflict_key

                smap = dec.scale_map()
                dyn_lora = [
                    {"id": dom_to_id[d], "scale": (s * p2b_scale if d == "formal-verification" else s)}
                    for d, s in smap.items()
                    if s > 0.0 and d in dom_to_id
                ]
                sid = slot_q_mix.get()
                try:
                    http_post(f"{base_url}/slots/{sid}?action=erase", {})
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
                            "id_slot": sid,
                        },
                        timeout=300.0,
                    )
                    ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    return iid, str(resp.get("content", "")), ms, None
                finally:
                    slot_q_mix.put(sid)

            zr_m_resp: dict[str, str] = {}
            zr_m_lat: dict[str, float] = {}
            contested_ids: list[str] = []
            with ThreadPoolExecutor(max_workers=pslots) as pool:
                futs_m = [pool.submit(_run_mixed_routed, mr) for mr in mixed_rows]
                for fm in as_completed(futs_m):
                    iid, content, ms, ckey = fm.result()
                    zr_m_resp[iid] = content
                    zr_m_lat[iid] = ms
                    if ckey is not None:
                        contested_ids.append(iid)

            results["arms"]["phase6_zone_routed_3pack"] = {
                "general_retention": summarize_retention_sanitized(rt_r, rt_rl),
                "mixed_composition": summarize_mixed_sanitized(zr_m_resp, zr_m_lat),
                "contested_hard_veto2_ids": sorted(contested_ids),
                "simultaneous_research_page_holdout": summarize_holdout_sanitized(sim_h, sim_hl),
            }
            _checkpoint_arm("phase6_zone_routed_3pack")
            results["arms"]["phase6_naive_unprojected_sum"] = {
                "general_retention": summarize_retention_sanitized(nv_r, nv_rl),
                "private_holdout": summarize_holdout_sanitized(nv_h, nv_hl),
            }
            _checkpoint_arm("phase6_naive_unprojected_sum")
        finally:
            stop_llama_server(proc)

    serialized = json.dumps(results, indent=2, sort_keys=True) + "\n"
    verify_zero_vault_leak(serialized, [*holdout_rows, *ret_rows, *mixed_rows, *canary_rows])
    (VERIF_DIR / "vault_arms_adapters.json").write_text(serialized, encoding="utf-8")

    summary: dict[str, Any] = {}
    for arm_name, arm_val in results["arms"].items():
        summary[arm_name] = {
            sk: (
                f"{sv.get('total_passed')}/{sv.get('total_count')}"
                if isinstance(sv, Mapping) and "total_passed" in sv
                else sv
            )
            for sk, sv in arm_val.items()
        }
    print(json.dumps({"adapters_summary": summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
