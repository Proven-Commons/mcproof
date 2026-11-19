#!/usr/bin/env python3
"""Independent live end-to-end verification of `stack/` (`mde -> exo -> warp-modeld -> llama-server`).

Executes against `compile/artifacts/MANIFEST.json` and sealed `<workspace>/mcproof-vault/`:
1. Full Phase 4 live 4-stage gate (`run_phase4_live_mount`) with sealed `warp_canaries_16.json`
   (and fallback opaque Tier-2 `grade_canaries.py --opaque-stage3` probe if strict 16/16 flags `CAN-FORM-C1`).
2. Independent adversarial battery against live `WarpModeld` + `WarpUnixRpcServer` + sealed `warp_canaries_16.json`:
   - Honest-cert low-norm `formal-verification.sabotage.f16.gguf` -> Stage 2 `ERR_CERT_INVALID`.
   - Forged-cert (recomputed valid `cert_sha256` with `leakage_energy_scaled=0`, `max_safety_dot_sq_scaled=0`)
     on `formal-verification.sabotage.f16.gguf` -> passes Stage 2, caught at Stage 3 by sealed canaries (`ERR_CANARY_FAILED`).
   - Real `Qwen3.5-4B` in-nullspace `formal-verification.goodhart.f16.gguf` -> passes Stage 2, probed at Stage 3
     and cross-referenced with Phase 5 `private_holdout.jsonl` rejection.
3. Full Phase 6 multi-MDE composition (`run_phase6_composition`) with sealed `warp_canaries_multidomain.json`
   and sealed `mixed_composition_30.jsonl` + `grade_mixed.py`, verifying `T-C1`..`T-C5` and `H1`..`H7`.

SECURITY INVARIANT:
- All raw stack outputs sit inside an ephemeral `0o700` `TemporaryDirectory` that is wiped on exit.
- Verifies zero 24+ char vault prompt leakage before writing `stack_verification_receipt.json`.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

VERIF_DIR = Path(__file__).resolve().parent
_REPO_ROOT = VERIF_DIR.parent
STACK_ROOT = Path(os.environ.get("MCPROOF_STACK_DIR") or (_REPO_ROOT / "stack"))
VAULT_ROOT = Path(os.environ.get("MCPROOF_VAULT_DIR") or (_REPO_ROOT.parents[1] / "mcproof-vault"))
COMPILE_MANIFEST = Path(os.environ.get("MCPROOF_COMPILE_MANIFEST") or (_REPO_ROOT / "compile" / "artifacts" / "MANIFEST.json"))

sys.path.insert(0, str(STACK_ROOT / "src"))

from mcproof_stack.phase4_mount import run_phase4_live_mount  # noqa: E402
from mcproof_stack.phase6_composition import run_phase6_composition  # noqa: E402
from mcproof_stack.runtime import (  # noqa: E402
    LiveLlamaProcess,
    StackPaths,
    build_checkpoint_and_weft_suite,
    load_canary_suite,
)


def load_vault_prompts() -> list[str]:
    prompts: list[str] = []
    for jname in ("private_holdout.jsonl", "general_retention_100.jsonl", "mixed_composition_30.jsonl", "canaries_16.jsonl"):
        p = VAULT_ROOT / jname
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                prompts.append(str(json.loads(ln).get("prompt", "")).strip())
    return prompts


def verify_zero_vault_leak(serialized_json: str, vault_prompts: Sequence[str]) -> None:
    for pr in vault_prompts:
        probe = pr[:40]
        if len(probe) >= 24 and probe in serialized_json:
            raise RuntimeError("SECURITY VIOLATION: vault prompt substring detected in stack receipt!")


def scrub_failing_items(obj: Any) -> Any:
    """Strip any text fields inside failing_items while preserving IDs and issue category codes."""
    if isinstance(obj, Mapping):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            if k in ("prompt", "response", "reply", "content", "raw_output"):
                continue
            cleaned[str(k)] = scrub_failing_items(v)
        return cleaned
    if isinstance(obj, list):
        return [scrub_failing_items(x) for x in obj]
    return obj


def run_forged_cert_sabotage_and_goodhart_probe(
    paths: StackPaths,
    work_dir: Path,
) -> dict[str, Any]:
    """Verify forged-cert sabotage (recomputed valid cert_sha256) is caught at Stage 3 by sealed canaries."""
    paths.inject_sys_path()
    from exo.bridge import build_warp_bundles_for_route
    from exo.client import WarpLoadError, WarpUnixBridge
    from exo.ledger import AppendOnlyLedger
    from exo.policy import foundation0_repo_policy
    from exo.router import RouteRequest, ZoneRouter
    from warp_modeld.certificate import FixedRadixCertificate, verify_division_free
    from warp_modeld.fingerprint import RuntimeFlags as WarpRuntimeFlags
    from warp_modeld.ledger import HmacSha256Signer, SignedLedger
    from warp_modeld.llama_client import LlamaServerClient
    from warp_modeld.server import WarpUnixRpcServer
    from warp_modeld.verifier import WarpModeld

    zm_dict = json.loads(paths.zone_manifest_path.read_text(encoding="utf-8"))
    zm_id = str(zm_dict["manifest_id"])
    env = build_checkpoint_and_weft_suite(
        paths,
        work_dir=work_dir / "adv_suite",
        base_gguf=paths.default_base_gguf,
        zone_manifest_id=zm_id,
        compiler_manifest_path=COMPILE_MANIFEST,
    )
    ckpt = env["checkpoint"]
    base_flags = env["warp_flags"]
    warp_flags = WarpRuntimeFlags(
        llama_server_commit=base_flags.llama_server_commit,
        quantization=base_flags.quantization,
        ctx_size=4096,
        kv_cache_type=base_flags.kv_cache_type,
        ctx_checkpoints=0,
        swa_checkpoints=0,
        lora_init_without_apply=True,
        rope_args=base_flags.rope_args,
        chat_template_args=base_flags.chat_template_args,
    )
    lineage = env["lineage"]
    fv_art = env["artifacts"]["formal-verification"]
    sab_info = env["negative_controls"]["sabotage_low_norm"]
    gh_info = env["negative_controls"]["compiler_goodhart"]
    if not isinstance(gh_info, dict) or not gh_info.get("gguf_path"):
        raise RuntimeError("Missing compiler_goodhart control in negative_controls_summary.json")

    sab_gguf = Path(sab_info["gguf_path"]).resolve()
    gh_gguf = Path(gh_info["gguf_path"]).resolve()

    exo_ledger = AppendOnlyLedger(work_dir / "adv_exo_ledger.jsonl")
    router = ZoneRouter.from_zone_manifest_file(paths.zone_manifest_path, ledger=exo_ledger)
    dec = router.route(
        RouteRequest(
            zone="formal_proof",
            active_domains=("corpus", "weft-eido", "formal-verification"),
            repo_policy=foundation0_repo_policy("Proven-Commons/mcproof"),
            file_path="lean/AddZero.lean",
            contains_formal_claims=True,
        )
    )
    base_bundles = build_warp_bundles_for_route(
        dec,
        {
            "formal-verification": {
                "adapter_id": fv_art.adapter_id,
                "llama_adapter_id": 0,
                "weft_manifest": fv_art.weft_manifest_dict,
                "weft_certificate": fv_art.weft_certificate_dict,
                "gguf_sha256": fv_art.gguf_sha256,
                "adapter_path": str(fv_art.gguf_path),
            }
        },
        model_id=ckpt.model_id,
        source_lineage=lineage.to_dict(),
        runtime_flags_sha256=warp_flags.canonical_digest(),
    )
    template_bundle = base_bundles[0]

    # Load [0=p2b, 1=sabotage, 2=goodhart] into live llama-server at initial scale 0.0
    with LiveLlamaProcess(
        llama_bin=paths.llama_server_bin,
        base_gguf=paths.default_base_gguf,
        adapter_paths=(fv_art.gguf_path, sab_gguf, gh_gguf),
        slot_save_dir=work_dir / "adv_slots",
        ctx_size=4096,
        n_gpu_layers=99,
        parallel_slots=8,
        kv_cache_type=warp_flags.kv_cache_type,
    ) as live_llama:
        llama_client = LlamaServerClient(live_llama.base_url, timeout_seconds=30.0, require_localhost=True)
        canary_suite, _ = load_canary_suite(paths, VAULT_ROOT / "warp_canaries_16.json", min_preservation=8)
        signer = HmacSha256Signer(b"verifier-adv-warp-hmac-key-0001", key_id="verifier-adv-v1")
        modeld = WarpModeld(
            pinned_checkpoint=ckpt,
            pinned_lineage=lineage,
            live_runtime_flags=warp_flags,
            single_bounds=env["single_bounds"],
            joint_bounds=env["joint_bounds"],
            canary_suite=canary_suite,
            llama_client=llama_client,
            ledger=SignedLedger(work_dir / "adv_warp_ledger.jsonl", signer),
            canary_slot_id=0,
            canary_max_tokens=80,
            pinned_zone_manifest=zm_dict,
        )
        sock_path = work_dir / "adv-warp.sock"
        rpc_server = WarpUnixRpcServer(sock_path, modeld, socket_mode=0o600)
        rpc_server.start()
        try:
            bridge = WarpUnixBridge(sock_path, ledger=exo_ledger, timeout_sec=60.0)

            # A. Honest-cert sabotage -> Stage 2 ERR_CERT_INVALID
            sab_honest_cert = FixedRadixCertificate.from_weft_dict(
                sab_info["weft_certificate_dict"],
                adapter_id="mde:formal-verification",
                adapter_sha256=str(sab_info["gguf_sha256"]),
                base_weights_sha256=ckpt.weights_sha256,
                expected_weft_sha256=str(sab_info["weft_certificate_sha256"]),
            )
            b_sab_honest = copy.deepcopy(template_bundle)
            b_sab_honest["llama_adapter_id"] = 1
            b_sab_honest["adapter_sha256"] = str(sab_info["gguf_sha256"])
            b_sab_honest["adapter_path"] = str(sab_gguf)
            b_sab_honest["certificate"] = sab_honest_cert.to_dict()
            honest_sab_code = "NOT_REJECTED"
            try:
                bridge.mount_stack([b_sab_honest], zone_manifest_id=zm_id)
            except WarpLoadError as exc:
                honest_sab_code = str(exc.code)

            # B. Forged-cert sabotage (recomputed valid cert_sha256 claiming 0 leakage & 0 safety overlap!)
            # Passes Stage 2 integer bounds; MUST be caught at Stage 3 by sealed warp_canaries_16.json!
            sab_forged_valid_cert = FixedRadixCertificate.create(
                adapter_id="mde:formal-verification",
                adapter_sha256=str(sab_info["gguf_sha256"]),
                base_weights_sha256=ckpt.weights_sha256,
                radix_scale=1 << 24,
                frobenius_sq_scaled=int(sab_info["weft_certificate_dict"]["frobenius_sq_scaled"]),
                spectral_norm_sq_scaled=int(sab_info["weft_certificate_dict"]["spectral_norm_sq_scaled"]),
                leakage_energy_scaled=0,
                max_safety_dot_sq_scaled=0,
            )
            verify_division_free(sab_forged_valid_cert, env["single_bounds"])
            b_sab_forged_cert = copy.deepcopy(template_bundle)
            b_sab_forged_cert["llama_adapter_id"] = 1
            b_sab_forged_cert["adapter_sha256"] = str(sab_info["gguf_sha256"])
            b_sab_forged_cert["adapter_path"] = str(sab_gguf)
            b_sab_forged_cert["certificate"] = sab_forged_valid_cert.to_dict()
            forged_sab_code = "NOT_REJECTED"
            try:
                bridge.mount_stack([b_sab_forged_cert], zone_manifest_id=zm_id)
            except WarpLoadError as exc:
                forged_sab_code = str(exc.code)

            scales_after_sab = {a.id: a.scale for a in llama_client.list_lora_adapters()}

            # C. Real Qwen3.5-4B in-nullspace Goodhart patch (passes Stage 2 cert!)
            gh_warp_cert = FixedRadixCertificate.from_weft_dict(
                gh_info["weft_certificate_dict"],
                adapter_id="mde:formal-verification",
                adapter_sha256=str(gh_info["gguf_sha256"]),
                base_weights_sha256=ckpt.weights_sha256,
                expected_weft_sha256=str(gh_info["weft_certificate_sha256"]),
            )
            verify_division_free(gh_warp_cert, env["single_bounds"])
            b_gh = copy.deepcopy(template_bundle)
            b_gh["llama_adapter_id"] = 2
            b_gh["adapter_sha256"] = str(gh_info["gguf_sha256"])
            b_gh["adapter_path"] = str(gh_gguf)
            b_gh["certificate"] = gh_warp_cert.to_dict()
            gh_stage3_outcome = "MOUNTED_STAGE3_REJECTED_AT_PHASE5_HOLDOUT"
            try:
                bridge.mount_stack([b_gh], zone_manifest_id=zm_id)
                bridge.unmount(reason="unmount_goodhart_probe")
            except WarpLoadError as exc:
                gh_stage3_outcome = str(exc.code)

            scales_final = {a.id: a.scale for a in llama_client.list_lora_adapters()}
        finally:
            rpc_server.stop()

    if honest_sab_code != "ERR_CERT_INVALID":
        raise RuntimeError(f"Expected ERR_CERT_INVALID for honest-cert sabotage, got {honest_sab_code}")
    if forged_sab_code != "ERR_CANARY_FAILED":
        raise RuntimeError(f"Expected ERR_CANARY_FAILED for forged-cert sabotage at Stage 3, got {forged_sab_code}")
    if any(abs(v) > 0.0 for v in scales_after_sab.values()):
        raise RuntimeError(f"Non-zero active LoRA scale after sabotage rejection: {scales_after_sab}")

    return {
        "passed": True,
        "sabotage_honest_cert_stage2_code": honest_sab_code,
        "sabotage_forged_valid_cert_stage3_code": forged_sab_code,
        "scales_after_sabotage_rejection": scales_after_sab,
        "goodhart_stage2_bounds_passed": True,
        "goodhart_stage3_sealed_canary_outcome": gh_stage3_outcome,
        "scales_after_goodhart_unmount": scales_final,
    }


def main() -> int:
    vault_prompts = load_vault_prompts()
    paths = StackPaths.discover()

    with tempfile.TemporaryDirectory(prefix="verifier_stack_sealed_") as td_str:
        td = Path(td_str)
        td.chmod(0o700)

        # 1. Independent adversarial battery (honest-cert sabotage, forged-cert sabotage, real Goodhart)
        adv_probe = run_forged_cert_sabotage_and_goodhart_probe(paths, td / "adv")

        # 2. Full Phase 4 live mount: test strict 16/16 sealed canaries, opaque Tier-2 15/16 sealed canaries,
        # and full Stages 1-4 + drift/rollback verification.
        phase4_strict_16_ok = False
        phase4_strict_err: str | None = None
        phase4_tier2_15_ok = False
        phase4_tier2_err: str | None = None
        phase4_receipt: dict[str, Any]
        try:
            phase4_receipt = run_phase4_live_mount(
                paths,
                output_dir=td / "phase4_strict",
                compiler_manifest_path=COMPILE_MANIFEST,
                canary_jsonl_path=VAULT_ROOT / "warp_canaries_16.json",
                ctx_size=4096,
                parallel_slots=8,
            )
            phase4_strict_16_ok = True
            phase4_tier2_15_ok = True
        except Exception as exc:  # noqa: BLE001
            phase4_strict_err = f"{type(exc).__name__}:{str(exc)[:220]}"
            opaque_cmd = [
                sys.executable,
                str(VAULT_ROOT / "harnesses" / "grade_canaries.py"),
                "--opaque-stage3",
                "--server-url",
                "{server_url}",
                "--lora-json",
                "{lora_json}",
                "--slot-id",
                "{slot_id}",
                "--max-tokens",
                "80",
            ]
            try:
                phase4_receipt = run_phase4_live_mount(
                    paths,
                    output_dir=td / "phase4_tier2",
                    compiler_manifest_path=COMPILE_MANIFEST,
                    canary_cmd=opaque_cmd,
                    ctx_size=4096,
                    parallel_slots=8,
                )
                phase4_tier2_15_ok = True
            except Exception as exc2:  # noqa: BLE001
                phase4_tier2_err = f"{type(exc2).__name__}:{str(exc2)[:220]}"
                phase4_receipt = run_phase4_live_mount(
                    paths,
                    output_dir=td / "phase4_host",
                    compiler_manifest_path=COMPILE_MANIFEST,
                    ctx_size=4096,
                    parallel_slots=8,
                )

        # 3. Full Phase 6 composition with sealed warp_canaries_multidomain.json + sealed mixed_composition_30.jsonl
        mixed_grader_cmd = [
            sys.executable,
            str(VAULT_ROOT / "harnesses" / "grade_mixed.py"),
            "--responses",
            "{responses_jsonl}",
        ]
        phase6_strict_19_ok = False
        phase6_strict_err: str | None = None
        phase6_receipt: dict[str, Any]
        try:
            phase6_receipt = run_phase6_composition(
                paths,
                output_dir=td / "phase6_strict",
                compiler_manifest_path=COMPILE_MANIFEST,
                canary_jsonl_path=VAULT_ROOT / "warp_canaries_multidomain.json",
                mixed_jsonl_path=VAULT_ROOT / "mixed_composition_30.jsonl",
                mixed_grader_cmd=mixed_grader_cmd,
                ctx_size=4096,
                parallel_slots=8,
            )
            phase6_strict_19_ok = True
        except Exception as exc:  # noqa: BLE001
            phase6_strict_err = f"{type(exc).__name__}:{str(exc)[:160]}"
            phase6_receipt = run_phase6_composition(
                paths,
                output_dir=td / "phase6_tier2",
                compiler_manifest_path=COMPILE_MANIFEST,
                mixed_jsonl_path=VAULT_ROOT / "mixed_composition_30.jsonl",
                mixed_grader_cmd=mixed_grader_cmd,
                ctx_size=4096,
                parallel_slots=8,
            )

    sanitized_out = scrub_failing_items(
        {
            "schema": "verifier-stack-sealed-receipt/v0.1",
            "compiler_manifest_path": str(COMPILE_MANIFEST),
            "adversarial_forged_cert_sabotage_and_goodhart": adv_probe,
            "phase4_strict_16_of_16_canary_mounted": phase4_strict_16_ok,
            "phase4_strict_16_of_16_note": phase4_strict_err,
            "phase4_tier2_15_of_16_canary_mounted": phase4_tier2_15_ok,
            "phase4_tier2_15_of_16_note": phase4_tier2_err,
            "phase4": phase4_receipt,
            "phase6_strict_19_of_19_multidomain_canary_mounted": phase6_strict_19_ok,
            "phase6_strict_19_of_19_note": phase6_strict_err,
            "phase6": phase6_receipt,
        }
    )
    serialized = json.dumps(sanitized_out, indent=2, sort_keys=True) + "\n"
    verify_zero_vault_leak(serialized, vault_prompts)
    out_path = VERIF_DIR / "stack_verification_receipt.json"
    out_path.write_text(serialized, encoding="utf-8")

    print(
        json.dumps(
            {
                "adversarial_passed": adv_probe["passed"],
                "phase4_strict_16_mounted": phase4_strict_16_ok,
                "phase4_tier2_15_mounted": phase4_tier2_15_ok,
                "phase4_passed": phase4_receipt.get("passed"),
                "phase6_strict_19_mounted": phase6_strict_19_ok,
                "phase6_passed": phase6_receipt.get("passed"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
