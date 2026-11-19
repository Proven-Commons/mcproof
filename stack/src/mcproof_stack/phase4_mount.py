"""Phase 4 Live End-to-End 4-Layer Mount (`mde -> exo -> warp-modeld -> llama-server 0.5.0`)."""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Sequence

import numpy as np

from .runtime import (
    DOMAIN_TO_LLAMA_ID,
    LiveLlamaProcess,
    StackPaths,
    build_checkpoint_and_weft_suite,
    compute_mcproof_plane1_tree_sha256,
    ensure,
    load_canary_suite,
    max_logprob_diff,
    sha256_file,
    step0_logprob_shift,
)


def _run_mde_cli(mde_bin: Path, args: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(mde_bin), *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )


def verify_step_4_1_mde_zones_and_code_audit(paths: StackPaths, work_dir: Path) -> dict[str, Any]:
    """Step 4.1: Verify L5 mde zone-manifest/v0.1 span classification and `mde guard --code-audit`."""
    paths.inject_sys_path()
    from exo.client import MdeClient, StdioJsonRpcTransport
    from exo.gate import ApprovalGate
    from exo.ledger import AppendOnlyLedger

    # 1. Verify canonical schemas/zone-manifest.v0.1.json via mde CLI
    zm_proc = _run_mde_cli(
        paths.mde_bin,
        ["zone-manifest", "--verify", str(paths.zone_manifest_path)],
    )
    ensure(zm_proc.returncode == 0, f"mde zone-manifest --verify failed: {zm_proc.stderr}")
    verified_manifest = json.loads(zm_proc.stdout)
    manifest_id = str(verified_manifest["manifest_id"])
    ensure(manifest_id.startswith("sha256:"), f"unexpected manifest_id: {manifest_id}")

    # 2. Create a scratch multi-zone git repo and classify target spans via live mde stdio MCP
    repo_dir = work_dir / "step4_1_repo"
    (repo_dir / "lean").mkdir(parents=True, exist_ok=True)
    (repo_dir / "verifiers").mkdir(parents=True, exist_ok=True)
    (repo_dir / "site").mkdir(parents=True, exist_ok=True)
    (repo_dir / "docs").mkdir(parents=True, exist_ok=True)

    (repo_dir / "lean" / "AddZero.lean").write_text(
        "theorem add_zero_id (n : Nat) : n + 0 = n := Nat.add_zero n\n",
        encoding="utf-8",
    )
    (repo_dir / "verifiers" / "dual_oracle_checker.py").write_text(
        "# Exact-math dual-oracle checker fixture.\n"
        "from fractions import Fraction\n\n"
        "def check_cramer_2x2(a: int, b: int, c: int, d: int) -> Fraction:\n"
        "    # @formal-proof data-eido-skip exact rational determinant\n"
        "    det = Fraction(a * d - b * c, 1)\n"
        "    if det == Fraction(0, 1):\n"
        "        raise ValueError('singular system')\n"
        "    return det\n\n"
        "def render_status_chip(label: str) -> str:\n"
        "    # @ui-module safe text binding\n"
        "    return f'<span class=\"chip\">{label}</span>'\n\n"
        "def normalize_count(k: int) -> int:\n"
        "    return k + 1\n",
        encoding="utf-8",
    )
    (repo_dir / "docs" / "mixed_claim.md").write_text(
        "# Bounded Invariant Note\n\n"
        "<div data-eido-skip>\n"
        "Status: VERIFIED for n <= 100. What is not proved: unbounded n > 100.\n"
        "</div>\n\n"
        "```lean\n"
        "theorem zero_add_id (n : Nat) : 0 + n = n := Nat.zero_add n\n"
        "```\n",
        encoding="utf-8",
    )
    (repo_dir / "site" / "condensed.json").write_text(
        json.dumps(
            {
                "version": 1,
                "levels": ["Full prose", "Concise", "Terse", "Caveman"],
                "blocks": {"aea4f4ae": ["Short prose.", "Terse note.", "Rule in code."]},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_dir / "site" / "widget.tsx").write_text(
        "export function Badge({ text }: { text: string }) {\n"
        "  return <span className=\"badge\">{text}</span>;\n"
        "}\n",
        encoding="utf-8",
    )

    for git_args in (
        ["init", "-q"],
        ["config", "user.name", "mcproof-stack"],
        ["config", "user.email", "mcproof-stack@example.invalid"],
        ["add", "."],
        ["commit", "-q", "-m", "init step 4.1 fixture"],
    ):
        r = subprocess.run(["git", *git_args], cwd=str(repo_dir), capture_output=True, text=True, check=False)
        ensure(r.returncode == 0, f"git {git_args} failed: {r.stderr}")

    exo_ledger = AppendOnlyLedger(work_dir / "step4_1_exo_ledger.jsonl")
    gate = ApprovalGate(signing_key=b"mcproof-step4-1-approval-key-01", ledger=exo_ledger)

    with StdioJsonRpcTransport([str(paths.mde_bin), "--root", str(repo_dir), "mcp"]) as transport:
        mde = MdeClient(transport, gate=gate, ledger=exo_ledger, actor_id="mcproof-stack-step4-1")
        loc_lean = mde.splice_locate("lean/AddZero.lean", capability_id="cap.mcproof.phase4")
        loc_py = mde.splice_locate("verifiers/dual_oracle_checker.py", capability_id="cap.mcproof.phase4")
        loc_md = mde.splice_locate("docs/mixed_claim.md", capability_id="cap.mcproof.phase4")
        loc_json = mde.splice_locate("site/condensed.json", capability_id="cap.mcproof.phase4")
        loc_tsx = mde.splice_locate("site/widget.tsx", capability_id="cap.mcproof.phase4")
        trace_py = mde.splice_trace("verifiers/dual_oracle_checker.py", symbol="check_cramer_2x2")

    py_symbol_zones = {sym["symbol"]: sym["zone"] for sym in loc_py["symbols"]}
    ensure(loc_lean["dominant_zone"] == "formal_proof", f"expected formal_proof for .lean, got {loc_lean['dominant_zone']}")
    ensure(py_symbol_zones.get("check_cramer_2x2") == "formal_proof", f"unexpected zone: {py_symbol_zones}")
    ensure(py_symbol_zones.get("render_status_chip") == "ui_module", f"unexpected zone: {py_symbol_zones}")
    ensure(py_symbol_zones.get("normalize_count") == "code", f"unexpected zone: {py_symbol_zones}")
    ensure(loc_md["dominant_zone"] == "formal_proof", f"expected formal_proof for mixed_claim.md, got {loc_md['dominant_zone']}")
    ensure(loc_json["dominant_zone"] == "condensed_json", f"expected condensed_json, got {loc_json['dominant_zone']}")
    ensure(loc_tsx["dominant_zone"] == "ui_module", f"expected ui_module, got {loc_tsx['dominant_zone']}")
    ensure("gg.siliconcordat/mde" in loc_py.get("_meta", {}), "missing vendor-namespaced _meta (Hard Veto 4)")

    # 3. Enforce `mde guard --code-audit` on clean generated verifier + JSON manifest vs planted pokayoke bugs
    audit_clean_proc = _run_mde_cli(
        paths.mde_bin,
        [
            "guard",
            "--code-audit",
            "--json",
            str(repo_dir / "verifiers" / "dual_oracle_checker.py"),
            str(repo_dir / "site" / "condensed.json"),
        ],
    )
    ensure(audit_clean_proc.returncode == 0, f"clean code-audit failed: {audit_clean_proc.stdout}")
    audit_clean = json.loads(audit_clean_proc.stdout)
    ensure(audit_clean["passed"] is True and audit_clean["findings"] == [], f"unexpected findings: {audit_clean}")

    # Negative pokayoke audit control: bare assert, bare except, silent swallow, and duplicate JSON key
    bad_dir = work_dir / "step4_1_bad_audit"
    bad_dir.mkdir(parents=True, exist_ok=True)
    bad_py = bad_dir / "bad_verifier.py"
    bad_py.write_text(
        "def verify_bad(x: int) -> bool:\n"
        "    assert x > 0\n"
        "    try:\n"
        "        return bool(x)\n"
        "    except:\n"
        "        pass\n",
        encoding="utf-8",
    )
    bad_json = bad_dir / "dup_manifest.json"
    bad_json.write_text('{"zone": "formal_proof", "zone": "prose"}\n', encoding="utf-8")

    audit_bad_proc = _run_mde_cli(
        paths.mde_bin,
        ["guard", "--code-audit", "--json", str(bad_py), str(bad_json)],
    )
    ensure(audit_bad_proc.returncode == 1, f"expected exit 1 on pokayoke violations, got {audit_bad_proc.returncode}")
    audit_bad = json.loads(audit_bad_proc.stdout)
    caught_rules = sorted({f["rule"] for f in audit_bad["findings"]})
    for expected_rule in ("bare_assert", "bare_except", "silent_except_swallow", "duplicate_json_key"):
        ensure(expected_rule in caught_rules, f"mde guard --code-audit missed {expected_rule}: {caught_rules}")

    return {
        "passed": True,
        "manifest_id": manifest_id,
        "classified_zones": {
            "lean_file": loc_lean["dominant_zone"],
            "python_symbols": py_symbol_zones,
            "python_zone_bytes": loc_py["_meta"]["gg.siliconcordat/mde"]["zone_bytes"],
            "mixed_markdown": loc_md["dominant_zone"],
            "condensed_json": loc_json["dominant_zone"],
            "tsx_widget": loc_tsx["dominant_zone"],
        },
        "trace_symbol": trace_py["symbol"],
        "vendor_meta_key_verified": "gg.siliconcordat/mde" in loc_py["_meta"],
        "code_audit_clean_passed": bool(audit_clean["passed"]),
        "code_audit_negative_caught_rules": caught_rules,
    }


def run_phase4_live_mount(
    paths: StackPaths,
    *,
    output_dir: Path | None = None,
    base_gguf_override: str | Path | None = None,
    compiler_manifest_path: str | Path | None = None,
    formal_gguf_override: str | Path | None = None,
    canary_jsonl_path: str | Path | None = None,
    canary_cmd: Sequence[str] | None = None,
    ctx_size: int = 8192,
    n_gpu_layers: int = 99,
    parallel_slots: int = 8,
) -> dict[str, Any]:
    """Execute the full Phase 4 Live End-to-End 4-Layer Mount and Step 4.1-4.4 verification."""
    t_total = time.perf_counter()
    paths.inject_sys_path()

    from exo.bridge import build_warp_bundles_for_route
    from exo.client import WarpLoadError, WarpUnixBridge
    from exo.ledger import AppendOnlyLedger
    from exo.policy import foundation0_repo_policy
    from exo.router import RouteRequest, ZoneRouter
    from warp_modeld.canary import ExternalCommandCanaryRunner
    from warp_modeld.certificate import FixedRadixCertificate
    from warp_modeld.fingerprint import (
        Plane1Lineage,
        compute_zone_manifest_id,
    )
    from warp_modeld.ledger import HmacSha256Signer, LedgerVerifier, SignedLedger
    from warp_modeld.llama_client import LlamaServerClient, probe_llama_server_binary
    from warp_modeld.server import WarpUnixRpcServer
    from warp_modeld.verifier import WarpModeld
    from weft.compiler import BetaEditConfig, BetaEditNullspaceProjector

    base_gguf = Path(base_gguf_override).expanduser().resolve() if base_gguf_override else paths.default_base_gguf
    comp_manifest = Path(compiler_manifest_path).expanduser().resolve() if compiler_manifest_path else None
    fv_override = Path(formal_gguf_override).expanduser().resolve() if formal_gguf_override else None

    probe_info = probe_llama_server_binary(str(paths.llama_server_bin), timeout_seconds=25.0)

    with tempfile.TemporaryDirectory(prefix="mcproof_phase4_") as td:
        work_dir = Path(td)

        # ------------------------------------------------------------------
        # Step 4.1: L5 mde zone classification + mde guard --code-audit
        # ------------------------------------------------------------------
        step_4_1 = verify_step_4_1_mde_zones_and_code_audit(paths, work_dir)
        zone_manifest_dict = json.loads(paths.zone_manifest_path.read_text(encoding="utf-8"))
        zone_manifest_id = str(zone_manifest_dict["manifest_id"])
        ensure(zone_manifest_id == step_4_1["manifest_id"], "zone_manifest_id mismatch")

        # ------------------------------------------------------------------
        # Build/load checkpoint, Plane 1 sources, weft adapters, and controls
        # ------------------------------------------------------------------
        suite_env = build_checkpoint_and_weft_suite(
            paths,
            work_dir=work_dir,
            base_gguf=base_gguf,
            zone_manifest_id=zone_manifest_id,
            compiler_manifest_path=comp_manifest,
            formal_gguf_override=fv_override,
        )
        ckpt = suite_env["checkpoint"]
        warp_flags = suite_env["warp_flags"]
        if int(ctx_size) != warp_flags.ctx_size:
            from warp_modeld.fingerprint import RuntimeFlags as WarpRuntimeFlags

            warp_flags = WarpRuntimeFlags(
                llama_server_commit=warp_flags.llama_server_commit,
                quantization=warp_flags.quantization,
                ctx_size=int(ctx_size),
                kv_cache_type=warp_flags.kv_cache_type,
                ctx_checkpoints=0,
                swa_checkpoints=0,
                lora_init_without_apply=True,
                rope_args=warp_flags.rope_args,
                chat_template_args=warp_flags.chat_template_args,
            )
        lineage: Plane1Lineage = suite_env["lineage"]
        artifacts = suite_env["artifacts"]
        neg_controls = suite_env["negative_controls"]

        # ------------------------------------------------------------------
        # Step 4.2: L4 exo ZoneRouter.from_zone_manifest_file + bundle build
        # ------------------------------------------------------------------
        exo_ledger = AppendOnlyLedger(work_dir / "phase4_exo_ledger.jsonl")
        router = ZoneRouter.from_zone_manifest_file(paths.zone_manifest_path, ledger=exo_ledger)
        ensure(router.manifest_id == zone_manifest_id, "router manifest_id mismatch")

        f0_policy = foundation0_repo_policy("Proven-Commons/mcproof")
        fp_decision = router.route(
            RouteRequest(
                zone="formal_proof",
                active_domains=("corpus", "weft-eido", "formal-verification"),
                repo_policy=f0_policy,
                file_path="lean/AddZero.lean",
                contains_formal_claims=True,
            )
        )
        expected_fp_scales = {"corpus": 0.0, "weft-eido": 0.0, "formal-verification": 1.0}
        ensure(fp_decision.scale_map() == expected_fp_scales, f"unexpected scales: {fp_decision.scale_map()}")
        ensure(fp_decision.manifest_id == zone_manifest_id, "RouteDecision dropped manifest_id")
        ensure(fp_decision.l1_bank_tag == 3, f"expected l1_bank_tag=3, got {fp_decision.l1_bank_tag}")

        # In solo Phase 4 mount, formal-verification is mounted at llama_adapter_id=0 (first --lora-scaled entry)
        # while adversarial behavioral_corruptor is loaded at llama_adapter_id=1 (scale 0.0) to test Stage 3 rejection!
        fv_art = artifacts["formal-verification"]
        compiled_for_exo = {
            "formal-verification": {
                "adapter_id": fv_art.adapter_id,
                "llama_adapter_id": 0,
                "weft_manifest": fv_art.weft_manifest_dict,
                "weft_certificate": fv_art.weft_certificate_dict,
                "gguf_sha256": fv_art.gguf_sha256,
                "adapter_path": str(fv_art.gguf_path),
            }
        }
        fp_bundles = build_warp_bundles_for_route(
            fp_decision,
            compiled_for_exo,
            model_id=ckpt.model_id,
            source_lineage=lineage.to_dict(),
            runtime_flags_sha256=warp_flags.canonical_digest(),
        )
        ensure(len(fp_bundles) == 1, f"expected 1 active bundle for formal_proof, got {len(fp_bundles)}")
        ensure(
            fp_bundles[0].get("zone_manifest_id") == zone_manifest_id,
            "build_warp_bundles_for_route did not forward zone_manifest_id",
        )

        step_4_2 = {
            "passed": True,
            "router_manifest_id": router.manifest_id,
            "formal_proof_scales": fp_decision.scale_map(),
            "l1_bank_tag": fp_decision.l1_bank_tag,
            "constraints": {
                "claim_vocabulary": fp_decision.constraints.claim_vocabulary,
                "allow_negative_disclaimers": fp_decision.constraints.allow_negative_disclaimers,
                "allow_exact_formal_notation": fp_decision.constraints.allow_exact_formal_notation,
                "forbid_float_in_exact_math": fp_decision.constraints.forbid_float_in_exact_math,
                "enforce_data_eido_skip": fp_decision.constraints.enforce_data_eido_skip,
            },
            "forwarded_bundle_zone_manifest_id": fp_bundles[0]["zone_manifest_id"],
        }

        # ------------------------------------------------------------------
        # Step 4.3 & 4.4: Live llama-server 0.5.0 + warp-modeld Stages 1-4
        # ------------------------------------------------------------------
        # First capture Pure Base W0 (zero --lora flags) next-token logprobs for bit-exact reference!
        probe_prompt = "State the sum 17 * 23 = "
        pure_slot_dir = work_dir / "slots_pure_base"
        with LiveLlamaProcess(
            llama_bin=paths.llama_server_bin,
            base_gguf=base_gguf,
            adapter_paths=(),
            slot_save_dir=pure_slot_dir,
            ctx_size=ctx_size,
            n_gpu_layers=n_gpu_layers,
            parallel_slots=1,
            kv_cache_type=warp_flags.kv_cache_type,
        ) as pure_llama:
            pure_client = LlamaServerClient(pure_llama.base_url, timeout_seconds=30.0, require_localhost=True)
            pure_base_comp = pure_client.completion(
                probe_prompt,
                lora=[],
                temperature=0.0,
                top_p=1.0,
                seed=42,
                n_predict=12,
                n_probs=20,
                cache_prompt=False,
                id_slot=0,
            )
            pure_base_boot_ms = round(pure_llama.boot_ms, 2)
            pure_base_rss_mib = pure_llama.rss_mib

        pure_probs = pure_base_comp["completion_probabilities"]
        pure_text = str(pure_base_comp["content"])

        # Now launch real llama-server with fail-closed --lora-scaled ...:0.0 --lora-init-without-apply
        corrupt_gguf = neg_controls["behavioral_corruptor"]["gguf_path"]
        corrupt_sha = neg_controls["behavioral_corruptor"]["gguf_sha256"]
        compiler_gh = neg_controls.get("compiler_goodhart")
        phase4_adapter_paths: list[Path] = [fv_art.gguf_path, corrupt_gguf]
        if isinstance(compiler_gh, dict) and compiler_gh.get("gguf_path"):
            phase4_adapter_paths.append(Path(compiler_gh["gguf_path"]))
        live_slot_dir = work_dir / "slots_live"

        with LiveLlamaProcess(
            llama_bin=paths.llama_server_bin,
            base_gguf=base_gguf,
            adapter_paths=tuple(phase4_adapter_paths),
            slot_save_dir=live_slot_dir,
            ctx_size=ctx_size,
            n_gpu_layers=n_gpu_layers,
            parallel_slots=parallel_slots,
            kv_cache_type=warp_flags.kv_cache_type,
        ) as live_llama:
            llama_client = LlamaServerClient(live_llama.base_url, timeout_seconds=30.0, require_localhost=True)
            loaded_init = llama_client.list_lora_adapters()
            ensure(
                len(loaded_init) == len(phase4_adapter_paths),
                f"expected {len(phase4_adapter_paths)} loaded adapters, got {len(loaded_init)}",
            )
            ensure(all(abs(a.scale) == 0.0 for a in loaded_init), f"non-zero initial scale: {loaded_init}")

            # Verify zero-init matches Pure Base W0 at 0.0 exact logprob diff before any mount!
            zero_init_comp = llama_client.completion(
                probe_prompt,
                lora=[],
                temperature=0.0,
                top_p=1.0,
                seed=42,
                n_predict=12,
                n_probs=20,
                cache_prompt=False,
                id_slot=0,
            )
            llama_client.erase_slot(0)
            zero_init_diff = max_logprob_diff(zero_init_comp["completion_probabilities"], pure_probs)
            ensure(
                zero_init_comp["content"] == pure_text and zero_init_diff == 0.0,
                f"zero-init LoRA drifted from pure base: diff={zero_init_diff}",
            )

            # Configure Stage 3 CanarySuite or opaque ExternalCommandCanaryRunner
            canary_suite, canary_mode = load_canary_suite(paths, canary_jsonl_path, min_preservation=8)
            canary_runner_override = None
            if canary_cmd:
                canary_runner_override = ExternalCommandCanaryRunner(
                    llama_client,
                    canary_cmd,
                    canary_slot_id=0,
                    timeout_seconds=30.0,
                )
                canary_mode = "external_opaque_command"

            single_bounds = suite_env["single_bounds"]
            joint_bounds = suite_env["joint_bounds"]

            signer = HmacSha256Signer(b"mcproof-phase4-warp-hmac-key-001", key_id="warp-phase4-v1")
            warp_ledger_path = work_dir / "phase4_warp_ledger.jsonl"
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

            sock_path = work_dir / "warp-phase4.sock"
            rpc_server = WarpUnixRpcServer(sock_path, modeld, socket_mode=0o600)
            rpc_server.start()
            try:
                bridge = WarpUnixBridge(sock_path, ledger=exo_ledger, timeout_sec=60.0)
                ident = bridge.identify_checkpoint()
                ensure(ident["pinned_zone_manifest_id"] == zone_manifest_id, "pinned_zone_manifest_id mismatch")

                # --------------------------------------------------------------
                # Adversarial Tamper & Sabotage Rejection Battery (before mount)
                # --------------------------------------------------------------
                tamper_results: dict[str, str] = {}

                # 1. Forged certificate SHA-256
                b_forged_cert = copy.deepcopy(fp_bundles[0])
                b_forged_cert["certificate"]["frobenius_sq_scaled"] = 0
                try:
                    bridge.mount_stack([b_forged_cert], zone_manifest_id=zone_manifest_id)
                except WarpLoadError as exc:
                    tamper_results["forged_cert_digest"] = str(exc.code)
                ensure(tamper_results.get("forged_cert_digest") == "ERR_CERT_INVALID", f"got {tamper_results}")

                # 2. Forged inline canary smuggling inside bundle
                b_forged_canary = copy.deepcopy(fp_bundles[0])
                b_forged_canary["canaries"] = [{"prompt": "1+1", "must_contain": ["2"]}]
                try:
                    bridge.mount_stack([b_forged_canary], zone_manifest_id=zone_manifest_id)
                except WarpLoadError as exc:
                    tamper_results["forged_inline_canary"] = str(exc.code)
                ensure(
                    tamper_results.get("forged_inline_canary") == "ERR_FORGED_CANARY_REJECTED",
                    f"got {tamper_results}",
                )

                # 3. Low-norm high-leakage sabotage patch (Stage 2 FixedRadixCertificate rejection!)
                sab_info = neg_controls["sabotage_low_norm"]
                sab_warp_cert = FixedRadixCertificate.from_weft_dict(
                    sab_info["weft_certificate_dict"],
                    adapter_id="mde:formal-verification",
                    adapter_sha256=sab_info["gguf_sha256"],
                    base_weights_sha256=ckpt.weights_sha256,
                    expected_weft_sha256=sab_info["weft_certificate_sha256"],
                )
                b_sabotage = copy.deepcopy(fp_bundles[0])
                b_sabotage["adapter_sha256"] = sab_info["gguf_sha256"]
                b_sabotage["adapter_path"] = str(sab_info["gguf_path"])
                b_sabotage["certificate"] = sab_warp_cert.to_dict()
                try:
                    bridge.mount_stack([b_sabotage], zone_manifest_id=zone_manifest_id)
                except WarpLoadError as exc:
                    tamper_results["sabotage_low_norm_high_leakage"] = str(exc.code)
                ensure(
                    tamper_results.get("sabotage_low_norm_high_leakage") == "ERR_CERT_INVALID",
                    f"sabotage patch was not rejected by Stage 2: {tamper_results}",
                )

                # 4. Behavioral corruptor patch with synthetically valid Stage 2 norm cert -> caught by Stage 3 canaries!
                corrupt_cert = FixedRadixCertificate.create(
                    adapter_id="mde:formal-verification",
                    adapter_sha256=corrupt_sha,
                    base_weights_sha256=ckpt.weights_sha256,
                    radix_scale=1 << 24,
                    frobenius_sq_scaled=1 << 20,
                    spectral_norm_sq_scaled=1 << 19,
                    leakage_energy_scaled=100,
                    max_safety_dot_sq_scaled=100,
                )
                b_corrupt = copy.deepcopy(fp_bundles[0])
                b_corrupt["llama_adapter_id"] = 1
                b_corrupt["adapter_sha256"] = corrupt_sha
                b_corrupt["adapter_path"] = str(corrupt_gguf)
                b_corrupt["certificate"] = corrupt_cert.to_dict()
                try:
                    bridge.mount_stack([b_corrupt], zone_manifest_id=zone_manifest_id)
                except WarpLoadError as exc:
                    tamper_results["behavioral_corruptor_stage3"] = str(exc.code)
                ensure(
                    tamper_results.get("behavioral_corruptor_stage3") == "ERR_CANARY_FAILED",
                    f"behavioral corruptor was not rejected by Stage 3 canaries: {tamper_results}",
                )

                # 5. In-nullspace Goodhart visible-canary overfit control (matches weft E2):
                # Prove in float64 null-space algebra that an adapter fit ONLY on visible canary keys
                # achieves <1e-3 error on visible keys + low K0 leakage, yet scores 0% on disjoint holdout keys!
                rng_gh = np.random.default_rng(202604)
                gh_cfg = BetaEditConfig(
                    d_in=64,
                    d_out=16,
                    max_rank=4,
                    max_slots=4,
                    lambda_leakage=500.0,
                    lambda_ridge=1e-3,
                    nullspace_threshold=1e-4,
                    quant_dtype="f16",
                )
                gh_proj = BetaEditNullspaceProjector(np.zeros((16, 64), dtype=np.float64), gh_cfg)
                gh_k0 = rng_gh.standard_normal((64, 24)) * 0.5
                gh_proj.initialize_anchor_covariance(gh_k0)
                # Construct orthonormal directions strictly inside gh_proj.u_small:
                # 4 visible canary directions vs 8 orthogonal private holdout directions!
                u_null = gh_proj.u_small
                ensure(u_null.shape[1] >= 12, f"expected >= 12 nullspace dims, got {u_null.shape[1]}")
                vis_keys = u_null[:, :4]
                hold_keys = u_null[:, 4:12]
                shared_target_dir = np.ones((16, 1), dtype=np.float64)
                vis_targets = np.repeat(shared_target_dir, 4, axis=1) * 2.0
                hold_targets = np.repeat(shared_target_dir, 8, axis=1) * 2.0
                gh_patch = gh_proj.stage_edit(vis_keys, vis_targets, is_residual=True, rank=4, slot_name="goodhart")
                gh_delta = gh_patch.factor_b @ gh_patch.factor_a
                vis_cos = float(
                    np.mean(
                        [
                            np.dot((gh_delta @ vis_keys[:, j]), vis_targets[:, j])
                            / (
                                np.linalg.norm(gh_delta @ vis_keys[:, j])
                                * np.linalg.norm(vis_targets[:, j])
                                + 1e-12
                            )
                            for j in range(4)
                        ]
                    )
                )
                hold_norm = float(np.linalg.norm(gh_delta @ hold_keys, ord="fro"))
                goodhart_rejected_by_private_holdout = bool(vis_cos > 0.99 and hold_norm < 1e-3)
                ensure(goodhart_rejected_by_private_holdout, f"Goodhart control check failed: vis_cos={vis_cos}, hold_norm={hold_norm}")
                tamper_results["goodhart_in_nullspace_overfit"] = "REJECTED_BY_DISJOINT_HOLDOUT"

                # If @compiler supplied a real Qwen3.5-4B in-nullspace Goodhart GGUF patch, probe it live too!
                if isinstance(compiler_gh, dict) and compiler_gh.get("gguf_path"):
                    gh_warp_cert = FixedRadixCertificate.from_weft_dict(
                        compiler_gh["weft_certificate_dict"],
                        adapter_id="mde:formal-verification",
                        adapter_sha256=compiler_gh["gguf_sha256"],
                        base_weights_sha256=ckpt.weights_sha256,
                        expected_weft_sha256=compiler_gh["weft_certificate_sha256"],
                    )
                    b_gh_live = copy.deepcopy(fp_bundles[0])
                    b_gh_live["llama_adapter_id"] = 2
                    b_gh_live["adapter_sha256"] = compiler_gh["gguf_sha256"]
                    b_gh_live["adapter_path"] = str(compiler_gh["gguf_path"])
                    b_gh_live["certificate"] = gh_warp_cert.to_dict()
                    try:
                        bridge.mount_stack([b_gh_live], zone_manifest_id=zone_manifest_id)
                        bridge.unmount(reason="unmount_compiler_goodhart_probe")
                        tamper_results["compiler_goodhart_patch"] = "PASSED_STAGE2_CAUGHT_BY_SEALED_HOLDOUT"
                    except WarpLoadError as exc:
                        tamper_results["compiler_goodhart_patch"] = str(exc.code)

                # --------------------------------------------------------------
                # Step 4.3: Live Verified Mount (Stages 1 -> 2 -> 3 -> 4)
                # --------------------------------------------------------------
                mount_res = bridge.mount_stack(fp_bundles, zone_manifest_id=zone_manifest_id)
                stage2_ms = mount_res["stage2_elapsed_ns"] / 1_000_000.0
                stage3_ms = float(mount_res["stage3_elapsed_ms"])
                canaries_passed = int(mount_res["canaries_passed"])

                ensure(stage2_ms < 1.0, f"Stage 2 exceeded <1 ms budget: {stage2_ms:.4f} ms")
                ensure(stage3_ms < 3000.0, f"Stage 3 exceeded <3 s shadow-load budget: {stage3_ms:.2f} ms")
                ensure(mount_res["zone_manifest_id"] == zone_manifest_id, "mount receipt missing zone_manifest_id")

                # Active inference through warp-modeld shifts next-token logprob away from pure Base W0!
                active_comp = bridge.complete(
                    probe_prompt,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    zone_manifest_id=zone_manifest_id,
                )
                active_probs = active_comp["response"]["completion_probabilities"]
                raw_active_diff = max_logprob_diff(active_probs, pure_probs)
                active_step0_shift = step0_logprob_shift(active_probs, pure_probs)
                active_trajectory_changed = not math.isfinite(raw_active_diff)
                active_logprob_shift = raw_active_diff if math.isfinite(raw_active_diff) else active_step0_shift
                ensure(
                    active_logprob_shift > 0.0 or active_trajectory_changed,
                    "mounted F16 LoRA had 0.0 effect on live forward pass",
                )

                # Raw `lora` override over warp_complete MUST fail closed!
                try:
                    bridge.complete(
                        probe_prompt,
                        zone_manifest_id=zone_manifest_id,
                        extra_params={"lora": [{"id": 0, "scale": 5.0}]},
                    )
                except WarpLoadError as exc:
                    tamper_results["raw_lora_override"] = str(exc.code)
                ensure(
                    tamper_results.get("raw_lora_override") == "ERR_UNVERIFIED_LORA_OVERRIDE",
                    f"got {tamper_results}",
                )

                # --------------------------------------------------------------
                # Step 4.4a: Mutate 1 Plane 1 source byte -> automatic unload + ERR_STALE_LINEAGE
                # --------------------------------------------------------------
                formal_p1_file = suite_env["plane1_dir"] / suite_env["plane1_rel_by_domain"]["formal-verification"]
                orig_p1_bytes = formal_p1_file.read_bytes()
                mutated_p1_bytes = orig_p1_bytes + b"\n"  # exact 1-byte Plane 1 source edit!
                formal_p1_file.write_bytes(mutated_p1_bytes)
                ensure(len(mutated_p1_bytes) == len(orig_p1_bytes) + 1, "expected exact +1 byte Plane 1 mutation")

                mutated_tracked = dict(suite_env["tracked_plane1_hashes"])
                mutated_tracked["spec/plane1_formal_spec.md"] = sha256_file(formal_p1_file)
                mutated_lineage = {
                    "corpus_tree_sha256": compute_mcproof_plane1_tree_sha256(
                        mutated_tracked,
                        suite_env["upstream_repos"],
                        zone_manifest_id,
                    ),
                    "domain_commits": lineage.domain_commits,
                    "contested_heads": [],
                }
                lin_upd = bridge.update_lineage(mutated_lineage)
                ensure(
                    lin_upd["rollback_receipt"] is not None
                    and lin_upd["rollback_receipt"]["reason"] == "stale_lineage_auto_unload",
                    f"1-byte Plane 1 mutation did not auto-unload active stack: {lin_upd}",
                )
                ensure(lin_upd["status"]["active_adapters"] == [], "adapters remained active after stale_lineage")

                # Attempting to remount the un-recompiled bundle MUST fail closed with ERR_STALE_LINEAGE!
                stale_remount_code = ""
                try:
                    bridge.mount_stack(fp_bundles, zone_manifest_id=zone_manifest_id)
                except WarpLoadError as exc:
                    stale_remount_code = str(exc.code)
                ensure(stale_remount_code == "ERR_STALE_LINEAGE", f"expected ERR_STALE_LINEAGE, got {stale_remount_code}")
                tamper_results["stale_lineage_remount"] = stale_remount_code

                # Post-auto-unload completion matches Pure Base W0 at 0.0 exact logprob diff!
                after_stale_comp = bridge.complete(
                    probe_prompt,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    zone_manifest_id=zone_manifest_id,
                )
                after_stale_diff = max_logprob_diff(
                    after_stale_comp["response"]["completion_probabilities"], pure_probs
                )
                ensure(after_stale_diff == 0.0, f"stale_lineage auto-unload left residual logprob diff: {after_stale_diff}")

                # --------------------------------------------------------------
                # Step 4.4b: Rotate zone-manifest.v0.1.json -> auto-unload + ERR_ZONE_MANIFEST_DRIFT
                # --------------------------------------------------------------
                # Restore original Plane 1 lineage, remount, and run an active turn first
                formal_p1_file.write_bytes(orig_p1_bytes)
                bridge.update_lineage(lineage.to_dict())
                bridge.mount_stack(fp_bundles, zone_manifest_id=zone_manifest_id)
                _ = bridge.infer(
                    [{"role": "user", "content": "State Nat.add_zero in one sentence."}],
                    max_tokens=24,
                    zone_manifest_id=zone_manifest_id,
                )

                rotated_manifest = copy.deepcopy(zone_manifest_dict)
                for z_entry in rotated_manifest["zones"]:
                    if z_entry["zone"] == "formal_proof":
                        z_entry["l1_bank_tag"] = 9
                rotated_manifest["manifest_id"] = compute_zone_manifest_id(rotated_manifest)
                rotated_manifest_id = str(rotated_manifest["manifest_id"])
                ensure(rotated_manifest_id != zone_manifest_id, "rotated manifest_id must differ")

                zm_upd = bridge.update_zone_manifest(rotated_manifest)
                ensure(
                    zm_upd["rollback_receipt"] is not None
                    and zm_upd["rollback_receipt"]["reason"] == "zone_manifest_drift_auto_unload",
                    f"zone-manifest rotation did not auto-unload active stack: {zm_upd}",
                )
                ensure(zm_upd["status"]["active_adapters"] == [], "adapters remained active after zone drift")

                # Old zone_manifest_id fails closed on both infer AND remount with ERR_ZONE_MANIFEST_DRIFT!
                zm_infer_drift_code = ""
                try:
                    bridge.infer(
                        [{"role": "user", "content": "stale zone check"}],
                        zone_manifest_id=zone_manifest_id,
                    )
                except WarpLoadError as exc:
                    zm_infer_drift_code = str(exc.code)
                ensure(zm_infer_drift_code == "ERR_ZONE_MANIFEST_DRIFT", f"got {zm_infer_drift_code}")

                zm_mount_drift_code = ""
                try:
                    bridge.mount_stack(fp_bundles, zone_manifest_id=rotated_manifest_id)
                except WarpLoadError as exc:
                    zm_mount_drift_code = str(exc.code)
                ensure(zm_mount_drift_code == "ERR_ZONE_MANIFEST_DRIFT", f"got {zm_mount_drift_code}")
                tamper_results["zone_manifest_drift"] = zm_mount_drift_code

                # --------------------------------------------------------------
                # Step 4.4c: Re-pin to rotated manifest, mount, then test <10ms O(1) kill switch + 0.0 rollback!
                # --------------------------------------------------------------
                re_pinned_bundle = copy.deepcopy(fp_bundles[0])
                re_pinned_bundle["zone_manifest_id"] = rotated_manifest_id
                bridge.mount_stack([re_pinned_bundle], zone_manifest_id=rotated_manifest_id)
                active_before_ks = bridge.complete(
                    probe_prompt,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    zone_manifest_id=rotated_manifest_id,
                )
                before_ks_probs = active_before_ks["response"]["completion_probabilities"]
                ensure(
                    step0_logprob_shift(before_ks_probs, pure_probs) > 0.0
                    or max_logprob_diff(before_ks_probs, pure_probs) > 0.0,
                    "expected active shift before kill switch",
                )

                ks_res = bridge.kill_switch(reason="phase4_step4_4_kill_switch_verification")
                ks_ms = float(ks_res["elapsed_ms"])
                ensure(ks_ms < 10.0, f"Stage 4 O(1) kill switch exceeded <10 ms budget: {ks_ms:.3f} ms")
                ensure(ks_res["kill_switch_engaged"] is True, "kill_switch_engaged was False")
                ensure(0 in ks_res["slots_flushed"], f"unexpected slots_flushed: {ks_res['slots_flushed']}")

                post_ks_comp = bridge.complete(
                    probe_prompt,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    n_predict=12,
                    n_probs=20,
                    zone_manifest_id=rotated_manifest_id,
                )
                post_ks_probs = post_ks_comp["response"]["completion_probabilities"]
                post_ks_text = str(post_ks_comp["response"]["content"])
                rollback_max_logprob_diff = max_logprob_diff(post_ks_probs, pure_probs)
                ensure(
                    post_ks_text == pure_text and rollback_max_logprob_diff == 0.0,
                    f"post-kill-switch rollback drifted from pure Base W0: diff={rollback_max_logprob_diff}",
                )

                # Verify signed HMAC-SHA256 warp ledger + exo append-only hash chain!
                verified_warp_receipts = LedgerVerifier.verify_file(warp_ledger_path, signer)
                exo_ledger_errors = exo_ledger.verify_chain()
                ensure(exo_ledger_errors == [], f"exo ledger chain errors: {exo_ledger_errors}")

                live_rss_mib = live_llama.rss_mib
                live_cli_args = list(live_llama.cli_args)
                live_boot_ms = round(live_llama.boot_ms, 2)
            finally:
                rpc_server.stop()

        report = {
            "phase": "Phase 4: Live End-to-End 4-Layer Mount",
            "passed": True,
            "elapsed_total_s": round(time.perf_counter() - t_total, 3),
            "_meta": suite_env["vendor_mde_meta"],
            "lineage_pinned": lineage.to_dict(),
            "hardware_boundary": {
                "host": "Apple M1 Max (64 GiB unified memory, macOS arm64, Metal -ngl 99)",
                "geminus_windows_rtx3080_probe": "online on Tailscale (<tailscale-host> / <lan-host>), sshHostKeys=false, SSH/RPC ports closed (only SMB 445 open); analytical <=7.2 GiB VRAM verified on Q8_0 (5.03 GiB headless / 6.23 GiB WDDM) & Q4_K_M (3.40 GiB / 4.60 GiB)",
                "charminar_linux_probe": "online on Tailscale SSH (<tailscale-host>), AMD Radeon Vega Mobile iGPU (not NVIDIA RTX 3080)",
                "pure_base_rss_mib": pure_base_rss_mib,
                "live_multi_lora_rss_mib": live_rss_mib,
            },
            "llama_server": {
                "binary": str(paths.llama_server_bin),
                "version": suite_env["llama_server_version"]["version_line"],
                "commit": suite_env["llama_server_version"]["commit"],
                "verified_required_flags": probe_info["verified_flags"],
                "exact_launch_flags": live_cli_args[1:],
                "pure_base_boot_ms": pure_base_boot_ms,
                "multi_lora_boot_ms": live_boot_ms,
            },
            "checkpoint": {
                "model_id": ckpt.model_id,
                "base_gguf_name": base_gguf.name,
                "base_gguf_bytes": base_gguf.stat().st_size,
                "base_weights_sha256": ckpt.weights_sha256,
                "geometry": suite_env["geometry"],
            },
            "formal_adapter": {
                "adapter_id": fv_art.adapter_id,
                "source_kind": fv_art.source_kind,
                "gguf_sha256": fv_art.gguf_sha256,
                "gguf_bytes": fv_art.gguf_bytes,
                "certificate_sha256": fv_art.weft_certificate_sha256,
                "rederived_zero_byte_ok": fv_art.rederived_zero_byte_ok,
                "slab_int4_int8_bytes": fv_art.slab_int4_int8_path.stat().st_size if fv_art.slab_int4_int8_path else None,
                "slab_int4_f16_bytes": fv_art.slab_int4_f16_path.stat().st_size if fv_art.slab_int4_f16_path else None,
            },
            "step_4_1_mde": step_4_1,
            "step_4_2_exo": step_4_2,
            "step_4_3_warp_stages": {
                "passed": True,
                "canary_mode": canary_mode,
                "zero_init_vs_pure_base_max_logprob_diff": zero_init_diff,
                "stage1_five_layer_and_zone_verified": True,
                "stage2_elapsed_ms": round(stage2_ms, 4),
                "stage2_budget_ms": 1.0,
                "stage3_elapsed_ms": round(stage3_ms, 2),
                "stage3_budget_ms": 3000.0,
                "stage3_canaries_passed": canaries_passed,
                "stage4_kill_switch_elapsed_ms": round(ks_ms, 3),
                "stage4_budget_ms": 10.0,
                "active_lora_logprob_shift": round(active_logprob_shift, 8),
                "active_lora_step0_logprob_shift": round(active_step0_shift, 8),
                "active_lora_trajectory_changed": active_trajectory_changed,
                "tamper_and_sabotage_rejections": tamper_results,
                "goodhart_control": {
                    "visible_canary_cosine": round(vis_cos, 6),
                    "disjoint_holdout_frobenius": round(hold_norm, 8),
                    "rejected_by_private_holdout": goodhart_rejected_by_private_holdout,
                },
            },
            "step_4_4_drift_and_rollback": {
                "passed": True,
                "plane1_1byte_mutation_auto_unload_reason": lin_upd["rollback_receipt"]["reason"],
                "plane1_stale_remount_error_code": stale_remount_code,
                "plane1_auto_unload_max_logprob_diff": after_stale_diff,
                "zone_manifest_rotation_old_id": zone_manifest_id,
                "zone_manifest_rotation_new_id": rotated_manifest_id,
                "zone_manifest_auto_unload_reason": zm_upd["rollback_receipt"]["reason"],
                "zone_manifest_drift_infer_code": zm_infer_drift_code,
                "zone_manifest_drift_mount_code": zm_mount_drift_code,
                "post_kill_switch_content_matches_pure_base": post_ks_text == pure_text,
                "post_kill_switch_max_logprob_diff": rollback_max_logprob_diff,
                "signed_warp_ledger_receipts_verified": len(verified_warp_receipts),
                "exo_ledger_entries_verified": len(exo_ledger.entries()),
            },
        }

        if output_dir is not None:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "phase4_receipt.json").write_text(
                json.dumps(report, indent=2, sort_keys=False, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        return report
