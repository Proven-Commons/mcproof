#!/usr/bin/env python3
"""Independent 10/10 live llama-server zero-variance flake check on the 16 sealed canaries.

SECURITY INVARIANT: Never writes any prompt text, completion text, or secret needle
from <workspace>/mcproof-vault/ to stdout or receipt files. Records only
canary IDs, category/family/rung metadata, response SHA-256 digests across all 10 runs,
pass/fail counts, sanitized rule categories, and dynamically measured checkpoint/server provenance.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request

_VERIF_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _VERIF_DIR.parent
VAULT_ROOT = Path(os.environ.get("MCPROOF_VAULT_DIR") or (_REPO_ROOT.parents[1] / "mcproof-vault"))
PINNED_BASE_GGUF_SHA256 = "10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1"
OUT_JSON = _VERIF_DIR / "canary_zero_flake_receipt.json"

sys.path.insert(0, str(_VERIF_DIR))
from graders import grade_canaries  # noqa: E402
from leak_audit import load_vault_prompts, verify_zero_vault_leak_text  # noqa: E402


def _resolve_base_gguf() -> Path:
    env_p = os.environ.get("MCPROOF_BASE_GGUF")
    if env_p:
        return Path(env_p).expanduser().resolve()
    for cand in (
        _REPO_ROOT / "compile" / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf",
        _REPO_ROOT.parent / "compile" / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf",
    ):
        if cand.is_file():
            return cand.resolve()
    raise FileNotFoundError("Qwen3.5-4B-Q8_0.gguf not found; set MCPROOF_BASE_GGUF")


def _resolve_llama_bin() -> Path:
    env_b = os.environ.get("LLAMA_SERVER_BIN")
    if env_b:
        return Path(env_b).expanduser().resolve()
    found = shutil.which("llama-server")
    if found:
        return Path(found).resolve()
    raise FileNotFoundError("llama-server binary not found on PATH; set LLAMA_SERVER_BIN")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _probe_llama_server_version(llama_bin: Path) -> str:
    proc = subprocess.run([str(llama_bin), "--version"], capture_output=True, text=True, timeout=15, check=False)
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    m = re.search(r"version:\s*([^\r\n]+)", combined)
    if not m:
        raise RuntimeError(f"Unable to parse `llama-server --version` output: {combined.strip()[:240]}")
    ver_line = m.group(1).strip()
    if "commit" not in ver_line:
        raise RuntimeError(f"`llama-server --version` missing commit identifier: {ver_line!r}")
    return ver_line


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def sanitize_failure_code(code: str) -> str:
    return code.split(":", 1)[0]


def main() -> int:
    base_gguf = _resolve_base_gguf()
    llama_bin = _resolve_llama_bin()
    measured_gguf_sha256 = _sha256_file(base_gguf)
    if not hmac.compare_digest(measured_gguf_sha256, PINNED_BASE_GGUF_SHA256):
        raise RuntimeError(
            f"Served GGUF SHA-256 mismatch: measured {measured_gguf_sha256} != pinned {PINNED_BASE_GGUF_SHA256}"
        )
    measured_server_version = _probe_llama_server_version(llama_bin)

    specs = grade_canaries.load_canary_specs()
    prompts_by_id = {
        json.loads(ln)["id"]: json.loads(ln)["prompt"]
        for ln in (VAULT_ROOT / "canaries_16.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    }
    canary_jsonl_sha = _sha256_file(VAULT_ROOT / "canaries_16.jsonl")
    warp_canary_json_sha = _sha256_file(VAULT_ROOT / "warp_canaries_16.json")

    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="verif_canary_10x_") as td:
        slot_dir = Path(td) / "slots"
        slot_dir.mkdir()
        srv_log = Path(td) / "llama_server.log"
        cmd = [
            str(llama_bin),
            "-m",
            str(base_gguf),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-c",
            "2048",
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
        log_fh = srv_log.open("w", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 60.0
            ready = False
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    log_fh.flush()
                    raise RuntimeError(f"llama-server exited early: {srv_log.read_text()[-800:]}")
                try:
                    with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as r:
                        if r.status == 200:
                            ready = True
                            break
                except urllib.error.HTTPError as he:
                    he.close()
                    time.sleep(0.15)
                except OSError:
                    time.sleep(0.15)
            if not ready:
                raise RuntimeError("Timed out waiting for llama-server /health")

            props_build_info: str | None = None
            try:
                with urllib.request.urlopen(f"{base_url}/props", timeout=5.0) as pr:
                    props_obj = json.loads(pr.read().decode("utf-8"))
                    if isinstance(props_obj, dict) and "build_info" in props_obj:
                        props_build_info = str(props_obj["build_info"])
            except OSError:
                props_build_info = None

            n_runs = 10
            t_start = time.perf_counter()
            run_hashes_by_id: dict[str, list[str]] = {s["id"]: [] for s in specs}
            run_pass_by_id: dict[str, list[bool]] = {s["id"]: [] for s in specs}
            first_responses: dict[str, str] = {}
            single_pass_latencies_ms: list[float] = []

            for run_idx in range(n_runs):
                t_pass = time.perf_counter()
                for spec in specs:
                    cid = spec["id"]
                    grade_canaries._erase_llama_slot(base_url, 0)
                    resp_text = grade_canaries._query_llama_chat(
                        base_url,
                        prompts_by_id[cid],
                        spec.get("system_prompt"),
                        [],
                        0,
                        int(spec.get("max_tokens", 128)),
                        seed=42,
                    )
                    resp_sha = hashlib.sha256(resp_text.encode("utf-8")).hexdigest()
                    fails = grade_canaries.evaluate_canary(resp_text, spec)
                    run_hashes_by_id[cid].append(resp_sha)
                    run_pass_by_id[cid].append(len(fails) == 0)
                    if run_idx == 0:
                        first_responses[cid] = resp_text
                single_pass_latencies_ms.append(round((time.perf_counter() - t_pass) * 1000.0, 2))

            total_s = round(time.perf_counter() - t_start, 3)
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            log_fh.close()

    text_flaky_ids = sorted(cid for cid, hashes in run_hashes_by_id.items() if len(set(hashes)) > 1)
    verdict_flaky_ids = sorted(cid for cid, passes in run_pass_by_id.items() if len(set(passes)) > 1)

    graded_b0 = grade_canaries.grade_canary_map(first_responses)
    per_canary_summary = []
    for o in graded_b0["outcomes"]:
        cid = o["id"]
        per_canary_summary.append(
            {
                "id": cid,
                "category": o["category"],
                "family": o["family"],
                "difficulty_rung": o["difficulty_rung"],
                "b0_passed": o["passed"],
                "b0_failure_categories": [sanitize_failure_code(c) for c in o["failure_codes"]],
                "unique_output_sha256_count_over_10_runs": len(set(run_hashes_by_id[cid])),
                "output_sha256_run1": run_hashes_by_id[cid][0],
                "verdict_consistent_10_of_10": len(set(run_pass_by_id[cid])) == 1,
            }
        )

    receipt: dict[str, Any] = {
        "schema": "verifier-canary-zero-flake-receipt/v0.2",
        "checkpoint_gguf": base_gguf.name,
        "checkpoint_gguf_sha256": measured_gguf_sha256,
        "checkpoint_gguf_verified_against_pin": True,
        "llama_server_version": measured_server_version,
        "llama_server_props_build_info": props_build_info,
        "decoding": {
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "cache_prompt": False,
            "enable_thinking": False,
            "slot_erased_before_each_canary": True,
        },
        "canaries_16_jsonl_sha256": canary_jsonl_sha,
        "warp_canaries_16_json_sha256": warp_canary_json_sha,
        "runs_executed": 10,
        "canaries_per_run": len(specs),
        "total_live_inferences": 10 * len(specs),
        "total_elapsed_s": total_s,
        "single_16_canary_sweep_ms_median": sorted(single_pass_latencies_ms)[len(single_pass_latencies_ms) // 2],
        "single_16_canary_sweep_ms_all": single_pass_latencies_ms,
        "output_byte_flaky_ids": text_flaky_ids,
        "verdict_flaky_ids": verdict_flaky_ids,
        "flaky_id_count": len(set(text_flaky_ids) | set(verdict_flaky_ids)),
        "zero_flake_10_of_10_passed": len(text_flaky_ids) == 0 and len(verdict_flaky_ids) == 0,
        "b0_bare_base_summary": {
            "preservation_passed": graded_b0["preservation_passed"],
            "preservation_total": graded_b0["preservation_total"],
            "formal_passed": graded_b0["formal_passed"],
            "formal_total": graded_b0["formal_total"],
            "total_passed": graded_b0["total_passed"],
            "total_count": graded_b0["total_count"],
            "verdict": graded_b0["verdict"],
        },
        "per_canary": per_canary_summary,
    }
    serialized = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    verify_zero_vault_leak_text(serialized, load_vault_prompts(VAULT_ROOT), label="canary_zero_flake_receipt.json")
    OUT_JSON.write_text(serialized, encoding="utf-8")
    print(
        json.dumps(
            {
                "zero_flake_10_of_10_passed": receipt["zero_flake_10_of_10_passed"],
                "flaky_id_count": receipt["flaky_id_count"],
                "checkpoint_gguf_sha256": measured_gguf_sha256,
                "llama_server_version": measured_server_version,
                "single_sweep_median_ms": receipt["single_16_canary_sweep_ms_median"],
            },
            indent=2,
        )
    )
    return 0 if receipt["zero_flake_10_of_10_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
