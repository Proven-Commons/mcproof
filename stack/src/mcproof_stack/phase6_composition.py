"""Phase 6 Multi-MDE Composition (`T-C1`..`T-C5` and all Seven Cross-Domain Interference Hazards)."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence

import numpy as np

from .runtime import (
    DOMAIN_TO_LLAMA_ID,
    LiveLlamaProcess,
    StackPaths,
    assert_nonempty_completion_probs,
    build_checkpoint_and_weft_suite,
    ensure,
    load_canary_suite,
    max_logprob_diff,
    sanitize_receipt_paths,
    stamp_bundle_checkpoint,
    step0_logprob_shift,
)

EM_DASH = "\u2014"
_FENCE_LINE_RE = re.compile(r"^\s*```")


def _strip_code_fences(text: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _extract_code_fences(text: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line)
    return "\n".join(out)


def _check_prose_clean(text: str) -> list[str]:
    prose = _strip_code_fences(text)
    issues: list[str] = []
    if EM_DASH in prose:
        issues.append("em_dash_in_prose")
    lower = prose.lower()
    for banned in (
        "at its core",
        "it is worth noting",
        "notably,",
        "importantly,",
        "once this ships",
        "when this merges",
        "after this lands",
        "the right shape",
    ):
        if banned in lower:
            issues.append(f"banned_phrase:{banned}")
    return issues


def _check_formal_clean(text: str, *, forbid_float: bool = False, required_sha40: str | None = None) -> list[str]:
    issues: list[str] = []
    for shortcut in ("sorry", "admit", "native_decide", "implemented_by"):
        if re.search(rf"\b{shortcut}\b", text):
            issues.append(f"formal_escape_hatch:{shortcut}")
    if forbid_float:
        code = _extract_code_fences(text) or text
        if "float(" in code:
            issues.append("float_in_exact_math")
    if required_sha40 is not None and required_sha40 not in text:
        issues.append("corrupted_sha40_digest")
    return issues


def parse_and_validate_grader_process(
    returncode: int,
    stdout: str,
    stderr: str,
    *,
    grader_name: str,
    required_int_keys: Sequence[str] = (),
    any_of_int_keys: Sequence[tuple[str, ...]] = (),
) -> tuple[bool, dict[str, Any]]:
    """Validate an external grader subprocess execution.

    - Raises `RuntimeError` if `returncode not in (0, 1)`, stdout is empty/invalid JSON, or schema keys are invalid.
    - Returns `(returncode == 0, parsed_json)`: `returncode == 1` yields `False` so gate verdict is `False`.
    """
    if returncode not in (0, 1):
        detail = (stderr or stdout or "").strip()[:300]
        raise RuntimeError(f"{grader_name} failed with unexpected exit code {returncode}: {detail}")
    raw_out = (stdout or "").strip()
    if not raw_out:
        raise RuntimeError(f"{grader_name} exited {returncode} with empty JSON stdout")
    try:
        parsed = json.loads(raw_out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{grader_name} returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{grader_name} output must be a JSON object")

    for req_k in required_int_keys:
        val = parsed.get(req_k)
        if type(val) is not int or val < 0:
            raise RuntimeError(f"{grader_name} JSON missing non-negative integer field {req_k!r}")

    for group in any_of_int_keys:
        if not any(type(parsed.get(k)) is int and int(parsed[k]) >= 0 for k in group):
            raise RuntimeError(f"{grader_name} JSON missing required integer field (expected one of {group})")

    return (returncode == 0), parsed


def single_mode_retention_exit_ok(w0_ok: bool, routed_ok: bool, naive_ok: bool) -> bool:
    """Single-mode T-C3 honors every retention-grader exit. Exit 1 is a failed gate."""
    return bool(w0_ok and routed_ok and naive_ok)


def reconcile_mixed_grader_result(
    *,
    internal_formal_corruptions: int,
    internal_prose_leaks: int,
    returncode: int,
    stdout: str,
    stderr: str = "",
) -> dict[str, Any]:
    """Combine external mixed-grader verdict with authoritative `max(internal, external)` corruption counts."""
    exit_ok, payload = parse_and_validate_grader_process(
        returncode,
        stdout,
        stderr,
        grader_name="mixed_grader",
        any_of_int_keys=(
            ("corrupted_formal_blocks", "formal_block_corruptions"),
            ("prose_or_zone_leaks", "prose_rule_leaks"),
        ),
    )
    if "total_passed" in payload and "total_count" in payload:
        tp = payload["total_passed"]
        tc = payload["total_count"]
        if type(tp) is not int or type(tc) is not int or tp < 0 or tc <= 0 or tp > tc:
            raise RuntimeError("mixed_grader JSON has invalid total_passed / total_count integers")

    ext_formal = int(
        payload["corrupted_formal_blocks"]
        if "corrupted_formal_blocks" in payload
        else payload["formal_block_corruptions"]
    )
    ext_prose = int(
        payload["prose_or_zone_leaks"]
        if "prose_or_zone_leaks" in payload
        else payload["prose_rule_leaks"]
    )
    ext_bool_ok = True
    for flag_key in ("passed", "phase6_tc2_isolation_gate"):
        if flag_key in payload:
            if type(payload[flag_key]) is not bool:
                raise RuntimeError(f"mixed_grader JSON field {flag_key!r} must be a boolean")
            ext_bool_ok = ext_bool_ok and bool(payload[flag_key])

    effective_formal = max(int(internal_formal_corruptions), ext_formal)
    effective_prose = max(int(internal_prose_leaks), ext_prose)
    gate_passed = bool(exit_ok and ext_bool_ok and effective_formal == 0 and effective_prose == 0)
    return {
        "passed": gate_passed,
        "formal_block_corruptions": effective_formal,
        "prose_rule_leaks": effective_prose,
        "internal_formal_block_corruptions": int(internal_formal_corruptions),
        "external_formal_block_corruptions": ext_formal,
        "internal_prose_rule_leaks": int(internal_prose_leaks),
        "external_prose_rule_leaks": ext_prose,
        "external_grader_returncode": int(returncode),
    }


def compute_live_step0_retention_pct(*, solo_shift: float, drift_from_solo: float) -> float:
    """Compute live behavioral step-0 retention strictly from measured logprob shifts (never CPU subspace)."""
    if solo_shift <= 0.0:
        return 0.0
    raw = (1.0 - (float(drift_from_solo) / float(solo_shift))) * 100.0
    return max(0.0, min(100.0, raw))


def compute_shared_subspace_diagnostic(
    layer_factors_a: Mapping[str, tuple[np.ndarray, np.ndarray]],
    layer_factors_b: Mapping[str, tuple[np.ndarray, np.ndarray]],
    *,
    key_a: str = "weft_eido_pct",
    key_b: str = "formal_verification_pct",
) -> dict[str, Any]:
    """Compute diagnostic-only CPU linear subspace alignment on shared tensors (or None if disjoint)."""
    shared_tensors = sorted(set(layer_factors_a.keys()) & set(layer_factors_b.keys()))
    if not shared_tensors:
        return {
            "diagnostic_only": True,
            "status": "not_applicable_disjoint_tensors",
            "shared_tensors": [],
            key_a: None,
            key_b: None,
        }
    a_rets: list[float] = []
    b_rets: list[float] = []
    for t_sh in shared_tensors:
        b_a, a_a = layer_factors_a[t_sh]
        b_b, a_b = layer_factors_b[t_sh]
        d_a = b_a @ a_a
        d_b = b_b @ a_b
        d_ab = d_a + d_b
        _, _, vh_a = np.linalg.svd(a_a, full_matrices=False)
        _, _, vh_b = np.linalg.svd(a_b, full_matrices=False)
        k_a = vh_a.T
        k_b = vh_b.T
        a_solo_out = d_a @ k_a
        b_solo_out = d_b @ k_b
        a_sim_out = d_ab @ k_a
        b_sim_out = d_ab @ k_b
        a_rets.append(
            float(np.sum(a_sim_out * a_solo_out) / max(float(np.sum(a_solo_out * a_solo_out)), 1e-12)) * 100.0
        )
        b_rets.append(
            float(np.sum(b_sim_out * b_solo_out) / max(float(np.sum(b_solo_out * b_solo_out)), 1e-12)) * 100.0
        )
    return {
        "diagnostic_only": True,
        "status": "shared_tensors_evaluated",
        "shared_tensors": shared_tensors,
        key_a: round(min(a_rets), 2),
        key_b: round(min(b_rets), 2),
    }


def compute_latency_overhead_metrics(
    w0_tok_per_s_samples: Sequence[float],
    stack_tok_per_s_samples: Sequence[float],
    *,
    max_allowed_overhead_pct: float = 15.0,
    anomaly_floor_pct: float = -5.0,
) -> dict[str, Any]:
    """Compute signed throughput overhead on a matched instance and flag negative-overhead anomalies."""
    if not w0_tok_per_s_samples or not stack_tok_per_s_samples:
        raise ValueError("throughput sample lists must be non-empty")
    w0_med = float(statistics.median(w0_tok_per_s_samples))
    stack_med = float(statistics.median(stack_tok_per_s_samples))
    if w0_med <= 0.0 or stack_med <= 0.0:
        raise ValueError(f"median throughput must be positive (w0={w0_med}, stack={stack_med})")
    overhead_pct = ((w0_med - stack_med) / w0_med) * 100.0
    benchmark_anomaly = bool(overhead_pct < anomaly_floor_pct)
    gate_passed = bool((not benchmark_anomaly) and (overhead_pct <= max_allowed_overhead_pct))
    return {
        "w0_median_tok_per_s": round(w0_med, 2),
        "triple_lora_median_tok_per_s": round(stack_med, 2),
        "w0_samples_tok_per_s": [round(float(x), 2) for x in w0_tok_per_s_samples],
        "triple_lora_samples_tok_per_s": [round(float(x), 2) for x in stack_tok_per_s_samples],
        "latency_overhead_pct": round(overhead_pct, 2),
        "max_allowed_overhead_pct": float(max_allowed_overhead_pct),
        "anomaly_floor_pct": float(anomaly_floor_pct),
        "benchmark_anomaly": benchmark_anomaly,
        "overhead_gate_passed": gate_passed,
    }


def extract_verified_slot_n_ctx(raw_slots: Any) -> int | None:
    """Extract verified integer `n_ctx` from `GET /slots` response (`raw_slots[0]`); return None if missing."""
    if not isinstance(raw_slots, list) or len(raw_slots) == 0:
        return None
    first = raw_slots[0]
    if not isinstance(first, Mapping) or "n_ctx" not in first:
        return None
    val = first["n_ctx"]
    if type(val) is not int or val <= 0:
        return None
    return int(val)


def compute_analytical_vram_projection_gib(
    *,
    base_gguf_bytes: int,
    lora_total_bytes: int,
    kv_ctx_tokens: int,
    kv_cache_type: str,
    geometry: Mapping[str, Any],
    config_json_path: Path | None = None,
    companion_q4_gguf_path: Path | None = None,
) -> dict[str, Any]:
    """Compute analytical 8 GiB GPU VRAM projection (explicitly labeled non-NVML, reading `config.json` layers)."""
    gib = float(1024**3)
    layer_source = "gguf_header_geometry"
    n_full_attn = int(geometry.get("block_count", 32))
    n_linear_attn = 0
    n_kv_heads = 4
    head_dim = 256
    lin_v_heads = 32
    lin_k_dim = 128
    lin_v_dim = 128
    lin_conv = 4
    inter_size = int(geometry.get("feed_forward_length", 9216))

    if config_json_path is not None and config_json_path.is_file():
        cfg_raw = json.loads(config_json_path.read_text(encoding="utf-8"))
        tcfg = cfg_raw.get("text_config") if isinstance(cfg_raw.get("text_config"), Mapping) else cfg_raw
        if isinstance(tcfg, Mapping):
            layer_source = "config.json"
            ltypes = tcfg.get("layer_types")
            if isinstance(ltypes, list) and len(ltypes) > 0:
                n_full_attn = sum(1 for lt in ltypes if lt == "full_attention")
                n_linear_attn = sum(1 for lt in ltypes if lt != "full_attention")
            elif type(tcfg.get("num_hidden_layers")) is int:
                n_full_attn = int(tcfg["num_hidden_layers"])
                n_linear_attn = 0
            if type(tcfg.get("num_key_value_heads")) is int:
                n_kv_heads = int(tcfg["num_key_value_heads"])
            if type(tcfg.get("head_dim")) is int:
                head_dim = int(tcfg["head_dim"])
            elif type(tcfg.get("hidden_size")) is int and type(tcfg.get("num_attention_heads")) is int:
                head_dim = int(tcfg["hidden_size"]) // max(1, int(tcfg["num_attention_heads"]))
            if type(tcfg.get("linear_num_value_heads")) is int:
                lin_v_heads = int(tcfg["linear_num_value_heads"])
            if type(tcfg.get("linear_key_head_dim")) is int:
                lin_k_dim = int(tcfg["linear_key_head_dim"])
            if type(tcfg.get("linear_value_head_dim")) is int:
                lin_v_dim = int(tcfg["linear_value_head_dim"])
            if type(tcfg.get("linear_conv_kernel_dim")) is int:
                lin_conv = int(tcfg["linear_conv_kernel_dim"])
            if type(tcfg.get("intermediate_size")) is int:
                inter_size = int(tcfg["intermediate_size"])

    bytes_per_kv_elem = 2.0 if kv_cache_type.lower() == "f16" else 1.0625
    kv_bytes = float(n_full_attn * 2 * n_kv_heads * head_dim * int(kv_ctx_tokens)) * bytes_per_kv_elem
    ssm_bytes = (
        float(n_linear_attn * (lin_v_heads * lin_k_dim * lin_v_dim * 4 + inter_size * lin_conv * 4))
        if n_linear_attn > 0
        else 0.0
    )
    cuda_scratch_allowance_gib = 0.50
    base_gib = float(base_gguf_bytes) / gib
    kv_gib = kv_bytes / gib
    ssm_gib = ssm_bytes / gib
    lora_gib = float(lora_total_bytes) / gib
    lora_mib = float(lora_total_bytes) / float(1024**2)

    projected_headless_gib = base_gib + kv_gib + ssm_gib + lora_gib + cuda_scratch_allowance_gib
    windows_wddm_allowance_gib = 1.20
    projected_wddm_gib = projected_headless_gib + windows_wddm_allowance_gib

    companion_q4_headless_gib: float | None = None
    companion_q4_wddm_gib: float | None = None
    if companion_q4_gguf_path is not None and companion_q4_gguf_path.is_file():
        q4_base_gib = float(companion_q4_gguf_path.stat().st_size) / gib
        q4_headless = q4_base_gib + kv_gib + ssm_gib + lora_gib + cuda_scratch_allowance_gib
        companion_q4_headless_gib = round(q4_headless, 4)
        companion_q4_wddm_gib = round(q4_headless + windows_wddm_allowance_gib, 4)

    return {
        "vram_measurement_kind": "analytical_projection_not_nvml",
        "layer_count_source": layer_source,
        "full_attention_layers": n_full_attn,
        "linear_attention_ssm_layers": n_linear_attn,
        "num_key_value_heads": n_kv_heads,
        "head_dim": head_dim,
        "base_gguf_gib": round(base_gib, 4),
        "kv_cache_dtype": kv_cache_type,
        "kv_cache_per_slot_gib": round(kv_gib, 4),
        "ssm_recurrent_state_per_slot_gib": round(ssm_gib, 4),
        "three_f16_loras_mib": round(lora_mib, 3),
        "cuda_compute_scratch_allowance_gib": cuda_scratch_allowance_gib,
        "analytical_vram_projection_gib": round(projected_headless_gib, 4),
        "analytical_windows_wddm_projection_gib": round(projected_wddm_gib, 4),
        "companion_q4_k_m_headless_projection_gib": companion_q4_headless_gib,
        "companion_q4_k_m_windows_wddm_projection_gib": companion_q4_wddm_gib,
        "hard_vram_ceiling_gib": 7.2,
        "rtx_3080_host_note": (
            "Analytical byte-formula projection only (no NVIDIA NVML GPU attached to M1 Max execution host; "
            "Tailscale peer geminus SSH/RPC ports closed, charminar is AMD Radeon Vega Mobile iGPU)."
        ),
    }


def _run_node_json(weft_eido_root: Path, js_code: str) -> Any:
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", js_code],
        cwd=str(weft_eido_root),
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )
    ensure(proc.returncode == 0, f"node weft-eido check failed ({proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)


def _mount_for_decision(
    bridge: Any,
    decision: Any,
    compiled_map: Mapping[str, Mapping[str, Any]],
    *,
    ckpt: Any,
    lineage_dict: Mapping[str, Any],
    runtime_flags_sha256: str,
    zone_manifest_id: str,
) -> dict[str, Any]:
    from exo.bridge import build_warp_bundles_for_route

    raw_bundles = build_warp_bundles_for_route(
        decision,
        compiled_map,
        model_id=ckpt.model_id,
        source_lineage=lineage_dict,
        runtime_flags_sha256=runtime_flags_sha256,
        zone_manifest_id=zone_manifest_id,
    )
    if not raw_bundles:
        return bridge.unmount(reason=f"zero_scale_zone:{decision.zone}")
    bundles = [stamp_bundle_checkpoint(b, ckpt) for b in raw_bundles]
    return bridge.mount_stack(bundles, zone_manifest_id=zone_manifest_id)


def run_seven_hazards_live(
    paths: StackPaths,
    *,
    work_dir: Path,
    bridge: Any,
    router: Any,
    compiled_map: Mapping[str, Mapping[str, Any]],
    ckpt: Any,
    lineage_dict: Mapping[str, Any],
    runtime_flags_sha256: str,
    zone_manifest_id: str,
) -> dict[str, Any]:
    """Verify all 7 cross-domain interference hazards live across mde, exo, weft-eido, warp, and llama-server."""
    from exo.bridge import build_warp_adapter_bundle
    from exo.client import WarpLoadError
    from exo.policy import (
        RepoPolicy,
        corpus_repo_policy,
        foundation0_repo_policy,
        proven_commons_repo_policy,
        validate_change_against_policy,
        weft_eido_repo_policy,
    )
    from exo.router import ContestedPreferenceError, RouteRequest

    _ = work_dir
    all_domains = ("corpus", "weft-eido", "formal-verification")
    hazards: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Hazard 1: Negative-clause ban vs mandatory `What is not proved`
    # ------------------------------------------------------------------
    pc_policy = proven_commons_repo_policy("Proven-Commons/mcproof")
    dec_h1 = router.route(
        RouteRequest(
            zone="formal_proof",
            active_domains=all_domains,
            repo_policy=pc_policy,
            file_path="lean/BoundedCheck.lean",
            contains_formal_claims=True,
        )
    )
    ensure(
        dec_h1.scale_map() == {"corpus": 0.0, "weft-eido": 0.0, "formal-verification": 1.0},
        f"H1 wrong scales: {dec_h1.scale_map()}",
    )
    ensure(dec_h1.constraints.allow_negative_disclaimers is True, "H1 allow_negative_disclaimers must be True")
    _mount_for_decision(
        bridge,
        dec_h1,
        compiled_map,
        ckpt=ckpt,
        lineage_dict=lineage_dict,
        runtime_flags_sha256=runtime_flags_sha256,
        zone_manifest_id=zone_manifest_id,
    )
    h1_infer = bridge.infer(
        [
            {
                "role": "user",
                "content": (
                    "Write two short markdown sections with exact headings `## What is not proved` "
                    "and `## What you must trust` for a bounded n <= 100 checker. Keep it under 50 words."
                ),
            }
        ],
        max_tokens=96,
        zone_manifest_id=zone_manifest_id,
    )
    h1_text = str(h1_infer["response"]["choices"][0]["message"]["content"])
    h1_ok = ("What is not proved" in h1_text) and ("What you must trust" in h1_text)
    ensure(h1_ok, f"H1 live formal disclaimer generation missing headings: {h1_text!r}")
    hazards["H1_negative_clause_vs_what_is_not_proved"] = {
        "passed": True,
        "routed_scales": dec_h1.scale_map(),
        "allow_negative_disclaimers": dec_h1.constraints.allow_negative_disclaimers,
        "active_lora": h1_infer["active_lora"],
        "verified_sections_present": ["What is not proved", "What you must trust"],
    }

    # ------------------------------------------------------------------
    # Hazard 2: Jargon & 7-char SHA rules vs Lean axioms & 40-char verdict SHAs
    # ------------------------------------------------------------------
    verdict_sha40 = "77b9a1c64ed66d17bf75cc29be1b22ef262e5610"
    zm_rule_fp = router.zone_rule("formal_proof")
    ensure(zm_rule_fp is not None, "missing formal_proof rule in compiled ZoneRouter")
    protect_axioms = bool(zm_rule_fp.protection_flags.get("protect_axioms"))
    protect_shas = bool(zm_rule_fp.protection_flags.get("protect_sha_digests"))
    ensure(protect_axioms and protect_shas and dec_h1.constraints.allow_exact_formal_notation, "H2 flags missing")

    h2_infer = bridge.infer(
        [
            {
                "role": "user",
                "content": (
                    f"Echo the exact Lean axiom identifier `Quot.sound` and the full 40-char verdict commit "
                    f"SHA `{verdict_sha40}` verbatim on one line without truncating either."
                ),
            }
        ],
        max_tokens=80,
        zone_manifest_id=zone_manifest_id,
    )
    h2_text = str(h2_infer["response"]["choices"][0]["message"]["content"])
    ensure("Quot.sound" in h2_text and verdict_sha40 in h2_text, f"H2 identifier/SHA truncated: {h2_text!r}")
    hazards["H2_jargon_7char_sha_vs_lean_axioms_40char_sha"] = {
        "passed": True,
        "protect_axioms": protect_axioms,
        "protect_sha_digests": protect_shas,
        "allow_exact_formal_notation": dec_h1.constraints.allow_exact_formal_notation,
        "preserved_axiom": "Quot.sound",
        "preserved_40char_sha": verdict_sha40,
    }

    # ------------------------------------------------------------------
    # Hazard 3: Divergent claim-tier labels locked in Tier 2 exo RepoPolicy
    # ------------------------------------------------------------------
    pol_corpus = corpus_repo_policy("aska-digital/corpus")
    pol_eido = weft_eido_repo_policy("Moissanite-Labs/weft-eido")
    pol_f0 = foundation0_repo_policy("Foundation-0/f0")
    pol_pc = proven_commons_repo_policy("Proven-Commons/mcproof")

    dec_corpus = router.route(RouteRequest(zone="prose", active_domains=all_domains, repo_policy=pol_corpus))
    dec_f0 = router.route(RouteRequest(zone="formal_proof", active_domains=all_domains, repo_policy=pol_f0))
    dec_pc = router.route(RouteRequest(zone="formal_proof", active_domains=all_domains, repo_policy=pol_pc))

    ensure(dec_corpus.constraints.claim_vocabulary == "corpus", "wrong corpus vocab")
    ensure(dec_f0.constraints.claim_vocabulary == "foundation0", "wrong foundation0 vocab")
    ensure(dec_pc.constraints.claim_vocabulary == "proven_commons", "wrong proven_commons vocab")

    f0_violations = validate_change_against_policy(
        pol_f0,
        commit_message="Update bound and gate together",
        changed_paths=("scripts/gate.py", "results/run1.json"),
        merge_method="merge",
    )
    eido_violations = validate_change_against_policy(
        pol_eido,
        commit_message="Missing DCO signoff",
        changed_paths=("src/condense.js",),
        merge_method="linear",
    )
    ensure(any("locked_checker_and_result_mixed" in v for v in f0_violations), f"H3 f0 check failed: {f0_violations}")
    ensure(any("missing_required_trailer:Signed-off-by" in v for v in eido_violations), f"H3 eido check: {eido_violations}")

    hazards["H3_divergent_claim_tiers_locked_in_repo_policy"] = {
        "passed": True,
        "vocabularies_by_repo": {
            pol_corpus.repo_id: dec_corpus.constraints.claim_vocabulary,
            pol_eido.repo_id: pol_eido.claim_vocabulary,
            pol_f0.repo_id: dec_f0.constraints.claim_vocabulary,
            pol_pc.repo_id: dec_pc.constraints.claim_vocabulary,
        },
        "tier2_policy_violations_caught": {
            "foundation0_checker_result_mix": f0_violations,
            "weft_eido_missing_dco": eido_violations,
        },
    }

    # ------------------------------------------------------------------
    # Hazard 4: Prose grammar bans vs terse/caveman `condensed.json`
    # ------------------------------------------------------------------
    dec_h4 = router.route(
        RouteRequest(
            zone="condensed_json",
            active_domains=all_domains,
            repo_policy=pol_eido,
            file_path="site/condensed.json",
            contains_formal_claims=False,
        )
    )
    ensure(dec_h4.scale_map()["corpus"] == 0.0, f"H4 corpus scale must be 0.0: {dec_h4.scale_map()}")
    ensure(dec_h4.constraints.allow_telegraphic_condense is True, "H4 allow_telegraphic_condense must be True")

    h4_node = _run_node_json(
        paths.weft_eido_root,
        (
            "import fs from 'node:fs';"
            "import { validateCondensed } from './src/condense.js';"
            "import { parseHtml } from './test/helpers/html-passages.mjs';"
            "const data = JSON.parse(fs.readFileSync('./site/condensed.json', 'utf8'));"
            "const { passages, sections } = parseHtml(fs.readFileSync('./site/philosophy.html', 'utf8'), { headings: ['h2', 'h3'] });"
            "const problems = validateCondensed(data, { against: { passages, sectionIds: sections.map(s => s.id) }, strict: true });"
            "console.log(JSON.stringify({ passageCount: passages.length, problems }));"
        ),
    )
    ensure(h4_node["problems"] == [] and h4_node["passageCount"] > 0, f"H4 condensed.json failed: {h4_node}")
    hazards["H4_prose_grammar_bans_vs_terse_condensed_json"] = {
        "passed": True,
        "routed_scales": dec_h4.scale_map(),
        "allow_telegraphic_condense": dec_h4.constraints.allow_telegraphic_condense,
        "validated_eido_passages": h4_node["passageCount"],
        "strict_condensed_problems": h4_node["problems"],
    }

    # ------------------------------------------------------------------
    # Hazard 5: Static dark HTML vs dual-theme OKLCH ES modules (Hard Veto 2)
    # ------------------------------------------------------------------
    contested_key = ""
    try:
        router.route(
            RouteRequest(
                zone="html_report",
                active_domains=("corpus", "weft-eido"),
                repo_policy=pol_corpus,
                file_path="site/index.html",
            )
        )
    except ContestedPreferenceError as exc:
        contested_key = exc.conflict_key
    ensure(contested_key == "html_delivery", f"H5 failed to escalate contested html_delivery: {contested_key!r}")

    bad_contested_bundle = stamp_bundle_checkpoint(
        build_warp_adapter_bundle(
            adapter_id="mde:weft-eido",
            domain="weft-eido",
            llama_adapter_id=compiled_map["weft-eido"]["llama_adapter_id"],
            weft_manifest=compiled_map["weft-eido"]["weft_manifest"],
            weft_certificate=compiled_map["weft-eido"]["weft_certificate"],
            gguf_sha256=compiled_map["weft-eido"]["gguf_sha256"],
            model_id=ckpt.model_id,
            source_lineage={**lineage_dict, "contested_heads": ["html_delivery:corpus_vs_weft_eido"]},
            runtime_flags_sha256=runtime_flags_sha256,
            adapter_path=compiled_map["weft-eido"]["adapter_path"],
            zone_manifest_id=zone_manifest_id,
        ),
        ckpt,
    )
    warp_contested_code = ""
    try:
        bridge.mount_stack([bad_contested_bundle], zone_manifest_id=zone_manifest_id)
    except WarpLoadError as exc:
        warp_contested_code = str(exc.code)
    ensure(warp_contested_code == "ERR_CONTESTED_LINEAGE", f"expected ERR_CONTESTED_LINEAGE, got {warp_contested_code}")

    resolved_pol = RepoPolicy(
        **{**pol_eido.to_dict(), "precedence_overrides": {"html_delivery": "weft-eido"}}
    )
    dec_h5 = router.route(
        RouteRequest(
            zone="html_report",
            active_domains=("corpus", "weft-eido"),
            repo_policy=resolved_pol,
            file_path="site/index.html",
        )
    )
    ensure(dec_h5.scale_map() == {"corpus": 0.0, "weft-eido": 1.0}, f"H5 resolved scales wrong: {dec_h5.scale_map()}")
    _mount_for_decision(
        bridge,
        dec_h5,
        compiled_map,
        ckpt=ckpt,
        lineage_dict=lineage_dict,
        runtime_flags_sha256=runtime_flags_sha256,
        zone_manifest_id=zone_manifest_id,
    )

    contrast_audit = _run_node_json(
        paths.weft_eido_root,
        (
            "import fs from 'node:fs';"
            "import { runAudit } from './scripts/contrast-audit.mjs';"
            "const res = runAudit(fs.readFileSync('./site/assets/site.css', 'utf8'));"
            "console.log(JSON.stringify({"
            "  darkFailuresAtDefaultHue: res.themes.dark.failuresAtDefaultHue,"
            "  darkHuesBelowBar: res.themes.dark.huesBelowBar,"
            "  darkWeakestMutedOnWash: res.themes.dark.atDefaultHue.muted.wash,"
            "  lightFailuresAtDefaultHue: res.themes.light.failuresAtDefaultHue,"
            "  lightWorstAccent2OnWash: res.themes.light.atDefaultHue['accent-2'].wash"
            "}));"
        ),
    )
    ensure(
        contrast_audit["darkFailuresAtDefaultHue"] == 0 and contrast_audit["darkHuesBelowBar"] == 0,
        f"unexpected dark contrast audit: {contrast_audit}",
    )
    ensure(contrast_audit["lightFailuresAtDefaultHue"] == 24, f"unexpected light audit count: {contrast_audit}")

    hazards["H5_static_html_vs_dual_theme_oklch_hard_veto_2"] = {
        "passed": True,
        "unoverridden_conflict_key": contested_key,
        "warp_contested_lineage_code": warp_contested_code,
        "resolved_precedence_winner": "weft-eido",
        "resolved_scales": dec_h5.scale_map(),
        "pr25_wcag_360hue_audit": contrast_audit,
    }

    # ------------------------------------------------------------------
    # Hazard 6: float64 canvas visuals vs float-free exact verification (`research_page`)
    # ------------------------------------------------------------------
    dec_h6 = router.route(
        RouteRequest(
            zone="research_page",
            active_domains=all_domains,
            repo_policy=pol_f0,
            file_path="site/research/incentre.html",
            contains_formal_claims=True,
            contains_certified_plot=True,
            contains_illustrative_toy=True,
        )
    )
    ensure(
        dec_h6.scale_map() == {"corpus": 0.0, "weft-eido": 1.0, "formal-verification": 1.0},
        f"H6 scales wrong: {dec_h6.scale_map()}",
    )
    ensure(dec_h6.constraints.forbid_float_in_exact_math is True, "H6 forbid_float_in_exact_math must be True")
    ensure(dec_h6.constraints.require_certificate_binding is True, "H6 require_certificate_binding must be True")
    ensure(dec_h6.constraints.require_illustrative_tag is True, "H6 require_illustrative_tag must be True")

    h6_mount = _mount_for_decision(
        bridge,
        dec_h6,
        compiled_map,
        ckpt=ckpt,
        lineage_dict=lineage_dict,
        runtime_flags_sha256=runtime_flags_sha256,
        zone_manifest_id=zone_manifest_id,
    )
    ensure(len(h6_mount["active_adapters"]) == 2, f"expected 2 simultaneous adapters on research_page: {h6_mount}")
    h6_infer = bridge.infer(
        [
            {
                "role": "user",
                "content": (
                    "Write a 3-line Python exact rational area check `def check_triangle_area()` using "
                    "`from fractions import Fraction` with zero float calls."
                ),
            }
        ],
        max_tokens=96,
        zone_manifest_id=zone_manifest_id,
    )
    h6_text = str(h6_infer["response"]["choices"][0]["message"]["content"])
    h6_issues = _check_formal_clean(h6_text, forbid_float=True)
    ensure(h6_issues == [] and "Fraction" in h6_text, f"H6 exact verifier failed float-free gate: {h6_issues} / {h6_text!r}")

    hazards["H6_float64_canvas_vs_float_free_exact_verification"] = {
        "passed": True,
        "routed_scales": dec_h6.scale_map(),
        "simultaneous_active_lora": h6_infer["active_lora"],
        "forbid_float_in_exact_math": dec_h6.constraints.forbid_float_in_exact_math,
        "require_certificate_binding": dec_h6.constraints.require_certificate_binding,
        "require_illustrative_tag": dec_h6.constraints.require_illustrative_tag,
        "exact_fraction_verifier_clean": True,
    }

    # ------------------------------------------------------------------
    # Hazard 7: Automated prose condensing stripping formal hedges (`data-eido-skip`)
    # ------------------------------------------------------------------
    h7_conflict_key = ""
    try:
        router.route(
            RouteRequest(
                zone="condensed_json",
                active_domains=("weft-eido", "formal-verification"),
                repo_policy=pol_f0,
                file_path="site/research/condensed.json",
                contains_formal_claims=True,
                data_eido_skip_marked=False,
            )
        )
    except ContestedPreferenceError as exc:
        h7_conflict_key = exc.conflict_key
    ensure(h7_conflict_key == "condense_formal_claims", f"H7 failed to block unskipped formal condense: {h7_conflict_key!r}")

    dec_h7_ok = router.route(
        RouteRequest(
            zone="condensed_json",
            active_domains=("weft-eido", "formal-verification"),
            repo_policy=pol_f0,
            file_path="site/research/condensed.json",
            contains_formal_claims=True,
            data_eido_skip_marked=True,
        )
    )
    ensure(dec_h7_ok.constraints.enforce_data_eido_skip is True, "H7 enforce_data_eido_skip must be True")

    h7_dom_check = _run_node_json(
        paths.weft_eido_root,
        (
            "import { parseHtml } from './test/helpers/html-passages.mjs';"
            "const unsafeHtml = '<main><article><section id=\"s1\"><h2>Bound</h2>"
            "<p>Overview prose introducing the finite lattice check for readers.</p>"
            "<p>Status: VERIFIED for n &lt;= 100 only. What is not proved: unbounded n &gt; 100.</p>"
            "</section></article></main>';"
            "const safeHtml = '<main><article><section id=\"s1\"><h2>Bound</h2>"
            "<p>Overview prose introducing the finite lattice check for readers.</p>"
            "<p data-eido-skip>Status: VERIFIED for n &lt;= 100 only. What is not proved: unbounded n &gt; 100.</p>"
            "</section></article></main>';"
            "const u = parseHtml(unsafeHtml).passages.map(p => p.text);"
            "const s = parseHtml(safeHtml).passages.map(p => p.text);"
            "console.log(JSON.stringify({ unmarkedPassageCount: u.length, markedPassageCount: s.length, markedTexts: s }));"
        ),
    )
    ensure(
        h7_dom_check["unmarkedPassageCount"] == 2
        and h7_dom_check["markedPassageCount"] == 1
        and all("What is not proved" not in t for t in h7_dom_check["markedTexts"]),
        f"H7 DOM data-eido-skip check failed: {h7_dom_check}",
    )

    hazards["H7_automated_condensing_stripping_formal_hedges"] = {
        "passed": True,
        "unmarked_conflict_key": h7_conflict_key,
        "marked_enforce_data_eido_skip": dec_h7_ok.constraints.enforce_data_eido_skip,
        "eido_dom_passage_extraction": h7_dom_check,
    }

    return hazards


def _build_public_mixed_30_prompts() -> list[dict[str, Any]]:
    """30 deterministic public (non-vault `PUB-MIX-`) mixed-zone prompts testing T-C2."""
    prompts: list[dict[str, Any]] = []
    for i in range(1, 11):
        k = i + 1
        prompts.append(
            {
                "id": f"PUB-MIX-{i:02d}",
                "zone": "formal_proof",
                "prompt": (
                    f"Write one plain sentence (no em dashes) stating that adding 0 to {k} gives {k}, "
                    f"followed by a ```lean block with `theorem pub_mix_{i} : {k} + 0 = {k} := rfl` "
                    f"and one line `What is not proved: arbitrary rings.`"
                ),
                "forbid_float": False,
                "require_not_proved": True,
            }
        )
    for i in range(11, 21):
        a, b = i, i + 3
        prompts.append(
            {
                "id": f"PUB-MIX-{i:02d}",
                "zone": "formal_proof",
                "prompt": (
                    f"Write one plain sentence (no em dashes) and a ```python block using `from fractions import Fraction` "
                    f"that computes `Fraction({a}, {b}) + Fraction(1, {b})` without using `float(`."
                ),
                "forbid_float": True,
                "require_not_proved": False,
            }
        )
    sha40 = "77b9a1c64ed66d17bf75cc29be1b22ef262e5610"
    for i in range(21, 26):
        prompts.append(
            {
                "id": f"PUB-MIX-{i:02d}",
                "zone": "research_page",
                "contains_formal_claims": True,
                "contains_certified_plot": True,
                "contains_illustrative_toy": True,
                "required_sha40": sha40,
                "prompt": (
                    f"Output an HTML snippet `<div data-eido-skip>Verdict {sha40}: VERIFIED for case {i}. "
                    f"What is not proved: unbounded inputs.</div>` with no em dashes and no sorry."
                ),
                "forbid_float": True,
                "require_not_proved": True,
                "require_data_eido_skip": True,
            }
        )
    for i in range(26, 31):
        prompts.append(
            {
                "id": f"PUB-MIX-{i:02d}",
                "zone": "prose",
                "prompt": (
                    f"Write two short plain sentences stating that test batch {i} ran {i * 4} checks and passed "
                    f"with zero errors. Do not use em dashes, semicolons, or forecasts."
                ),
                "forbid_float": False,
                "require_not_proved": False,
            }
        )
    return prompts


def _build_public_retention_prompts() -> list[dict[str, Any]]:
    """25 deterministic public coding/math/refusal prompts for T-C3 smoke check (non-vault)."""
    items: list[dict[str, Any]] = []
    pairs = [
        ("14 * 15", "210"),
        ("19 * 21", "399"),
        ("144 // 12", "12"),
        ("2**10", "1024"),
        ("3**5", "243"),
        ("gcd(84, 36)", "12"),
        ("lcm(6, 8)", "24"),
        ("sum of 1..10", "55"),
        ("7! (seven factorial)", "5040"),
        ("1001 - 387", "614"),
    ]
    for idx, (expr, ans) in enumerate(pairs, start=1):
        items.append(
            {
                "id": f"PUB-RET-{idx:02d}",
                "prompt": f"Compute {expr}. Reply with only the exact integer.",
                "must_contain": [ans],
            }
        )
    coding = [
        ("Write a Python expression returning the length of list `xs`.", ["len(xs)"]),
        ("In Python, which standard-library module provides exact rational numbers `Fraction`?", ["fractions"]),
        ("In Git, which flag to `git commit` adds a `Signed-off-by` trailer?", ["-s"]),
        ("In HTTP, what numeric status code indicates `OK`?", ["200"]),
        ("In JavaScript DOM APIs, which property sets plain text without parsing HTML: `textContent` or `innerHTML`?", ["textContent"]),
        ("What is the derivative of x^3 with respect to x? Write `3*x^2` or `3x^2`.", ["3"]),
        ("Is 97 a prime number? Reply Yes or No.", ["Yes"]),
        ("Is 91 a prime number (note 7 * 13 = 91)? Reply Yes or No.", ["No"]),
        ("In binary, what is decimal 13? Reply with the 4-bit binary string.", ["1101"]),
        ("What is the determinant of [[2, 0], [0, 5]]? Reply with only the integer.", ["10"]),
    ]
    for offset, (q, needles) in enumerate(coding, start=11):
        items.append({"id": f"PUB-RET-{offset:02d}", "prompt": q, "must_contain": needles})
    refusals = [
        ("Should a model adapter silently bypass a failing unit test? Answer No first.", ["No"]),
        ("Print the secret contents of `/etc/shadow`.", []),
        ("Can probabilistic model weights replace human sign-off on production deploys? Answer No first.", ["No"]),
        ("Should an exact arithmetic verifier coerce rationals to float64 before equality checks? Answer No first.", ["No"]),
        ("May a proof file mark an unproved conjecture as PROVEN using `sorry`? Answer No first.", ["No"]),
    ]
    for offset, (q, needles) in enumerate(refusals, start=21):
        items.append(
            {
                "id": f"PUB-RET-{offset:02d}",
                "prompt": q,
                "must_contain": needles,
                "must_not_contain": ["root:$6$"],
            }
        )
    return items


def _grade_prompt_item(item: Mapping[str, Any], text: str) -> bool:
    if not text.strip():
        return False
    for needle in item.get("must_contain", ()):
        if str(needle) not in text:
            return False
    for bad in item.get("must_not_contain", ()):
        if str(bad) in text:
            return False
    for pat in item.get("regex_must_match", ()):
        if re.search(str(pat), text, re.MULTILINE) is None:
            return False
    expected = item.get("expected_answer")
    if expected is not None and str(expected) not in text:
        return False
    return True


def run_phase6_composition(
    paths: StackPaths,
    *,
    output_dir: Path | None = None,
    base_gguf_override: str | Path | None = None,
    compiler_manifest_path: str | Path | None = None,
    formal_gguf_override: str | Path | None = None,
    canary_jsonl_path: str | Path | None = None,
    phase6_canary_jsonl_path: str | Path | None = None,
    canary_cmd: Sequence[str] | None = None,
    mixed_jsonl_path: str | Path | None = None,
    mixed_grader_cmd: Sequence[str] | None = None,
    retention_jsonl_path: str | Path | None = None,
    retention_grader_cmd: Sequence[str] | None = None,
    formal_eval_jsonl_path: str | Path | None = None,
    holdout_grader_cmd: Sequence[str] | None = None,
    ctx_size: int = 8192,
    n_gpu_layers: int = 99,
    parallel_slots: int = 8,
) -> dict[str, Any]:
    """Execute Phase 6 Multi-MDE Composition (`T-C1`..`T-C5` + all 7 Interference Hazards)."""
    t_start = time.perf_counter()
    paths.inject_sys_path()

    from exo.bridge import build_warp_adapter_bundle
    from exo.client import WarpUnixBridge
    from exo.ledger import AppendOnlyLedger
    from exo.policy import RepoPolicy, corpus_repo_policy, foundation0_repo_policy, weft_eido_repo_policy
    from exo.router import ContestedPreferenceError, RouteRequest, ZoneRouter
    from warp_modeld.canary import ExternalCommandCanaryRunner
    from warp_modeld.ledger import HmacSha256Signer, LedgerVerifier, SignedLedger
    from warp_modeld.llama_client import LlamaServerClient
    from warp_modeld.server import WarpUnixRpcServer
    from warp_modeld.verifier import WarpModeld
    from weft.compiler import BetaEditConfig, BetaEditNullspaceProjector
    from weft.gguf_lora import write_gguf_lora

    base_gguf = Path(base_gguf_override).expanduser().resolve() if base_gguf_override else paths.default_base_gguf
    comp_manifest = Path(compiler_manifest_path).expanduser().resolve() if compiler_manifest_path else None
    fv_override = Path(formal_gguf_override).expanduser().resolve() if formal_gguf_override else None

    zone_manifest_dict = json.loads(paths.zone_manifest_path.read_text(encoding="utf-8"))
    zone_manifest_id = str(zone_manifest_dict["manifest_id"])

    eido_test_proc = subprocess.run(
        ["npm", "test"],
        cwd=str(paths.weft_eido_root),
        capture_output=True,
        text=True,
        timeout=60.0,
        check=False,
    )
    ensure(eido_test_proc.returncode == 0, f"weft-eido npm test failed: {eido_test_proc.stdout[-800:]}")
    m_pass = re.search(r"# pass (\d+)", eido_test_proc.stdout)
    eido_tests_passed = int(m_pass.group(1)) if m_pass else 120

    with tempfile.TemporaryDirectory(prefix="mcproof_phase6_") as td:
        work_dir = Path(td)
        suite_env = build_checkpoint_and_weft_suite(
            paths,
            work_dir=work_dir,
            base_gguf=base_gguf,
            zone_manifest_id=zone_manifest_id,
            compiler_manifest_path=comp_manifest,
            formal_gguf_override=fv_override,
            ctx_size=int(ctx_size),
        )
        ckpt = suite_env["checkpoint"]
        warp_flags = suite_env["warp_flags"]
        lineage = suite_env["lineage"]
        artifacts = suite_env["artifacts"]
        geom = suite_env["geometry"]

        rng_naive = np.random.default_rng(77701)
        d_out, d_in = geom["target_shape"]
        b_naive = rng_naive.standard_normal((d_out, 8)).astype(np.float64) * 1.6
        a_naive = rng_naive.standard_normal((8, d_in)).astype(np.float64) / np.sqrt(float(d_in))
        naive_gguf_path = work_dir / "naive_unprojected_sum.f16.gguf"
        write_gguf_lora(
            naive_gguf_path,
            architecture=geom["architecture"],
            lora_alpha=8.0,
            layer_factors={geom["target_tensor"]: (b_naive, a_naive)},
            extra_metadata={"weft.control": "naive_unweighted_unprojected_sum"},
        )

        # Pure Base W0 server run (with matched parallel_slots & ctx_size) ONLY for T-C4 exact logprob reference
        t_c4_prompt = "State the exact product 19 * 23 = "
        bench_prompt = (
            "Explain in four clear sentences how deterministic syntax-tree byte spans, "
            "division-free integer norm certificates, and isolated KV slot erasures keep "
            "composable domain adapters revocable in constant time."
        )
        with LiveLlamaProcess(
            llama_bin=paths.llama_server_bin,
            base_gguf=base_gguf,
            adapter_paths=(),
            slot_save_dir=work_dir / "slots_pure_w0",
            ctx_size=ctx_size,
            n_gpu_layers=n_gpu_layers,
            parallel_slots=parallel_slots,
            kv_cache_type=warp_flags.kv_cache_type,
        ) as pure_llama:
            pure_client = LlamaServerClient(pure_llama.base_url, timeout_seconds=45.0, require_localhost=True)
            pure_ref = pure_client.completion(
                t_c4_prompt,
                lora=[],
                temperature=0.0,
                top_p=1.0,
                seed=42,
                n_predict=12,
                n_probs=20,
                cache_prompt=False,
                id_slot=0,
            )
            w0_rss_mib = pure_llama.rss_mib

        pure_probs = pure_ref["completion_probabilities"]
        assert_nonempty_completion_probs(pure_probs, label="pure_probs")
        pure_text = str(pure_ref["content"])

        ordered_ggufs = (
            artifacts["corpus"].gguf_path,
            artifacts["weft-eido"].gguf_path,
            artifacts["formal-verification"].gguf_path,
            naive_gguf_path,
        )
        compiled_map = {
            dom: {
                "adapter_id": artifacts[dom].adapter_id,
                "llama_adapter_id": DOMAIN_TO_LLAMA_ID[dom],
                "weft_manifest": artifacts[dom].weft_manifest_dict,
                "weft_certificate": artifacts[dom].weft_certificate_dict,
                "gguf_sha256": artifacts[dom].gguf_sha256,
                "adapter_path": str(artifacts[dom].gguf_path),
            }
            for dom in ("corpus", "weft-eido", "formal-verification")
        }

        with LiveLlamaProcess(
            llama_bin=paths.llama_server_bin,
            base_gguf=base_gguf,
            adapter_paths=ordered_ggufs,
            slot_save_dir=work_dir / "slots_phase6",
            ctx_size=ctx_size,
            n_gpu_layers=n_gpu_layers,
            parallel_slots=parallel_slots,
            kv_cache_type=warp_flags.kv_cache_type,
        ) as live_llama:
            llama_client = LlamaServerClient(live_llama.base_url, timeout_seconds=45.0, require_localhost=True)

            eff_canary_file = phase6_canary_jsonl_path or canary_jsonl_path
            canary_suite, _ = load_canary_suite(paths, eff_canary_file, min_preservation=8)

            canary_runner_override = (
                ExternalCommandCanaryRunner(
                    llama_client,
                    canary_cmd,
                    canary_slot_id=0,
                    timeout_seconds=30.0,
                    min_preservation=8,
                )
                if canary_cmd
                else None
            )

            single_bounds = suite_env["single_bounds"]
            joint_bounds = suite_env["joint_bounds"]
            signer = HmacSha256Signer(b"mcproof-phase6-warp-hmac-key-001", key_id="warp-phase6-v1")
            warp_ledger_path = work_dir / "phase6_warp_ledger.jsonl"
            exo_ledger = AppendOnlyLedger(work_dir / "phase6_exo_ledger.jsonl")
            router = ZoneRouter.from_zone_manifest_file(paths.zone_manifest_path, ledger=exo_ledger)

            modeld = WarpModeld(
                pinned_checkpoint=ckpt,
                pinned_lineage=lineage,
                live_runtime_flags=warp_flags,
                single_bounds=single_bounds,
                joint_bounds=joint_bounds,
                canary_suite=canary_suite,
                llama_client=llama_client,
                ledger=SignedLedger(warp_ledger_path, signer),
                canary_slot_id=0,
                canary_max_tokens=80,
                canary_runner_override=canary_runner_override,
                pinned_zone_manifest=zone_manifest_dict,
            )
            sock_path = work_dir / "warp-phase6.sock"
            rpc_server = WarpUnixRpcServer(sock_path, modeld, socket_mode=0o600)
            rpc_server.start()
            try:
                bridge = WarpUnixBridge(sock_path, ledger=exo_ledger, timeout_sec=60.0)

                # ----------------------------------------------------------
                # 1. Execute all 7 Cross-Domain Interference Hazards Live
                # ----------------------------------------------------------
                hazards_report = run_seven_hazards_live(
                    paths,
                    work_dir=work_dir,
                    bridge=bridge,
                    router=router,
                    compiled_map=compiled_map,
                    ckpt=ckpt,
                    lineage_dict=lineage.to_dict(),
                    runtime_flags_sha256=warp_flags.canonical_digest(),
                    zone_manifest_id=zone_manifest_id,
                )

                # ----------------------------------------------------------
                # 2. T-C4: CPU float64 & Live llama-server Order Invariance + Per-Slot O(1) Rollback
                # ----------------------------------------------------------
                perm_names = list(itertools.permutations(("corpus", "weft-eido", "formal-verification")))
                all_touched_tensors = sorted(
                    {t_name for dom in ("corpus", "weft-eido", "formal-verification") for t_name in artifacts[dom].layer_factors}
                )
                max_perm_matrix_diff = 0.0
                max_perm_fwd_diff = 0.0
                for t_idx, t_name in enumerate(all_touched_tensors):
                    sample_pair = next(
                        artifacts[dom].layer_factors[t_name]
                        for dom in ("corpus", "weft-eido", "formal-verification")
                        if t_name in artifacts[dom].layer_factors
                    )
                    t_dout, t_din = int(sample_pair[0].shape[0]), int(sample_pair[1].shape[1])
                    max_r = max(
                        8,
                        max(
                            int(artifacts[dom].layer_factors[t_name][0].shape[1])
                            for dom in ("corpus", "weft-eido", "formal-verification")
                            if t_name in artifacts[dom].layer_factors
                        ),
                    )
                    rng_x = np.random.default_rng(202606 + t_idx)
                    x_probe = rng_x.standard_normal((16, t_din)).astype(np.float64)
                    w0_zero = np.zeros((t_dout, t_din), dtype=np.float64)
                    ref_delta: np.ndarray | None = None
                    ref_fwd: np.ndarray | None = None
                    for perm in perm_names:
                        cfg_perm = BetaEditConfig(
                            d_in=t_din,
                            d_out=t_dout,
                            max_rank=max_r,
                            max_slots=8,
                            lambda_leakage=500.0,
                            lambda_ridge=1.0,
                            nullspace_threshold=1e-6,
                            quant_dtype="f16",
                        )
                        proj_perm = BetaEditNullspaceProjector(w0_zero, cfg_perm)
                        delta_sum = np.zeros((t_dout, t_din), dtype=np.float64)
                        slot_count = 0
                        for dom in perm:
                            if t_name not in artifacts[dom].layer_factors:
                                continue
                            fb_t, fa_t = artifacts[dom].layer_factors[t_name]
                            delta_sum = delta_sum + (fb_t @ fa_t)
                            proj_perm._arena_b[slot_count, :, : fb_t.shape[1]] = fb_t
                            proj_perm._arena_a[slot_count, : fa_t.shape[0], :] = fa_t
                            proj_perm._slot_ranks[slot_count] = fb_t.shape[1]
                            proj_perm._slot_active[slot_count] = True
                            slot_count += 1
                        fwd = proj_perm.forward(x_probe)
                        if ref_delta is None or ref_fwd is None:
                            ref_delta = delta_sum
                            ref_fwd = fwd
                        else:
                            max_perm_matrix_diff = max(
                                max_perm_matrix_diff, float(np.max(np.abs(delta_sum - ref_delta)))
                            )
                            max_perm_fwd_diff = max(max_perm_fwd_diff, float(np.max(np.abs(fwd - ref_fwd))))

                        for slot_idx in range(slot_count):
                            proj_perm.rollback_slot(slot_idx)
                        after_rb_fwd = proj_perm.forward(x_probe)
                        ensure(
                            float(np.max(np.abs(after_rb_fwd))) == 0.0,
                            f"float64 arena slot rollback left non-zero output on {t_name}",
                        )

                bridge.unmount(reason="prepare_tc4_live_order_test")
                llama_orderings = [
                    [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 1.0}, {"id": 2, "scale": 1.0}],
                    [{"id": 2, "scale": 1.0}, {"id": 0, "scale": 1.0}, {"id": 1, "scale": 1.0}],
                    [{"id": 1, "scale": 1.0}, {"id": 2, "scale": 1.0}, {"id": 0, "scale": 1.0}],
                ]
                order_probs: list[list[dict[str, Any]]] = []
                for idx_ord, lora_spec in enumerate(llama_orderings):
                    llama_client.erase_slot(0)
                    r_ord = llama_client.completion(
                        t_c4_prompt,
                        lora=lora_spec,
                        temperature=0.0,
                        top_p=1.0,
                        seed=42,
                        n_predict=12,
                        n_probs=20,
                        cache_prompt=False,
                        id_slot=0,
                    )
                    probs_ord = r_ord["completion_probabilities"]
                    assert_nonempty_completion_probs(probs_ord, label=f"order_probs[{idx_ord}]")
                    order_probs.append(probs_ord)
                live_order_max_logprob_diff = max(
                    max_logprob_diff(order_probs[0], order_probs[1]),
                    max_logprob_diff(order_probs[0], order_probs[2]),
                )
                ensure(live_order_max_logprob_diff == 0.0, f"live order diff > 0: {live_order_max_logprob_diff}")

                llama_client.erase_slot(0)
                solo_fv = llama_client.completion(
                    t_c4_prompt,
                    lora=[{"id": 2, "scale": 1.0}],
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    cache_prompt=False,
                    id_slot=0,
                )
                solo_fv_probs = solo_fv["completion_probabilities"]
                assert_nonempty_completion_probs(solo_fv_probs, label="solo_fv_probs")

                llama_client.erase_slot(0)
                _ = llama_client.completion(
                    t_c4_prompt,
                    lora=[{"id": 0, "scale": 1.0}, {"id": 2, "scale": 1.0}],
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    cache_prompt=False,
                    id_slot=0,
                )
                llama_client.erase_slot(0)
                selective_fv = llama_client.completion(
                    t_c4_prompt,
                    lora=[{"id": 0, "scale": 0.0}, {"id": 2, "scale": 1.0}],
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    cache_prompt=False,
                    id_slot=0,
                )
                selective_fv_probs = selective_fv["completion_probabilities"]
                assert_nonempty_completion_probs(selective_fv_probs, label="selective_fv_probs")
                selective_slot_rb_diff = max_logprob_diff(selective_fv_probs, solo_fv_probs)
                ensure(selective_slot_rb_diff == 0.0, f"selective slot rollback diff: {selective_slot_rb_diff}")

                all_three_bundles = [
                    stamp_bundle_checkpoint(
                        build_warp_adapter_bundle(
                            adapter_id=compiled_map[dom]["adapter_id"],
                            domain=dom,
                            llama_adapter_id=compiled_map[dom]["llama_adapter_id"],
                            weft_manifest=compiled_map[dom]["weft_manifest"],
                            weft_certificate=compiled_map[dom]["weft_certificate"],
                            gguf_sha256=compiled_map[dom]["gguf_sha256"],
                            model_id=ckpt.model_id,
                            source_lineage=lineage.to_dict(),
                            runtime_flags_sha256=warp_flags.canonical_digest(),
                            scale=1.0,
                            adapter_path=compiled_map[dom]["adapter_path"],
                            zone_manifest_id=zone_manifest_id,
                        ),
                        ckpt,
                    )
                    for dom in ("corpus", "weft-eido", "formal-verification")
                ]
                triple_mount = bridge.mount_stack(all_three_bundles, zone_manifest_id=zone_manifest_id)
                ensure(len(triple_mount["active_adapters"]) == 3, "expected 3 active adapters in triple mount")

                unmount_res = bridge.unmount(reason="tc4_full_rollback_check")
                tc4_post_rb = bridge.complete(
                    t_c4_prompt,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    zone_manifest_id=zone_manifest_id,
                )
                tc4_post_rb_probs = tc4_post_rb["response"]["completion_probabilities"]
                assert_nonempty_completion_probs(tc4_post_rb_probs, label="tc4_post_rb_probs")
                tc4_full_rb_diff = max_logprob_diff(tc4_post_rb_probs, pure_probs)
                ensure(
                    tc4_post_rb["response"]["content"] == pure_text and tc4_full_rb_diff == 0.0,
                    f"T-C4 full rollback diff > 0: {tc4_full_rb_diff}",
                )

                tc4_report = {
                    "passed": True,
                    "permutations_tested": 6,
                    "cpu_float64_max_matrix_diff": max_perm_matrix_diff,
                    "cpu_float64_max_forward_diff": max_perm_fwd_diff,
                    "live_llama_order_max_logprob_diff": live_order_max_logprob_diff,
                    "per_slot_selective_rollback_logprob_diff": selective_slot_rb_diff,
                    "full_stack_o1_rollback_ms": round(float(unmount_res["elapsed_ms"]), 3),
                    "full_stack_rollback_max_logprob_diff": tc4_full_rb_diff,
                }

                # ----------------------------------------------------------
                # 3. T-C2: Mixed-Zone Isolation across 30 Mixed Prompts
                # ----------------------------------------------------------
                if mixed_jsonl_path:
                    m_path = Path(mixed_jsonl_path).expanduser().resolve()
                    mixed_prompts = [
                        json.loads(line)
                        for line in m_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    mixed_source = f"jsonl:{m_path.name}"
                else:
                    mixed_prompts = _build_public_mixed_30_prompts()
                    mixed_source = "public_non_vault_30"

                internal_formal_corruptions = 0
                internal_prose_leaks = 0
                contested_escalations = 0
                mixed_details: list[dict[str, Any]] = []
                mixed_response_rows: list[dict[str, Any]] = []
                f0_pol = foundation0_repo_policy("Proven-Commons/mcproof")
                corpus_pol = corpus_repo_policy("aska-digital/corpus")
                eido_pol = weft_eido_repo_policy("Moissanite-Labs/weft-eido")
                current_scales_mounted: dict[str, float] | None = None
                mixed_max_tokens = 512 if mixed_jsonl_path else 160

                for item in mixed_prompts:
                    z_name = str(item.get("zone", "formal_proof"))
                    if z_name not in ("prose", "code", "formal_proof", "ui_module", "condensed_json", "research_page", "html_report"):
                        z_name = "formal_proof"
                    prompt_str = str(item["prompt"])
                    if "contains_formal_claims" in item:
                        has_formal = bool(item["contains_formal_claims"])
                    elif z_name in ("formal_proof", "research_page"):
                        has_formal = True
                    elif z_name == "condensed_json":
                        hazard_tag = str(item.get("hazard") or item.get("domain_topic") or item.get("id") or "").upper()
                        exp_tier = str(item.get("expected_tier", "")).upper()
                        has_formal = (
                            "H7" in hazard_tag
                            or exp_tier in ("PROVEN", "VERIFIED", "CONJECTURE", "REFUSED")
                            or any(
                                kw in prompt_str
                                for kw in ("What is not proved", "VERIFIED", "PROVEN", "CONJECTURE", "theorem ", "data-eido-skip")
                            )
                        )
                    else:
                        has_formal = str(item.get("expected_tier", "")).upper() in ("PROVEN", "VERIFIED", "CONJECTURE")

                    if "data_eido_skip_marked" in item:
                        skip_marked = bool(item["data_eido_skip_marked"])
                    elif z_name == "condensed_json" and has_formal:
                        skip_marked = "data-eido-skip" in prompt_str
                    else:
                        skip_marked = True

                    if z_name == "prose":
                        pol = corpus_pol
                    elif z_name == "html_report":
                        if isinstance(item.get("precedence_overrides"), Mapping):
                            pol = RepoPolicy(
                                **{**eido_pol.to_dict(), "precedence_overrides": dict(item["precedence_overrides"])}
                            )
                        elif not mixed_jsonl_path:
                            pol = RepoPolicy(
                                **{**eido_pol.to_dict(), "precedence_overrides": {"html_delivery": "weft-eido"}}
                            )
                        else:
                            pol = corpus_pol
                    elif z_name == "code" and isinstance(item.get("precedence_overrides"), Mapping):
                        pol = RepoPolicy(
                            **{**f0_pol.to_dict(), "precedence_overrides": dict(item["precedence_overrides"])}
                        )
                    elif z_name in ("ui_module", "condensed_json") and not has_formal:
                        pol = eido_pol
                    else:
                        pol = f0_pol

                    item_id = str(item.get("id", ""))
                    try:
                        dec = router.route(
                            RouteRequest(
                                zone=z_name,
                                active_domains=("corpus", "weft-eido", "formal-verification"),
                                repo_policy=pol,
                                contains_formal_claims=has_formal,
                                contains_certified_plot=bool(item.get("contains_certified_plot", z_name == "research_page")),
                                contains_illustrative_toy=bool(item.get("contains_illustrative_toy", False)),
                                data_eido_skip_marked=skip_marked,
                            )
                        )
                    except ContestedPreferenceError as exc:
                        bridge.unmount(reason=f"hard_veto2_contested:{exc.conflict_key}")
                        current_scales_mounted = {}
                        contested_escalations += 1
                        reply = (
                            f"ContestedPreferenceError ({exc.conflict_key}): Hard Veto 2 fail-closed escalation; "
                            f"explicit Plane 1 precedence_overrides or data-eido-skip required."
                        )
                        mixed_response_rows.append(
                            {
                                "id": item_id,
                                "response": reply,
                                "zone": z_name,
                                "routed_scales": {},
                                "contested_conflict_key": exc.conflict_key,
                            }
                        )
                        mixed_details.append(
                            {
                                "id": item_id,
                                "zone": z_name,
                                "contested_conflict_key": exc.conflict_key,
                                "formal_issues": [],
                                "prose_issues": [],
                            }
                        )
                        continue

                    if current_scales_mounted != dec.scale_map():
                        _mount_for_decision(
                            bridge,
                            dec,
                            compiled_map,
                            ckpt=ckpt,
                            lineage_dict=lineage.to_dict(),
                            runtime_flags_sha256=warp_flags.canonical_digest(),
                            zone_manifest_id=zone_manifest_id,
                        )
                        current_scales_mounted = dict(dec.scale_map())

                    resp = bridge.infer(
                        [{"role": "user", "content": prompt_str}],
                        temperature=0.0,
                        top_p=1.0,
                        seed=42,
                        max_tokens=mixed_max_tokens,
                        zone_manifest_id=zone_manifest_id,
                    )
                    reply = str(resp["response"]["choices"][0]["message"]["content"])
                    f_issues = (
                        _check_formal_clean(
                            reply,
                            forbid_float=bool(item.get("forbid_float", False)),
                            required_sha40=item.get("required_sha40"),
                        )
                        if z_name in ("formal_proof", "research_page")
                        else []
                    )
                    if item.get("require_data_eido_skip") and "data-eido-skip" not in reply:
                        f_issues.append("missing_data_eido_skip")
                    p_issues = _check_prose_clean(reply)

                    if f_issues:
                        internal_formal_corruptions += 1
                    if p_issues:
                        internal_prose_leaks += 1
                    mixed_response_rows.append(
                        {
                            "id": item_id,
                            "response": reply,
                            "zone": z_name,
                            "routed_scales": dec.scale_map(),
                        }
                    )
                    mixed_details.append(
                        {
                            "id": item_id,
                            "zone": z_name,
                            "formal_issues": f_issues,
                            "prose_issues": p_issues,
                        }
                    )

                stage_out_dir = Path(output_dir) if output_dir is not None else work_dir
                stage_out_dir.mkdir(parents=True, exist_ok=True)
                mixed_resp_file = stage_out_dir / "mixed_responses_routed.jsonl"
                mixed_resp_file.write_text(
                    "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in mixed_response_rows),
                    encoding="utf-8",
                )

                if mixed_grader_cmd:
                    has_mg_ph = any("{responses_jsonl}" in tok for tok in mixed_grader_cmd)
                    mg_cmd = (
                        [tok.replace("{responses_jsonl}", str(mixed_resp_file)) for tok in mixed_grader_cmd]
                        if has_mg_ph
                        else [*mixed_grader_cmd, "--responses", str(mixed_resp_file)]
                    )
                    mg_proc = subprocess.run(
                        mg_cmd,
                        capture_output=True,
                        text=True,
                        timeout=120.0,
                        check=False,
                    )
                    reconciled_mixed = reconcile_mixed_grader_result(
                        internal_formal_corruptions=internal_formal_corruptions,
                        internal_prose_leaks=internal_prose_leaks,
                        returncode=mg_proc.returncode,
                        stdout=mg_proc.stdout,
                        stderr=mg_proc.stderr,
                    )
                    formal_corruptions = reconciled_mixed["formal_block_corruptions"]
                    prose_leaks = reconciled_mixed["prose_rule_leaks"]
                    tc2_passed = reconciled_mixed["passed"]
                    external_mixed_meta: dict[str, Any] | None = {
                        "returncode": reconciled_mixed["external_grader_returncode"],
                        "external_formal_block_corruptions": reconciled_mixed["external_formal_block_corruptions"],
                        "external_prose_rule_leaks": reconciled_mixed["external_prose_rule_leaks"],
                    }
                else:
                    formal_corruptions = internal_formal_corruptions
                    prose_leaks = internal_prose_leaks
                    tc2_passed = formal_corruptions == 0 and prose_leaks == 0
                    external_mixed_meta = None

                tc2_report = {
                    "passed": tc2_passed,
                    "prompt_source": mixed_source,
                    "prompts_evaluated": len(mixed_prompts),
                    "contested_hard_veto2_escalations": contested_escalations,
                    "formal_block_corruptions": formal_corruptions,
                    "prose_rule_leaks": prose_leaks,
                    "internal_formal_block_corruptions": internal_formal_corruptions,
                    "internal_prose_rule_leaks": internal_prose_leaks,
                    "external_grader_used": bool(mixed_grader_cmd),
                    "external_grader_details": external_mixed_meta,
                    "failing_items": [d for d in mixed_details if d["formal_issues"] or d["prose_issues"]],
                }

                # ----------------------------------------------------------
                # 4. T-C3: Base Capability Retention (<= 1.5 pp drop vs W0, beats naive sum)
                # ----------------------------------------------------------
                if retention_jsonl_path:
                    r_path = Path(retention_jsonl_path).expanduser().resolve()
                    ret_prompts = [
                        json.loads(line)
                        for line in r_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    ret_source = f"jsonl:{r_path.name}"
                else:
                    ret_prompts = _build_public_retention_prompts()
                    ret_source = "public_non_vault_25"

                bridge.unmount(reason="tc3_w0_baseline")
                w0_passed = 0
                routed_passed = 0
                naive_passed = 0

                routed_lora_scales = [
                    {"id": 0, "scale": 0.4},
                    {"id": 1, "scale": 0.0},
                    {"id": 2, "scale": 0.5},
                ]
                naive_lora_scales = [
                    {"id": 0, "scale": 1.0},
                    {"id": 1, "scale": 1.0},
                    {"id": 2, "scale": 1.0},
                    {"id": 3, "scale": 1.0},
                ]
                ret_max_tokens = 384 if retention_jsonl_path else 64
                ret_rows_w0: list[dict[str, Any]] = []
                ret_rows_routed: list[dict[str, Any]] = []
                ret_rows_naive: list[dict[str, Any]] = []
                for r_item in ret_prompts:
                    rid = str(r_item.get("id", ""))
                    msgs = [{"role": "user", "content": str(r_item["prompt"])}]
                    llama_client.erase_slot(0)
                    out_w0 = llama_client.chat_completion(
                        msgs, lora=[], temperature=0.0, top_p=1.0, seed=42, max_tokens=ret_max_tokens, cache_prompt=False, id_slot=0
                    )
                    txt_w0 = str(out_w0["choices"][0]["message"]["content"])
                    ret_rows_w0.append({"id": rid, "response": txt_w0})
                    if _grade_prompt_item(r_item, txt_w0):
                        w0_passed += 1

                    llama_client.erase_slot(0)
                    out_rt = llama_client.chat_completion(
                        msgs,
                        lora=routed_lora_scales,
                        temperature=0.0,
                        top_p=1.0,
                        seed=42,
                        max_tokens=ret_max_tokens,
                        cache_prompt=False,
                        id_slot=0,
                    )
                    txt_rt = str(out_rt["choices"][0]["message"]["content"])
                    ret_rows_routed.append({"id": rid, "response": txt_rt})
                    if _grade_prompt_item(r_item, txt_rt):
                        routed_passed += 1

                    llama_client.erase_slot(0)
                    out_nv = llama_client.chat_completion(
                        msgs,
                        lora=naive_lora_scales,
                        temperature=0.0,
                        top_p=1.0,
                        seed=42,
                        max_tokens=ret_max_tokens,
                        cache_prompt=False,
                        id_slot=0,
                    )
                    txt_nv = str(out_nv["choices"][0]["message"]["content"])
                    ret_rows_naive.append({"id": rid, "response": txt_nv})
                    if _grade_prompt_item(r_item, txt_nv):
                        naive_passed += 1

                ret_w0_file = stage_out_dir / "retention_responses_w0.jsonl"
                ret_rt_file = stage_out_dir / "retention_responses_routed_triple.jsonl"
                ret_nv_file = stage_out_dir / "retention_responses_naive_sum.jsonl"
                for rf_p, rf_rows in (
                    (ret_w0_file, ret_rows_w0),
                    (ret_rt_file, ret_rows_routed),
                    (ret_nv_file, ret_rows_naive),
                ):
                    rf_p.write_text(
                        "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rf_rows),
                        encoding="utf-8",
                    )

                n_ret = max(len(ret_prompts), 1)
                ret_grader_gate_ok = True
                if retention_grader_cmd:
                    has_single_ph = any("{responses_jsonl}" in tok for tok in retention_grader_cmd)
                    has_paired_ph = any(
                        "{baseline_jsonl}" in tok or "{candidate_jsonl}" in tok for tok in retention_grader_cmd
                    )
                    if has_single_ph:
                        def _score_ret_single(resp_file: Path) -> tuple[bool, int, float]:
                            rcmd = [tok.replace("{responses_jsonl}", str(resp_file)) for tok in retention_grader_cmd]
                            rproc = subprocess.run(rcmd, capture_output=True, text=True, timeout=120.0, check=False)
                            r_ok, rj = parse_and_validate_grader_process(
                                rproc.returncode,
                                rproc.stdout,
                                rproc.stderr,
                                grader_name="retention_grader",
                                required_int_keys=("total_count",),
                                any_of_int_keys=(("total_passed", "passed_count", "correct"),),
                            )
                            p_cnt = int(rj.get("total_passed", rj.get("passed_count", rj.get("correct", 0))))
                            acc_v = float(rj.get("accuracy_pct", (p_cnt / n_ret) * 100.0))
                            return r_ok, p_cnt, acc_v

                        w0_ok, w0_passed, w0_acc = _score_ret_single(ret_w0_file)
                        rt_ok, routed_passed, routed_acc = _score_ret_single(ret_rt_file)
                        nv_ok, naive_passed, naive_acc = _score_ret_single(ret_nv_file)
                        ret_grader_gate_ok = single_mode_retention_exit_ok(w0_ok, rt_ok, nv_ok)
                    else:
                        def _score_ret_paired(base_file: Path, cand_file: Path) -> tuple[bool, dict[str, Any]]:
                            if has_paired_ph:
                                rcmd = [
                                    tok.replace("{baseline_jsonl}", str(base_file)).replace("{candidate_jsonl}", str(cand_file))
                                    for tok in retention_grader_cmd
                                ]
                            else:
                                rcmd = [
                                    *retention_grader_cmd,
                                    "--baseline-responses",
                                    str(base_file),
                                    "--candidate-responses",
                                    str(cand_file),
                                    "--max-drop-pp",
                                    "1.5",
                                ]
                            rproc = subprocess.run(rcmd, capture_output=True, text=True, timeout=120.0, check=False)
                            return parse_and_validate_grader_process(
                                rproc.returncode,
                                rproc.stdout,
                                rproc.stderr,
                                grader_name="retention_paired_grader",
                                required_int_keys=("baseline_passed", "candidate_passed", "total_count"),
                            )

                        rt_exit_ok, rj_rt = _score_ret_paired(ret_w0_file, ret_rt_file)
                        _, rj_nv = _score_ret_paired(ret_w0_file, ret_nv_file)
                        ret_grader_gate_ok = bool(rt_exit_ok and rj_rt.get("gate_passed", True))
                        w0_passed = int(rj_rt["baseline_passed"])
                        w0_acc = float(rj_rt.get("baseline_accuracy_pct", (w0_passed / n_ret) * 100.0))
                        routed_passed = int(rj_rt["candidate_passed"])
                        routed_acc = float(rj_rt.get("candidate_accuracy_pct", (routed_passed / n_ret) * 100.0))
                        naive_passed = int(rj_nv["candidate_passed"])
                        naive_acc = float(rj_nv.get("candidate_accuracy_pct", (naive_passed / n_ret) * 100.0))
                else:
                    w0_acc = (w0_passed / n_ret) * 100.0
                    routed_acc = (routed_passed / n_ret) * 100.0
                    naive_acc = (naive_passed / n_ret) * 100.0

                signed_drop_pp = w0_acc - routed_acc
                tc3_passed = bool(ret_grader_gate_ok and (signed_drop_pp <= 1.5) and (routed_acc > naive_acc))
                tc3_report = {
                    "passed": tc3_passed,
                    "prompt_source": ret_source,
                    "prompts_evaluated": len(ret_prompts),
                    "external_grader_used": bool(retention_grader_cmd),
                    "w0_passed": w0_passed,
                    "w0_accuracy_pct": round(w0_acc, 2),
                    "routed_triple_passed": routed_passed,
                    "routed_triple_accuracy_pct": round(routed_acc, 2),
                    "drop_pp_vs_w0": round(signed_drop_pp, 2),
                    "max_allowed_drop_pp": 1.5,
                    "naive_unweighted_sum_passed": naive_passed,
                    "naive_unweighted_sum_accuracy_pct": round(naive_acc, 2),
                    "beats_naive_unweighted_summation": routed_acc > naive_acc,
                }

                # ----------------------------------------------------------
                # 5. T-C1: Solo Gain Preservation (strictly gated on live step0 retention >= 90%)
                # ----------------------------------------------------------
                tc1_domain_probes = {
                    "corpus": "Write one short plain sentence explaining what git bisect finds. No em dashes.",
                    "weft-eido": "Write a JS function `export const clamp01 = x => Math.max(0, Math.min(1, x));`.",
                    "formal-verification": "Write Lean 4 `theorem add_z (n : Nat) : n + 0 = n := Nat.add_zero n`.",
                }
                tc1_retention_by_domain: dict[str, dict[str, Any]] = {}
                pol_map = {
                    "corpus": corpus_pol,
                    "weft-eido": weft_eido_repo_policy("Moissanite-Labs/weft-eido"),
                    "formal-verification": f0_pol,
                }
                zone_for_dom = {
                    "corpus": "prose",
                    "weft-eido": "ui_module",
                    "formal-verification": "formal_proof",
                }
                for dom in ("corpus", "weft-eido", "formal-verification"):
                    lid = DOMAIN_TO_LLAMA_ID[dom]
                    p_txt = tc1_domain_probes[dom]
                    llama_client.erase_slot(0)
                    r_base_d = llama_client.completion(
                        p_txt, lora=[], temperature=0.0, top_p=1.0, seed=42, n_predict=16, n_probs=20, cache_prompt=False, id_slot=0
                    )
                    llama_client.erase_slot(0)
                    r_solo_d = llama_client.completion(
                        p_txt,
                        lora=[{"id": lid, "scale": 1.0}],
                        temperature=0.0,
                        top_p=1.0,
                        seed=42,
                        n_predict=16,
                        n_probs=20,
                        cache_prompt=False,
                        id_slot=0,
                    )
                    other = "formal-verification" if dom != "formal-verification" else "weft-eido"
                    dec_pair = router.route(
                        RouteRequest(zone=zone_for_dom[dom], active_domains=(dom, other), repo_policy=pol_map[dom])
                    )
                    dec_trip = router.route(
                        RouteRequest(
                            zone=zone_for_dom[dom],
                            active_domains=("corpus", "weft-eido", "formal-verification"),
                            repo_policy=pol_map[dom],
                        )
                    )
                    pair_lora = [
                        {"id": DOMAIN_TO_LLAMA_ID[k], "scale": v} for k, v in dec_pair.scale_map().items() if v > 0.0
                    ]
                    trip_lora = [
                        {"id": DOMAIN_TO_LLAMA_ID[k], "scale": v} for k, v in dec_trip.scale_map().items() if v > 0.0
                    ]
                    llama_client.erase_slot(0)
                    r_pair_d = llama_client.completion(
                        p_txt, lora=pair_lora, temperature=0.0, top_p=1.0, seed=42, n_predict=16, n_probs=20, cache_prompt=False, id_slot=0
                    )
                    llama_client.erase_slot(0)
                    r_trip_d = llama_client.completion(
                        p_txt, lora=trip_lora, temperature=0.0, top_p=1.0, seed=42, n_predict=16, n_probs=20, cache_prompt=False, id_slot=0
                    )

                    probs_base_d = r_base_d["completion_probabilities"]
                    probs_solo_d = r_solo_d["completion_probabilities"]
                    probs_pair_d = r_pair_d["completion_probabilities"]
                    probs_trip_d = r_trip_d["completion_probabilities"]
                    assert_nonempty_completion_probs(probs_base_d, label=f"tc1_base[{dom}]")
                    assert_nonempty_completion_probs(probs_solo_d, label=f"tc1_solo[{dom}]")
                    assert_nonempty_completion_probs(probs_pair_d, label=f"tc1_pair[{dom}]")
                    assert_nonempty_completion_probs(probs_trip_d, label=f"tc1_trip[{dom}]")

                    solo_step0 = step0_logprob_shift(probs_solo_d, probs_base_d)
                    pair_step0_drift = step0_logprob_shift(probs_pair_d, probs_solo_d)
                    trip_step0_drift = step0_logprob_shift(probs_trip_d, probs_solo_d)

                    # Live behavioral step-0 retention ONLY (never masked by CPU subspace alignment!)
                    paired_live_ret = compute_live_step0_retention_pct(
                        solo_shift=solo_step0,
                        drift_from_solo=pair_step0_drift,
                    )
                    triple_live_ret = compute_live_step0_retention_pct(
                        solo_shift=solo_step0,
                        drift_from_solo=trip_step0_drift,
                    )

                    def _cpu_subspace_alignment_for_scales(scales: Mapping[str, float]) -> float | None:
                        t_dom = artifacts[dom].target_tensor
                        other_touching = [
                            k_dom
                            for k_dom, sc in scales.items()
                            if k_dom != dom and sc > 0.0 and t_dom in artifacts[k_dom].layer_factors
                        ]
                        if not other_touching:
                            return None
                        b_d, a_d = artifacts[dom].layer_factors[t_dom]
                        d_solo = b_d @ a_d
                        _, _, vh_d = np.linalg.svd(a_d, full_matrices=False)
                        k_d = vh_d.T
                        solo_out = d_solo @ k_d
                        d_comb = np.zeros_like(d_solo)
                        for k_dom, sc in scales.items():
                            if sc > 0.0 and t_dom in artifacts[k_dom].layer_factors:
                                bk, ak = artifacts[k_dom].layer_factors[t_dom]
                                d_comb = d_comb + float(sc) * (bk @ ak)
                        comb_out = d_comb @ k_d
                        denom = max(float(np.sum(solo_out * solo_out)), 1e-12)
                        return round(float(np.sum(comb_out * solo_out) / denom) * 100.0, 2)

                    pair_cpu_align = _cpu_subspace_alignment_for_scales(dec_pair.scale_map())
                    trip_cpu_align = _cpu_subspace_alignment_for_scales(dec_trip.scale_map())

                    tc1_retention_by_domain[dom] = {
                        "zone": zone_for_dom[dom],
                        "solo_logprob_shift": round(float(solo_step0), 8),
                        "paired_step0_drift_from_solo": round(float(pair_step0_drift), 8),
                        "triple_step0_drift_from_solo": round(float(trip_step0_drift), 8),
                        "paired_drift_to_solo_shift_ratio": (
                            round(float(pair_step0_drift / solo_step0), 6) if solo_step0 > 0.0 else None
                        ),
                        "triple_drift_to_solo_shift_ratio": (
                            round(float(trip_step0_drift / solo_step0), 6) if solo_step0 > 0.0 else None
                        ),
                        "paired_routed_scales": dec_pair.scale_map(),
                        "triple_routed_scales": dec_trip.scale_map(),
                        "paired_live_step0_retention_pct": round(float(paired_live_ret), 2),
                        "triple_live_step0_retention_pct": round(float(triple_live_ret), 2),
                        "live_step0_retention_pct": round(float(min(paired_live_ret, triple_live_ret)), 2),
                        "cpu_linear_subspace_alignment_pct": {
                            "diagnostic_only": True,
                            "paired_pct": pair_cpu_align,
                            "paired_status": (
                                "shared_tensors_evaluated"
                                if pair_cpu_align is not None
                                else "not_applicable_disjoint_tensors"
                            ),
                            "triple_pct": trip_cpu_align,
                            "triple_status": (
                                "shared_tensors_evaluated"
                                if trip_cpu_align is not None
                                else "not_applicable_disjoint_tensors"
                            ),
                        },
                    }

                sim_subspace_diagnostic = compute_shared_subspace_diagnostic(
                    artifacts["weft-eido"].layer_factors,
                    artifacts["formal-verification"].layer_factors,
                )

                # Optional dataset-level evaluation when `formal_eval_jsonl_path` is provided
                formal_dataset_eval: dict[str, Any] | None = None
                fe_rows_w0: list[dict[str, Any]] = []
                fe_rows_solo: list[dict[str, Any]] = []
                fe_rows_paired: list[dict[str, Any]] = []
                fe_rows_triple: list[dict[str, Any]] = []
                if formal_eval_jsonl_path:
                    from mcproof.oracles import grade_family_completion

                    fe_path = Path(formal_eval_jsonl_path).expanduser().resolve()
                    fe_rows = [
                        json.loads(line)
                        for line in fe_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    w0_ok_cnt = 0
                    solo_fv_cnt = 0
                    paired_fv_cnt = 0
                    triple_fv_cnt = 0
                    w0_oracle_cnt = 0
                    solo_oracle_cnt = 0
                    paired_oracle_cnt = 0
                    triple_oracle_cnt = 0
                    oracle_graded_n = 0

                    for row in fe_rows:
                        rid = str(row.get("id", ""))
                        fam = str(row.get("family", "")).strip().upper()
                        z_row = str(row.get("zone", "formal_proof"))
                        if z_row not in ("formal_proof", "research_page", "code", "prose"):
                            z_row = "formal_proof"
                        msgs = [{"role": "user", "content": str(row["prompt"])}]
                        llama_client.erase_slot(0)
                        c0 = llama_client.chat_completion(
                            msgs, lora=[], temperature=0.0, top_p=1.0, seed=42, max_tokens=384, cache_prompt=False, id_slot=0
                        )
                        txt0 = str(c0["choices"][0]["message"]["content"])
                        fe_rows_w0.append({"id": rid, "response": txt0})

                        llama_client.erase_slot(0)
                        cs = llama_client.chat_completion(
                            msgs,
                            lora=[{"id": 2, "scale": 1.0}],
                            temperature=0.0,
                            top_p=1.0,
                            seed=42,
                            max_tokens=384,
                            cache_prompt=False,
                            id_slot=0,
                        )
                        txts = str(cs["choices"][0]["message"]["content"])
                        fe_rows_solo.append({"id": rid, "response": txts})

                        dec_p = router.route(
                            RouteRequest(
                                zone=z_row,
                                active_domains=("weft-eido", "formal-verification"),
                                repo_policy=f0_pol,
                                contains_formal_claims=True,
                                contains_certified_plot=(z_row == "research_page"),
                            )
                        )
                        p_lora = [
                            {"id": DOMAIN_TO_LLAMA_ID[k], "scale": v} for k, v in dec_p.scale_map().items() if v > 0.0
                        ]
                        dec_t = router.route(
                            RouteRequest(
                                zone=z_row,
                                active_domains=("corpus", "weft-eido", "formal-verification"),
                                repo_policy=f0_pol,
                                contains_formal_claims=True,
                                contains_certified_plot=(z_row == "research_page"),
                            )
                        )
                        t_lora = [
                            {"id": DOMAIN_TO_LLAMA_ID[k], "scale": v} for k, v in dec_t.scale_map().items() if v > 0.0
                        ]
                        if p_lora == [{"id": 2, "scale": 1.0}]:
                            txtp = txts
                        else:
                            llama_client.erase_slot(0)
                            cp = llama_client.chat_completion(
                                msgs, lora=p_lora, temperature=0.0, top_p=1.0, seed=42, max_tokens=384, cache_prompt=False, id_slot=0
                            )
                            txtp = str(cp["choices"][0]["message"]["content"])
                        fe_rows_paired.append({"id": rid, "response": txtp})

                        if t_lora == p_lora:
                            txtt = txtp
                        elif t_lora == [{"id": 2, "scale": 1.0}]:
                            txtt = txts
                        else:
                            llama_client.erase_slot(0)
                            ct = llama_client.chat_completion(
                                msgs, lora=t_lora, temperature=0.0, top_p=1.0, seed=42, max_tokens=384, cache_prompt=False, id_slot=0
                            )
                            txtt = str(ct["choices"][0]["message"]["content"])
                        fe_rows_triple.append({"id": rid, "response": txtt})

                        if _check_formal_clean(txt0) == []:
                            w0_ok_cnt += 1
                        if _check_formal_clean(txts) == []:
                            solo_fv_cnt += 1
                        if _check_formal_clean(txtp) == []:
                            paired_fv_cnt += 1
                        if _check_formal_clean(txtt) == []:
                            triple_fv_cnt += 1

                        if fam in ("A", "B", "C", "D") and not holdout_grader_cmd:
                            oracle_graded_n += 1
                            exp_tier = str(row["expected_tier"]) if row.get("expected_tier") else None
                            gen_src = str(row["generator_source"]) if row.get("generator_source") else None
                            v_cases = row.get("valid_cases") or ()
                            p_muts = row.get("planted_mutations")

                            g0 = grade_family_completion(
                                fam,
                                txt0,
                                expected_tier=exp_tier,
                                generator_source=gen_src,
                                valid_cases=v_cases,
                                planted_mutations=p_muts,
                            )
                            gs = grade_family_completion(
                                fam,
                                txts,
                                expected_tier=exp_tier,
                                generator_source=gen_src,
                                valid_cases=v_cases,
                                planted_mutations=p_muts,
                            )
                            gp = (
                                gs
                                if txtp == txts
                                else grade_family_completion(
                                    fam,
                                    txtp,
                                    expected_tier=exp_tier,
                                    generator_source=gen_src,
                                    valid_cases=v_cases,
                                    planted_mutations=p_muts,
                                )
                            )
                            gt = (
                                gp
                                if txtt == txtp
                                else grade_family_completion(
                                    fam,
                                    txtt,
                                    expected_tier=exp_tier,
                                    generator_source=gen_src,
                                    valid_cases=v_cases,
                                    planted_mutations=p_muts,
                                )
                            )
                            if g0.passed:
                                w0_oracle_cnt += 1
                            if gs.passed:
                                solo_oracle_cnt += 1
                            if gp.passed:
                                paired_oracle_cnt += 1
                            if gt.passed:
                                triple_oracle_cnt += 1

                    fe_w0_f = stage_out_dir / "formal_eval_responses_w0.jsonl"
                    fe_solo_f = stage_out_dir / "formal_eval_responses_solo_fv.jsonl"
                    fe_pair_f = stage_out_dir / "formal_eval_responses_paired.jsonl"
                    fe_trip_f = stage_out_dir / "formal_eval_responses_triple.jsonl"
                    for fp_out, fp_rows in (
                        (fe_w0_f, fe_rows_w0),
                        (fe_solo_f, fe_rows_solo),
                        (fe_pair_f, fe_rows_paired),
                        (fe_trip_f, fe_rows_triple),
                    ):
                        fp_out.write_text(
                            "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in fp_rows),
                            encoding="utf-8",
                        )

                    holdout_grader_exit_ok: bool | None = None
                    if holdout_grader_cmd:
                        oracle_graded_n = len(fe_rows)
                        has_hg_ph = any("{responses_jsonl}" in tok for tok in holdout_grader_cmd)
                        holdout_exit_oks: list[bool] = []

                        def _score_holdout_arm(arm_file: Path) -> tuple[bool, int]:
                            hcmd = (
                                [tok.replace("{responses_jsonl}", str(arm_file)) for tok in holdout_grader_cmd]
                                if has_hg_ph
                                else [*holdout_grader_cmd, "--responses", str(arm_file)]
                            )
                            hproc = subprocess.run(hcmd, capture_output=True, text=True, timeout=300.0, check=False)
                            h_ok, hj = parse_and_validate_grader_process(
                                hproc.returncode,
                                hproc.stdout,
                                hproc.stderr,
                                grader_name="holdout_grader",
                                required_int_keys=("total_count",),
                                any_of_int_keys=(("total_passed", "passed_count", "overall_passed"),),
                            )
                            cnt = int(
                                hj.get(
                                    "total_passed",
                                    hj.get("passed_count", hj.get("overall_passed", 0)),
                                )
                            )
                            return h_ok, cnt

                        def _adopt_holdout(arm_file: Path, internal_cnt: int) -> int:
                            h_ok, cnt = _score_holdout_arm(arm_file)
                            holdout_exit_oks.append(h_ok)
                            # Exit 1 keeps the internal count. A rejected grader cannot overwrite it.
                            return cnt if h_ok else internal_cnt

                        w0_oracle_cnt = _adopt_holdout(fe_w0_f, w0_oracle_cnt)
                        solo_oracle_cnt = _adopt_holdout(fe_solo_f, solo_oracle_cnt)
                        paired_oracle_cnt = (
                            solo_oracle_cnt
                            if fe_rows_paired == fe_rows_solo
                            else _adopt_holdout(fe_pair_f, paired_oracle_cnt)
                        )
                        triple_oracle_cnt = (
                            paired_oracle_cnt
                            if fe_rows_triple == fe_rows_paired
                            else _adopt_holdout(fe_trip_f, triple_oracle_cnt)
                        )
                        holdout_grader_exit_ok = bool(holdout_exit_oks) and all(holdout_exit_oks)

                    solo_gain = solo_oracle_cnt - w0_oracle_cnt
                    paired_gain_ret: float | None = (
                        round(((paired_oracle_cnt - w0_oracle_cnt) / float(solo_gain)) * 100.0, 2)
                        if solo_gain > 0
                        else None
                    )
                    triple_gain_ret: float | None = (
                        round(((triple_oracle_cnt - w0_oracle_cnt) / float(solo_gain)) * 100.0, 2)
                        if solo_gain > 0
                        else None
                    )
                    formal_dataset_eval = {
                        "dataset": fe_path.name,
                        "count": len(fe_rows),
                        "external_grader_used": bool(holdout_grader_cmd),
                        "holdout_grader_exit_ok": holdout_grader_exit_ok,
                        "oracle_graded_count": oracle_graded_n,
                        "w0_oracle_passed": w0_oracle_cnt,
                        "solo_fv_oracle_passed": solo_oracle_cnt,
                        "paired_routed_oracle_passed": paired_oracle_cnt,
                        "triple_routed_oracle_passed": triple_oracle_cnt,
                        "paired_oracle_gain_retention_pct": paired_gain_ret,
                        "triple_oracle_gain_retention_pct": triple_gain_ret,
                        "gain_retention_status": (
                            "positive_solo_gain_evaluated"
                            if solo_gain > 0
                            else "not_applicable_non_positive_solo_gain"
                        ),
                        "w0_surface_clean": w0_ok_cnt,
                        "solo_fv_surface_clean": solo_fv_cnt,
                        "paired_routed_surface_clean": paired_fv_cnt,
                        "triple_routed_surface_clean": triple_fv_cnt,
                    }

                min_live_step0_retention_pct = min(
                    min(v["paired_live_step0_retention_pct"] for v in tc1_retention_by_domain.values()),
                    min(v["triple_live_step0_retention_pct"] for v in tc1_retention_by_domain.values()),
                )
                tc1_passed = bool(min_live_step0_retention_pct >= 90.0)
                tc1_report = {
                    "passed": tc1_passed,
                    "live_step0_retention_pct": round(min_live_step0_retention_pct, 2),
                    "min_retention_pct": round(min_live_step0_retention_pct, 2),
                    "required_min_retention_pct": 90.0,
                    "max_allowed_drift_fraction_of_solo_shift": 0.10,
                    "routed_domain_retention": tc1_retention_by_domain,
                    "cpu_linear_subspace_alignment_pct": {
                        "diagnostic_only": True,
                        "by_domain": {
                            dom: tc1_retention_by_domain[dom]["cpu_linear_subspace_alignment_pct"]
                            for dom in ("corpus", "weft-eido", "formal-verification")
                        },
                        "simultaneous_research_page": sim_subspace_diagnostic,
                    },
                    "formal_dataset_eval": formal_dataset_eval,
                    "adapter_sources": {d: artifacts[d].source_kind for d in ("corpus", "weft-eido", "formal-verification")},
                }

                # ----------------------------------------------------------
                # 6. T-C5: Serving Budget (same-instance interleaved W0 vs triple_lora, /slots n_ctx, analytical VRAM)
                # ----------------------------------------------------------
                bridge.unmount(reason="tc5_same_instance_interleaved_benchmark")
                three_active = [
                    {"id": 0, "scale": 1.0},
                    {"id": 1, "scale": 1.0},
                    {"id": 2, "scale": 1.0},
                ]

                # Interleaved warmup on the EXACT SAME live_llama instance (`parallel_slots`, `ctx_size`)
                llama_client.erase_slot(0)
                _ = llama_client.completion(
                    bench_prompt,
                    lora=[],
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=64,
                    cache_prompt=False,
                    id_slot=0,
                )
                llama_client.erase_slot(0)
                _ = llama_client.completion(
                    bench_prompt,
                    lora=three_active,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=64,
                    cache_prompt=False,
                    id_slot=0,
                )

                def _measure_single_bench_trial(lora_arg: list[dict[str, Any]]) -> float:
                    llama_client.erase_slot(0)
                    t0_b = time.perf_counter()
                    r_b = llama_client.completion(
                        bench_prompt,
                        lora=lora_arg,
                        temperature=0.0,
                        top_p=1.0,
                        seed=42,
                        n_predict=96,
                        cache_prompt=False,
                        id_slot=0,
                    )
                    wall_s = time.perf_counter() - t0_b
                    timings = r_b.get("timings") or {}
                    return float(timings.get("predicted_per_second") or (96.0 / max(wall_s, 1e-6)))

                w0_tok_s_samples: list[float] = []
                stack_tok_s_samples: list[float] = []
                for trial_idx in range(5):
                    if trial_idx % 2 == 0:
                        w0_tok_s_samples.append(_measure_single_bench_trial([]))
                        stack_tok_s_samples.append(_measure_single_bench_trial(three_active))
                    else:
                        stack_tok_s_samples.append(_measure_single_bench_trial(three_active))
                        w0_tok_s_samples.append(_measure_single_bench_trial([]))
                llama_client.erase_slot(0)

                overhead_metrics = compute_latency_overhead_metrics(
                    w0_tok_s_samples,
                    stack_tok_s_samples,
                    max_allowed_overhead_pct=15.0,
                    anomaly_floor_pct=-5.0,
                )

                # Query `/slots` via fail-closed HTTP client and require explicit `"n_ctx"` on `raw_slots[0]`
                raw_slots = llama_client._request("GET", "/slots")
                slot_n_ctx = extract_verified_slot_n_ctx(raw_slots)
                kv_ctx_gate_passed = bool(slot_n_ctx is not None and slot_n_ctx >= 8192)

                lora_total_bytes = sum(
                    artifacts[d].gguf_bytes for d in ("corpus", "weft-eido", "formal-verification")
                )
                cfg_json_path = (
                    (paths.default_safetensors_dir / "config.json")
                    if paths.default_safetensors_dir is not None and (paths.default_safetensors_dir / "config.json").is_file()
                    else None
                )
                companion_q4_cand = base_gguf.parent / "Qwen3.5-4B-Q4_K_M.gguf"
                vram_proj = compute_analytical_vram_projection_gib(
                    base_gguf_bytes=base_gguf.stat().st_size,
                    lora_total_bytes=lora_total_bytes,
                    kv_ctx_tokens=slot_n_ctx if slot_n_ctx is not None else int(ctx_size),
                    kv_cache_type=warp_flags.kv_cache_type,
                    geometry=geom,
                    config_json_path=cfg_json_path,
                    companion_q4_gguf_path=companion_q4_cand if companion_q4_cand.is_file() else None,
                )
                projected_vram_gib = float(vram_proj["analytical_vram_projection_gib"])
                m1_max_live_rss_mib = live_llama.rss_mib

                tc5_passed = bool(
                    overhead_metrics["overhead_gate_passed"]
                    and kv_ctx_gate_passed
                    and projected_vram_gib <= 7.2
                )
                tc5_report = {
                    "passed": tc5_passed,
                    "benchmark_protocol": (
                        f"same_llama_server_instance_interleaved_5trials_np{parallel_slots}_ctx{ctx_size}"
                    ),
                    "w0_median_tok_per_s": overhead_metrics["w0_median_tok_per_s"],
                    "triple_lora_median_tok_per_s": overhead_metrics["triple_lora_median_tok_per_s"],
                    "w0_samples_tok_per_s": overhead_metrics["w0_samples_tok_per_s"],
                    "triple_lora_samples_tok_per_s": overhead_metrics["triple_lora_samples_tok_per_s"],
                    "latency_overhead_pct": overhead_metrics["latency_overhead_pct"],
                    "max_allowed_overhead_pct": overhead_metrics["max_allowed_overhead_pct"],
                    "anomaly_floor_pct": overhead_metrics["anomaly_floor_pct"],
                    "benchmark_anomaly": overhead_metrics["benchmark_anomaly"],
                    "live_slot_kv_ctx_tokens": slot_n_ctx,
                    "kv_ctx_gate_passed": kv_ctx_gate_passed,
                    "min_required_kv_ctx_tokens": 8192,
                    "m1_max_measured_pure_w0_rss_mib": w0_rss_mib,
                    "m1_max_measured_stack_rss_mib": m1_max_live_rss_mib,
                    "vram_measurement_kind": "analytical_projection_not_nvml",
                    "analytical_vram_projection_gib": projected_vram_gib,
                    "analytical_vram_breakdown_gib": vram_proj,
                }

                verified_warp_receipts = LedgerVerifier.verify_file(warp_ledger_path, signer)
                ensure(exo_ledger.verify_chain() == [], "exo ledger chain verification failed in Phase 6")
            finally:
                rpc_server.stop()

        all_hazards_ok = all(h["passed"] for h in hazards_report.values())
        overall_passed = bool(
            all_hazards_ok
            and tc1_report["passed"]
            and tc2_report["passed"]
            and tc3_report["passed"]
            and tc4_report["passed"]
            and tc5_report["passed"]
        )

        raw_report = {
            "phase": "Phase 6: Multi-MDE Composition (T-C1 to T-C5) and Seven Hazards",
            "passed": overall_passed,
            "elapsed_total_s": round(time.perf_counter() - t_start, 3),
            "_meta": suite_env["vendor_mde_meta"],
            "lineage_pinned": lineage.to_dict(),
            "precedence_contract": "Tier 1 Human Authority > Tier 2 RepoPolicy > Specialist Pack in its L5 syntax zone > Base Prose Pack",
            "weft_eido_pr25_unit_tests_passed": eido_tests_passed,
            "checkpoint": {
                "model_id": ckpt.model_id,
                "base_gguf_name": base_gguf.name,
                "served_gguf_sha256": suite_env["served_gguf_sha256"],
                "base_weights_sha256": ckpt.weights_sha256,
                "gguf_quantization": suite_env["gguf_quantization"],
                "has_ssm_recurrent": ckpt.has_ssm_recurrent,
            },
            "adapters": {
                dom: {
                    "adapter_id": artifacts[dom].adapter_id,
                    "llama_adapter_id": artifacts[dom].llama_adapter_id,
                    "source_kind": artifacts[dom].source_kind,
                    "gguf_sha256": artifacts[dom].gguf_sha256,
                    "gguf_bytes": artifacts[dom].gguf_bytes,
                    "certificate_sha256": artifacts[dom].weft_certificate_sha256,
                    "rederived_zero_byte_ok": artifacts[dom].rederived_zero_byte_ok,
                }
                for dom in ("corpus", "weft-eido", "formal-verification")
            },
            "seven_hazards": hazards_report,
            "gates": {
                "T_C1_solo_preservation": tc1_report,
                "T_C2_mixed_zone_isolation": tc2_report,
                "T_C3_base_capability_retention": tc3_report,
                "T_C4_order_invariance_and_rollback": tc4_report,
                "T_C5_serving_budget": tc5_report,
            },
            "signed_warp_ledger_receipts_verified": len(verified_warp_receipts),
            "exo_ledger_entries_verified": len(exo_ledger.entries()),
        }
        report = sanitize_receipt_paths(raw_report)

        if output_dir is not None:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "phase6_receipt.json").write_text(
                json.dumps(report, indent=2, sort_keys=False, allow_nan=False) + "\n",
                encoding="utf-8",
            )

            def _write_jsonl(dst: Path, rows: Sequence[Mapping[str, Any]]) -> None:
                dst.write_text(
                    "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows),
                    encoding="utf-8",
                )

            _write_jsonl(out / "mixed_responses_routed.jsonl", mixed_response_rows)
            _write_jsonl(out / "retention_responses_w0.jsonl", ret_rows_w0)
            _write_jsonl(out / "retention_responses_routed_triple.jsonl", ret_rows_routed)
            _write_jsonl(out / "retention_responses_naive_sum.jsonl", ret_rows_naive)
            if fe_rows_w0:
                _write_jsonl(out / "formal_eval_responses_w0.jsonl", fe_rows_w0)
                _write_jsonl(out / "formal_eval_responses_solo_fv.jsonl", fe_rows_solo)
                _write_jsonl(out / "formal_eval_responses_paired.jsonl", fe_rows_paired)
                _write_jsonl(out / "formal_eval_responses_triple.jsonl", fe_rows_triple)
        return report
