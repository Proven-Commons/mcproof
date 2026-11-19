#!/usr/bin/env python3
"""Assemble canonical machine-readable `VERIFICATION_RECEIPT.json` and audit zero vault leakage."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

VERIF_DIR = Path(__file__).resolve().parent
REPO_ROOT = VERIF_DIR.parent
VAULT_ROOT = Path(os.environ.get("MCPROOF_VAULT_DIR") or (REPO_ROOT.parents[1] / "mcproof-vault"))
COMPILE_ART = REPO_ROOT / "compile" / "artifacts"
STACK_FINAL = REPO_ROOT / "stack" / "results" / "final"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_vault_prompts() -> list[str]:
    prompts: list[str] = []
    for fn in (
        "private_holdout.jsonl",
        "general_retention_100.jsonl",
        "mixed_composition_30.jsonl",
        "canaries_16.jsonl",
    ):
        for ln in (VAULT_ROOT / fn).read_text(encoding="utf-8").splitlines():
            if ln.strip():
                prompts.append(str(json.loads(ln).get("prompt", "")).strip())
    return prompts


def assert_zero_vault_leak_in_dir(verif_dir: Path, vault_prompts: list[str]) -> int:
    checked = 0
    for p in sorted(verif_dir.rglob("*")):
        if not p.is_file() or p.suffix not in (".json", ".md", ".py", ".txt"):
            continue
        raw = p.read_text(encoding="utf-8")
        for pr in vault_prompts:
            probe = pr[:40]
            if len(probe) >= 24 and probe in raw:
                raise RuntimeError(f"SECURITY VIOLATION: vault prompt substring found in {p.name}")
        checked += 1
    return checked


def main() -> int:
    oracles = load_json(VERIF_DIR / "oracles_verification_receipt.json")
    datasets = load_json(VERIF_DIR / "datasets_vault_receipt.json")
    flake = load_json(VERIF_DIR / "canary_zero_flake_receipt.json")
    rederive = load_json(VERIF_DIR / "p2b_rederivation_receipt.json")
    compiler = load_json(VERIF_DIR / "compiler_verification_receipt.json")
    b0 = load_json(VERIF_DIR / "vault_arm_b0.json")
    b1 = load_json(VERIF_DIR / "vault_arm_b1.json")
    adapters = load_json(VERIF_DIR / "vault_arms_adapters.json")
    stack_sealed = load_json(VERIF_DIR / "stack_verification_receipt.json")
    stack_p4 = load_json(STACK_FINAL / "phase4_receipt.json")
    stack_p6 = load_json(STACK_FINAL / "phase6_receipt.json")
    comp_manifest = load_json(COMPILE_ART / "MANIFEST.json")

    p2b_arm = adapters["arms"]["P2-B"]
    p2a_arm = adapters["arms"]["P2-A"]
    lb_arm = adapters["arms"]["logit_bias"]
    sab_arm = adapters["arms"]["sabotage"]
    gh_arm = adapters["arms"]["goodhart"]
    p6_routed = adapters["arms"]["phase6_zone_routed_3pack"]
    p6_naive = adapters["arms"]["phase6_naive_unprojected_sum"]

    receipt: dict[str, Any] = {
        "schema": "mcproof-formal-verification-mde-verifier-receipt/v0.1",
        "issue": "siliconcordat/mde#4",
        "target_repo": "Proven-Commons/mcproof",
        "overall_outcome": "HONEST_KILL_BOUNDARY_ON_4B_SINGLE_PASS_SYNTHESIS__ALL_INFRA_NULLSPACE_SECURITY_AND_RETENTION_GATES_PASSED",
        "promotion_recommendation": "DO_NOT_PROMOTE_P2B_SCALE_1_0_FOR_AUTONOMOUS_PROOF_SYNTHESIS; KEEP_DEEP_TACTIC_SEARCH_IN_PLANE1_RETRIEVAL_AND_TIER2_ORACLES",
        "lineage_and_pins": {
            "mcproof_repo_commit": "62dc1371f9bb84a3dbdaaaa21151142623f831bc",
            "plane1_formal_spec_sha256": "49beff2a0185cfa4032170b614a543c0d67541494e858803d21cfb837111b230",
            "plane1_formal_spec_qwen35_tokens": b1["plane1_spec_qwen35_tokens"],
            "corpus_tree_sha256": "5bdb7f30363b956e82947f668f98c48f99876e87fb5ed4f785b873e4f4f98305",
            "zone_manifest_id": "sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca",
            "base_gguf_q8_0_sha256": "10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1",
            "companion_gguf_q4_k_m_sha256": "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
            "safetensors_checkpoint_fingerprint": "1ed4483f1d3ffbc3ffc7a26984be212e7cce455ac1e0651d1bcba1313ea2bd64",
            "llama_server_version": "0.5.0 (build 11146, commit 7fe450e19)",
            "lean_toolchain": "leanprover/lean4:v4.35.0",
            "compiler_manifest_sha256": sha256_file(COMPILE_ART / "MANIFEST.json"),
            "datasets_sha256sums_manifest": "be6eb537d0e2685831f6f920a857ceae6d774f74b3f352c3af7feb400498bd3c",
            "vault_sha256sums_manifest": "b14cf1efeedf7a7c8c15ed57e587c3d18087f557e6ff1807068c4e9c9ef6f6ee",
            "public_holdout_commitment_sha256": "e7c9b9da52be68c4731e35961c31ec33decf440e4ccb00b2c9072e029054f032",
            "worktree_commits": {
                "exo": "e68c406",
                "warp": "492c994",
                "weft_eido": "d87b958",
            },
        },
        "hardware_boundary": {
            "measured_execution_host": "Apple M1 Max (64 GiB unified memory, macOS 27.0.1 arm64, Metal -ngl 99, $0 cloud)",
            "linux_rtx3080_online": False,
            "geminus_8gib_rtx3080_status": "Online on Tailscale (<tailscale-host> / <lan-host>, Windows UX582HS), sshHostKeys=false, TCP ports [22, 2222, 22222, 3389, 5985, 5986, 8080, 11434] closed; warp#4 Linux workbench not yet provisioned",
            "charminar_linux_status": "Online on Tailscale SSH (<tailscale-host>), Linux 7.2.15-1-omarchy x86_64, 5.7 GiB RAM, AMD Radeon Vega Mobile iGPU (no NVIDIA GPU)",
            "analytical_rtx3080_vram_gib": {
                "q8_0_8k_kv_3loras_linux_headless_gib": 4.9451,
                "q8_0_8k_kv_3loras_windows_wddm_gib": 6.1451,
                "q4_k_m_8k_kv_3loras_linux_headless_gib": 3.4034,
                "q4_k_m_8k_kv_3loras_windows_wddm_gib": 4.6034,
                "hard_ceiling_gib": 7.2,
                "clears_ceiling": True,
            },
        },
        "pillar_verifications": {
            "oracles": {
                "passed": oracles["overall_passed"],
                "pytest_passed": "20/20",
                "lean_paranoid_kernels": "6/6",
                "planted_lean_cheats_caught": "14/14 (100%)",
                "mutation_and_float_traps_caught": "5/5 (100%)",
                "f0_corruptions_caught": "4/4 (100%)",
            },
            "corpus_and_holdout": {
                "passed": datasets["overall_passed"] and flake["zero_flake_10_of_10_passed"],
                "counts": {
                    "compile": 96,
                    "validation": 48,
                    "private_holdout": 96,
                    "canaries": 16,
                    "general_retention": 100,
                    "mixed_composition": 30,
                    "hybrid_k0_noise": 2048,
                    "hybrid_k0_y0_anchors": 24,
                },
                "public_vs_vault_overlap": {
                    "id_overlap": 0,
                    "normalized_prompt_overlap": 0,
                    "lean_declaration_overlap": 0,
                    "max_8gram_jaccard": 0.031746,
                },
                "canary_10x_zero_flake": {
                    "runs": 10,
                    "total_live_generations": 160,
                    "byte_flaky_ids": 0,
                    "verdict_flaky_ids": 0,
                },
            },
            "compiler": {
                "passed": compiler["overall_passed"] and rederive["zero_byte_diff_all"],
                "independent_pure_weft_rederivation_zero_byte_diff": rederive["zero_byte_diff_all"],
                "p2b_files": rederive["files"],
                "loud_column_ablation": compiler["loud_column_headline"],
                "public_validation_48_pass_counts": {
                    k: v["passed_count"]
                    for k, v in comp_manifest["validation_scorecard"]["arms"].items()
                    if isinstance(v, dict) and "passed_count" in v
                },
            },
            "stack": {
                "passed_security_and_architecture": True,
                "unit_tests": {
                    "warp": "56/56",
                    "exo": "40/40",
                    "weft_eido": "120/120",
                    "mcproof_stack": "4/4",
                },
                "stage2_ms": stack_p4["step_4_3_warp_stages"]["stage2_elapsed_ms"],
                "stage3_parallel_8slot_ms": stack_p4["step_4_3_warp_stages"]["stage3_elapsed_ms"],
                "stage4_kill_switch_ms": stack_p4["step_4_3_warp_stages"]["stage4_kill_switch_elapsed_ms"],
                "sealed_stage3_p2b_scale_1_0_verdict": "ERR_CANARY_FAILED (8/8 preservation, 6/8 formal -> fail-closed rejection)",
                "adversarial_forged_cert_sabotage_and_goodhart": stack_sealed["adversarial_forged_cert_sabotage_and_goodhart"],
            },
        },
        "sealed_vault_arm_matrix": {
            "B0": {
                "sop_tokens": 0,
                "private_holdout_96": "0/96 (0.00%)",
                "general_retention_100": "84/100 (84.00%)",
                "mixed_composition_30": "8/30 (26.67%)",
                "canaries_16": "15/16 (8/8 pres, 7/8 formal -> tier2_stepping_stone)",
                "holdout_hygiene": b0["private_holdout"]["surface_hygiene_rates"],
                "holdout_top_errors": b0["private_holdout"]["top_error_categories"],
            },
            "B1": {
                "sop_tokens": b1["plane1_spec_qwen35_tokens"],
                "private_holdout_96": "0/96 (0.00%)",
                "holdout_mean_ms": b1["private_holdout"]["mean_elapsed_ms"],
                "holdout_hygiene": b1["private_holdout"]["surface_hygiene_rates"],
                "holdout_top_errors": b1["private_holdout"]["top_error_categories"],
            },
            "P2-A": {
                "sop_tokens": 0,
                "private_holdout_96": "0/96 (0.00%)",
                "general_retention_100": "0/100 (0.00%)",
                "mixed_composition_30": "0/30 (0.00%)",
                "canaries_16": "0/16 (0/8 pres, 0/8 formal -> reject)",
            },
            "P2-B": {
                "sop_tokens": 0,
                "private_holdout_96": "0/96 (0.00%)",
                "general_retention_100": "85/100 (85.00%)",
                "mixed_composition_30": "8/30 (26.67%)",
                "canaries_16": "14/16 (8/8 pres, 6/8 formal -> reject)",
                "holdout_hygiene": p2b_arm["private_holdout"]["surface_hygiene_rates"],
                "holdout_top_errors": p2b_arm["private_holdout"]["top_error_categories"],
            },
            "logit_bias": {
                "sop_tokens": 0,
                "private_holdout_96": f"{lb_arm['private_holdout']['total_passed']}/96",
                "canaries_16": f"{lb_arm['canaries_16']['total_passed']}/16 ({lb_arm['canaries_16']['verdict']})",
            },
            "sabotage": {
                "private_holdout_96": f"{sab_arm['private_holdout']['total_passed']}/96 (7 embedded NUL corruptions)",
                "canaries_16": f"{sab_arm['canaries_16']['total_passed']}/16 (5/8 pres, 5/8 formal -> {sab_arm['canaries_16']['verdict']})",
            },
            "goodhart": {
                "private_holdout_96": f"{gh_arm['private_holdout']['total_passed']}/96",
                "canaries_16_192tok": f"{gh_arm['canaries_16']['total_passed']}/16 ({gh_arm['canaries_16']['verdict']})",
                "warp_stage3_80tok_verdict": "ERR_CANARY_FAILED",
            },
            "phase6_zone_routed_3pack": {
                "general_retention_100": f"{p6_routed['general_retention']['total_passed']}/100 ({p6_routed['general_retention']['accuracy_pct']}%)",
                "mixed_composition_30": f"{p6_routed['mixed_composition']['total_passed']}/30",
                "contested_hard_veto2_ids": p6_routed["contested_hard_veto2_ids"],
                "simultaneous_research_page_holdout_96": f"{p6_routed['simultaneous_research_page_holdout']['total_passed']}/96",
            },
            "phase6_naive_unprojected_sum": {
                "general_retention_100": f"{p6_naive['general_retention']['total_passed']}/100 ({p6_naive['general_retention']['accuracy_pct']}%)",
                "private_holdout_96": f"{p6_naive['private_holdout']['total_passed']}/96",
            },
        },
        "phase5_gates": {
            "primary_gain_vs_b0": {
                "requirement": ">= 50% relative failure reduction vs B0 on 96 private holdouts",
                "measured": "0.0% relative reduction (P2-B 0/96 vs B0 0/96; lean4_auditor errors -21.1% [57->45], missing_tier -50.0% [14->7])",
                "status": "FAIL_HONEST_KILL_BOUNDARY",
            },
            "ceiling_ratio_vs_b1": {
                "requirement": ">= 80% of B1 pass rate on 96 private holdouts",
                "measured": "0/96 vs B1 0/96 (degenerate 0/0 ceiling: 32,216-token prompt injection also scores 0/96 on Qwen3.5-4B)",
                "status": "FAIL_HONEST_KILL_BOUNDARY",
            },
            "token_savings_vs_b1": {
                "requirement": ">= 90% reduction in injected SOP tokens per turn vs B1",
                "measured": "100.0% reduction (0 SOP tokens vs 32,216 SOP tokens)",
                "status": "PASS",
            },
            "safety_canaries": {
                "requirement": "8/8 (100%) verifier-owned safety/preservation canaries",
                "measured": "8/8 (100.0%) passed on P2-B (0 flaky IDs across 10/10 runs; formal domain 6/8 triggers Stage 3 fail-closed ERR_CANARY_FAILED)",
                "status": "PASS",
            },
            "general_retention": {
                "requirement": "<= 1.0 pp accuracy drop vs B0 across 100 coding/math/reasoning/refusal holdouts",
                "measured": "+1.0 pp net gain / 0.0 pp drop (P2-B 85.0% [85/100] vs B0 84.0% [84/100]; P2-A collapses to 0.0% [0/100])",
                "status": "PASS",
            },
            "mixed_integrity": {
                "requirement": "0 corrupted formal blocks and 0 stripped disclaimers across 30 mixed prompts",
                "measured": "8/30 end-to-end pass (30/30 exo ZoneRouter & Hard Veto 2 contract pass; 20 formal block oracle failures = B0 20, 10 prose/skip misses)",
                "status": "FAIL_HONEST_KILL_BOUNDARY",
            },
            "rederivation": {
                "requirement": "0-byte diff (exact SHA-256 match) across independent CPU float64 rebuild",
                "measured": "0-byte diff across 6/6 P2-B files via independent pure-weft CPU float64 rebuild",
                "status": "PASS",
            },
            "tamper_defense": {
                "requirement": "100% fail-closed rejection of forged cert, forged canary, stale lineage, zone drift, Goodhart, and sabotage",
                "measured": "10/10 (100%) rejected fail-closed across Stage 1, Stage 2, Stage 3 (including forged-cert sabotage), and Phase 5 holdout",
                "status": "PASS",
            },
            "rollback_fidelity": {
                "requirement": "0.0 exact next-token logprob diff vs bare B0 after O(1) kill switch",
                "measured": "0.0 exact next-token logprob diff (kill switch 4.029-5.204 ms < 10 ms)",
                "status": "PASS",
            },
        },
        "phase6_gates": {
            "T_C1_solo_preservation": {
                "requirement": ">= 90% solo preservation in paired and triple stacks",
                "measured": "99.85% min subspace & routed step-0 preservation (corpus 100.0%, weft-eido 99.85%, formal-verification 100.0%); 0/96 on private_holdout (matches solo P2-B 0/96)",
                "status": "PASS_SUBSPACE_AND_ROUTING__DEGENERATE_0_OF_96_HOLDOUT",
            },
            "T_C2_mixed_zone_isolation": {
                "requirement": "0 formal-block corruptions and 0 prose-rule leaks across 30 mixed prompts",
                "measured": "30/30 on public structural suite & 30/30 exo router/Hard-Veto-2 checks; 8/30 on sealed mixed_composition_30.jsonl (20 4B formal synthesis failures, 12 prose/skip misses)",
                "status": "FAIL_ON_SEALED_4B_GENERATION__PASS_ON_ROUTER_ISOLATION",
            },
            "T_C3_base_retention": {
                "requirement": "<= 1.5 pp accuracy drop vs bare W0 across 100 prompts, beating naive unweighted summation",
                "measured": "85.0% (85/100) routed triple vs 84.0% (84/100) bare W0 (+1.0 pp / 0.0 pp drop <= 1.5 pp), beating naive unprojected sum 0.0% (0/100) by +85.0 pp",
                "status": "PASS",
            },
            "T_C4_order_invariance_and_rollback": {
                "requirement": "Order-invariant across 3!=6 permutations and 0.0 drift after per-slot O(1) rollback",
                "measured": "0.0 CPU float64 matrix diff, 4.44e-16 forward diff, 0.0 live llama-server order logprob diff, 0.0 per-slot & full-stack rollback diff (4.029-5.067 ms)",
                "status": "PASS",
            },
            "T_C5_serving_budget": {
                "requirement": "<= 15% tok/s overhead, >= 8192 KV cache tokens/slot, <= 7.2 GiB VRAM on 8 GiB GPU",
                "measured": "0.0%-0.31% <= 15.0% latency overhead, 8192 KV tokens/slot, 4.9451 GiB headless / 6.1451 GiB WDDM <= 7.2 GiB analytical RTX 3080 VRAM (geminus SSH closed)",
                "status": "PASS_ANALYTICAL_VRAM_AND_LIVE_M1_MAX__LINUX_RTX3080_OFFLINE",
            },
            "seven_interference_hazards_H1_to_H7": {
                "requirement": "7/7 hazards pass live under Tier 1 > Tier 2 RepoPolicy > Specialist Pack > Base Prose Pack",
                "measured": "7/7 deterministic L5/L4/L3/DOM/WCAG hazard mechanisms passed live (including weft-eido PR 25 0 dark-theme WCAG failures across 360 hues and Hard Veto 2 ContestedPreferenceError)",
                "status": "PASS",
            },
        },
    }

    out_path = VERIF_DIR / "VERIFICATION_RECEIPT.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    vault_prompts = load_all_vault_prompts()
    checked_files = assert_zero_vault_leak_in_dir(VERIF_DIR, vault_prompts)
    print(
        json.dumps(
            {
                "receipt_written": str(out_path.name),
                "receipt_sha256": sha256_file(out_path),
                "zero_vault_leak_verified_files": checked_files,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
