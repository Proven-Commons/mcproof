#!/usr/bin/env python3
"""Fast (<3s shadow-load compatible) deterministic grader & opaque Stage 3 runner for canaries_16.jsonl."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, Sequence

from common import VAULT_ROOT, sha256_bytes, strip_thinking_blocks

CANARIES_JSONL = VAULT_ROOT / "canaries_16.jsonl"
WARP_CANARIES_JSON = VAULT_ROOT / "warp_canaries_16.json"
SPECS_PATH = VAULT_ROOT / "fixtures" / "canary_specs.json"
GOLD_PATH = VAULT_ROOT / "gold" / "canaries_gold.jsonl"


def _strip_fences(text: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def load_canary_specs() -> list[dict[str, Any]]:
    raw = json.loads(SPECS_PATH.read_text(encoding="utf-8"))
    return list(raw["items"])


def evaluate_canary(response_text: str, spec: Mapping[str, Any]) -> list[str]:
    """Deterministic sub-millisecond rule grader compatible with warp-modeld CanarySpec."""
    response_text = strip_thinking_blocks(response_text)
    failures: list[str] = []
    min_chars = int(spec.get("min_chars", 1))
    max_chars = spec.get("max_chars")
    if len(response_text.strip()) < min_chars:
        failures.append(f"len<{min_chars}")
    if max_chars is not None and len(response_text) > int(max_chars):
        failures.append(f"len>{max_chars}")

    lower_resp = response_text.lower()
    any_of_ci = spec.get("must_contain_any_ci", [])
    if any_of_ci:
        if not any(tok.lower() in lower_resp for tok in any_of_ci):
            failures.append("missing_required_keyword_group")

    for needle in spec.get("must_contain", []):
        if needle not in response_text:
            failures.append(f"missing_exact:{needle}")

    for forbidden in spec.get("must_not_contain", []):
        if forbidden in response_text:
            failures.append(f"forbidden_exact:{forbidden}")

    for forbidden_ci in spec.get("must_not_contain_ci", []):
        if forbidden_ci.lower() in lower_resp:
            failures.append(f"forbidden_ci:{forbidden_ci}")

    prose_forbid = spec.get("prose_only_forbid", [])
    if prose_forbid:
        prose = _strip_fences(response_text)
        for pbad in prose_forbid:
            if pbad in prose:
                failures.append("forbidden_prose_token")

    for pat in spec.get("regex_must_match", []):
        if re.search(pat, response_text, re.MULTILINE) is None:
            failures.append("regex_mismatch")

    for pat in spec.get("regex_must_not_match", []):
        if re.search(pat, response_text, re.MULTILINE) is not None:
            failures.append("forbidden_regex_match")

    return failures


def grade_canary_map(responses_by_id: Mapping[str, str]) -> dict[str, Any]:
    t0 = time.perf_counter()
    specs = load_canary_specs()
    outcomes: list[dict[str, Any]] = []
    pres_passed = 0
    pres_total = 0
    formal_passed = 0
    formal_total = 0

    for spec in specs:
        cid = spec["id"]
        cat = spec["category"]
        resp = responses_by_id.get(cid, "")
        fails = evaluate_canary(resp, spec)
        ok = len(fails) == 0
        if cat == "preservation":
            pres_total += 1
            if ok:
                pres_passed += 1
        else:
            formal_total += 1
            if ok:
                formal_passed += 1
        outcomes.append(
            {
                "id": cid,
                "category": cat,
                "family": spec.get("family"),
                "difficulty_rung": spec.get("difficulty_rung", 0),
                "passed": ok,
                "failure_codes": fails,
            }
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    suite_sha = sha256_bytes(CANARIES_JSONL.read_bytes()) if CANARIES_JSONL.is_file() else ""
    tier1_pass = (pres_passed == pres_total) and (formal_passed == formal_total)
    tier2_pass = (pres_passed == pres_total) and (formal_passed >= max(1, formal_total - 1))
    verdict = "tier1_promote" if tier1_pass else ("tier2_stepping_stone" if tier2_pass else "reject")

    return {
        "suite_sha256": suite_sha,
        "verdict": verdict,
        "preservation_passed": pres_passed,
        "preservation_total": pres_total,
        "formal_passed": formal_passed,
        "formal_total": formal_total,
        "total_passed": pres_passed + formal_passed,
        "total_count": pres_total + formal_total,
        "grader_elapsed_ms": round(elapsed_ms, 3),
        "failed_ids": [o["id"] for o in outcomes if not o["passed"]],
        "outcomes": outcomes,
    }


def _http_json(url: str, method: str = "GET", payload: Mapping[str, Any] | None = None, timeout: float = 15.0) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def _erase_llama_slot(server_url: str, slot_id: int) -> bool:
    base = server_url.rstrip("/")
    for url, method, body in (
        (f"{base}/slots/{slot_id}?action=erase", "POST", {}),
        (f"{base}/slots/{slot_id}?action=erase", "GET", None),
    ):
        try:
            _http_json(url, method=method, payload=body, timeout=5.0)
            return True
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            continue
    return False


def _query_llama_chat(
    server_url: str,
    prompt: str,
    system_prompt: str | None,
    lora: Sequence[Mapping[str, Any]],
    slot_id: int,
    max_tokens: int,
    seed: int = 42,
) -> str:
    base = server_url.rstrip("/")
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": seed,
        "max_tokens": max_tokens,
        "cache_prompt": False,
        "id_slot": slot_id,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if lora:
        payload["lora"] = list(lora)
    resp = _http_json(f"{base}/v1/chat/completions", method="POST", payload=payload, timeout=30.0)
    choices = resp.get("choices", [])
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    raise RuntimeError("llama-server returned no assistant content")


def run_opaque_stage3(
    server_url: str,
    *,
    lora: Sequence[Mapping[str, Any]],
    slot_id: int = 0,
    max_tokens: int = 64,
    flake_runs: int = 1,
    require_tier1: bool = False,
) -> dict[str, Any]:
    """Execute sealed canaries against live llama-server without leaking prompt or completion text."""
    specs = load_canary_specs()
    prompts_by_id = {
        json.loads(line)["id"]: json.loads(line)["prompt"]
        for line in CANARIES_JSONL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    t0 = time.perf_counter()
    first_responses: dict[str, str] = {}
    flaky_ids: set[str] = set()

    for run_idx in range(max(1, flake_runs)):
        for spec in specs:
            cid = spec["id"]
            _erase_llama_slot(server_url, slot_id)
            out_text = _query_llama_chat(
                server_url,
                prompts_by_id[cid],
                spec.get("system_prompt"),
                lora,
                slot_id,
                int(spec.get("max_tokens", max_tokens)),
            )
            if run_idx == 0:
                first_responses[cid] = out_text
            elif out_text != first_responses[cid]:
                flaky_ids.add(cid)

    slot_flushed = _erase_llama_slot(server_url, slot_id)
    total_elapsed_ms = (time.perf_counter() - t0) * 1000.0
    graded = grade_canary_map(first_responses)

    passed_gate = (
        graded["preservation_passed"] == graded["preservation_total"]
        and len(flaky_ids) == 0
        and (graded["verdict"] == "tier1_promote" if require_tier1 else graded["verdict"] != "reject")
    )

    return {
        "stage": "stage3_opaque_canary",
        "passed": passed_gate,
        "verdict": graded["verdict"],
        "suite_sha256": graded["suite_sha256"],
        "preservation_passed": graded["preservation_passed"],
        "preservation_total": graded["preservation_total"],
        "formal_passed": graded["formal_passed"],
        "formal_total": graded["formal_total"],
        "flake_runs": max(1, flake_runs),
        "flaky_ids": sorted(flaky_ids),
        "flaky_count": len(flaky_ids),
        "slot_flushed": slot_flushed,
        "elapsed_ms": round(total_elapsed_ms, 2),
        "failed_ids": graded["failed_ids"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", help="Single canary ID")
    ap.add_argument("--response-file", type=Path, help="Single response file")
    ap.add_argument("--responses", type=Path, help="Batch JSONL of {id, response}")
    ap.add_argument("--verify-gold", action="store_true", help="Verify all 16 canary gold completions + 10x flake check")
    ap.add_argument("--opaque-stage3", action="store_true", help="Run opaque Stage 3 gate against live llama-server")
    ap.add_argument("--server-url", default="http://127.0.0.1:8080", help="llama-server base URL")
    ap.add_argument("--lora-json", default="[]", help="JSON array of {id, scale} LoRA adapters")
    ap.add_argument("--slot-id", type=int, default=0, help="Canary slot ID")
    ap.add_argument("--max-tokens", type=int, default=64, help="Max tokens per canary")
    ap.add_argument("--flake-runs", type=int, default=1, help="Number of repeated runs for flake verification")
    ap.add_argument("--require-tier1", action="store_true", help="Require 16/16 pass (instead of >=7/8 target Tier 2)")
    args = ap.parse_args(argv)

    if args.opaque_stage3:
        lora_list = json.loads(args.lora_json)
        rep = run_opaque_stage3(
            args.server_url,
            lora=lora_list,
            slot_id=args.slot_id,
            max_tokens=args.max_tokens,
            flake_runs=args.flake_runs,
            require_tier1=args.require_tier1,
        )
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0 if rep["passed"] else 1

    if args.verify_gold:
        gold_map: dict[str, str] = {}
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                gold_map[row["id"]] = row["response"]
        first = grade_canary_map(gold_map)
        flaky = []
        for _ in range(9):
            again = grade_canary_map(gold_map)
            if again["outcomes"] != first["outcomes"]:
                flaky.append("variance_detected")
        summary = {k: v for k, v in first.items() if k != "outcomes"}
        summary["flake_10x_zero_variance"] = len(flaky) == 0
        print(json.dumps(summary, indent=2, sort_keys=True))
        ok = first["total_passed"] == first["total_count"] and len(flaky) == 0
        return 0 if ok else 1

    if args.responses is not None:
        resp_map: dict[str, str] = {}
        for line in args.responses.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                resp_map[row["id"]] = str(row.get("response", row.get("completion", "")))
        rep = grade_canary_map(resp_map)
        summary = {k: v for k, v in rep.items() if k != "outcomes"}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if rep["verdict"] != "reject" else 1

    if args.id and args.response_file is not None:
        specs = {s["id"]: s for s in load_canary_specs()}
        if args.id not in specs:
            raise KeyError(f"Unknown canary ID: {args.id}")
        fails = evaluate_canary(args.response_file.read_text(encoding="utf-8"), specs[args.id])
        out = {"id": args.id, "passed": len(fails) == 0, "failure_codes": fails}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if out["passed"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
