"""Automated dependency-free unit tests and optional live tests for mcproof_stack."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any
import unittest
import unittest.mock

_STACK_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_STACK_SRC) not in sys.path:
    sys.path.insert(0, str(_STACK_SRC))

import numpy as np  # noqa: E402

from mcproof_stack.cli import build_parser  # noqa: E402
from mcproof_stack.phase4_mount import (  # noqa: E402
    record_live_rejection,
    run_phase4_live_mount,
    summarize_live_rejections,
    verify_step_4_1_mde_zones_and_code_audit,
)
from mcproof_stack.phase6_composition import (  # noqa: E402
    compute_analytical_vram_projection_gib,
    compute_latency_overhead_metrics,
    compute_live_step0_retention_pct,
    compute_shared_subspace_diagnostic,
    extract_verified_slot_n_ctx,
    parse_and_validate_grader_process,
    reconcile_mixed_grader_result,
    run_phase6_composition,
    single_mode_retention_exit_ok,
)
from mcproof_stack.runtime import (  # noqa: E402
    GGUF_MAGIC,
    GGUF_VERSION,
    StackPaths,
    resolve_siliconcordat_root,
    build_canary_command,
    build_checkpoint_and_weft_suite,
    compute_mcproof_plane1_tree_sha256,
    cross_check_supplied_runtime_flags,
    load_canary_suite,
    max_logprob_diff,
    parse_gguf_quantization,
    parse_llama_server_version_output,
    read_gguf_header_metadata,
    sha256_file,
    step0_logprob_shift,
    verify_rederivation_receipt,
    verify_supplied_checkpoint_against_served_gguf,
)


def _pack_gguf_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _build_minimal_gguf_header_bytes(meta: dict[str, Any]) -> bytes:
    """Build a minimal valid GGUF v3 header (0 tensors) for unit-testing metadata parsing."""
    kv_chunks: list[bytes] = []
    for key, val in sorted(meta.items()):
        prefix = _pack_gguf_str(key)
        if type(val) is bool:
            kv_chunks.append(prefix + struct.pack("<I?", 7, val))
        elif type(val) is int:
            kv_chunks.append(prefix + struct.pack("<II", 4, val))
        elif isinstance(val, str):
            kv_chunks.append(prefix + struct.pack("<I", 8) + _pack_gguf_str(val))
        else:
            raise TypeError(f"unsupported test metadata value: {val!r}")
    header = struct.pack("<4sIQQ", GGUF_MAGIC, GGUF_VERSION, 0, len(kv_chunks))
    return header + b"".join(kv_chunks)


def _discover_lab_paths_or_skip(tc: unittest.TestCase) -> StackPaths:
    try:
        paths = StackPaths.discover()
        paths.inject_sys_path()
        import exo  # noqa: F401
        import warp_modeld  # noqa: F401
        import weft  # noqa: F401
    except (RuntimeError, ImportError, FileNotFoundError) as exc:
        tc.skipTest(f"lab host prerequisite unavailable in isolated environment: {exc}")
    return paths


@dataclass(frozen=True)
class _FakeCkpt:
    weights_sha256: str
    layout_sha256: str
    has_ssm_recurrent: bool = True


@dataclass(frozen=True)
class _FakeStIdent:
    fingerprint: str
    layout_sha256: str


@dataclass(frozen=True)
class _FakeFlags:
    llama_server_commit: str
    quantization: str
    ctx_size: int
    kv_cache_type: str
    lora_init_without_apply: bool


class TestSiliconcordatRootResolution(unittest.TestCase):
    """Flat-clone and mcproof-lab layouts must resolve `siliconcordat` without `SILICONCORDAT_ROOT`."""

    def test_flat_clone_resolves_sibling_under_lab_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcproof_flat_") as td:
            lab = Path(td) / "workspace"
            lab.mkdir()
            (lab / "siliconcordat").mkdir()
            with unittest.mock.patch.dict(os.environ, {}, clear=True):
                resolved = resolve_siliconcordat_root(lab)
            self.assertEqual(resolved, (lab / "siliconcordat").resolve())

    def test_mcproof_lab_layout_resolves_parent_sibling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcproof_lab_") as td:
            work = Path(td) / "work"
            lab = work / "mcproof-lab"
            lab.mkdir(parents=True)
            (work / "siliconcordat").mkdir()
            with unittest.mock.patch.dict(os.environ, {}, clear=True):
                resolved = resolve_siliconcordat_root(lab)
            self.assertEqual(resolved, (work / "siliconcordat").resolve())

    def test_env_override_wins(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcproof_env_sc_") as td:
            custom = Path(td) / "custom-siliconcordat"
            custom.mkdir()
            lab = Path(td) / "lab"
            lab.mkdir()
            (lab / "siliconcordat").mkdir()
            with unittest.mock.patch.dict(os.environ, {"SILICONCORDAT_ROOT": str(custom)}, clear=True):
                resolved = resolve_siliconcordat_root(lab)
            self.assertEqual(resolved, custom.resolve())


class TestPureStackHelpers(unittest.TestCase):
    """Dependency-free (`pytest` + `numpy` only) unit coverage for all stack gates and helpers."""

    def test_max_logprob_diff_exact_and_mismatches(self) -> None:
        probs_a = [
            {
                "id": 11,
                "logprob": -0.125,
                "top_logprobs": [
                    {"id": 11, "logprob": -0.125},
                    {"id": 42, "logprob": -2.5},
                    {"id": 99, "logprob": -4.0},
                ],
            }
        ]
        # Permuted top_logprobs order with identical token IDs and values -> exact 0.0
        probs_b_same = [
            {
                "id": 11,
                "logprob": -0.125,
                "top_logprobs": [
                    {"id": 99, "logprob": -4.0},
                    {"id": 11, "logprob": -0.125},
                    {"id": 42, "logprob": -2.5},
                ],
            }
        ]
        self.assertEqual(max_logprob_diff(probs_a, probs_b_same), 0.0)

        # Token-ID dict lookup catches delta even when order differs
        probs_b_shifted = [
            {
                "id": 11,
                "logprob": -0.125,
                "top_logprobs": [
                    {"id": 99, "logprob": -3.75},
                    {"id": 11, "logprob": -0.125},
                    {"id": 42, "logprob": -2.5},
                ],
            }
        ]
        self.assertAlmostEqual(max_logprob_diff(probs_a, probs_b_shifted), 0.25, places=9)

        # Top-k length mismatch -> inf
        probs_len_mismatch = [
            {
                "id": 11,
                "logprob": -0.125,
                "top_logprobs": [
                    {"id": 11, "logprob": -0.125},
                    {"id": 42, "logprob": -2.5},
                ],
            }
        ]
        self.assertTrue(math.isinf(max_logprob_diff(probs_a, probs_len_mismatch)))

        # Top-k token-ID set mismatch -> inf
        probs_id_set_mismatch = [
            {
                "id": 11,
                "logprob": -0.125,
                "top_logprobs": [
                    {"id": 11, "logprob": -0.125},
                    {"id": 42, "logprob": -2.5},
                    {"id": 777, "logprob": -4.0},
                ],
            }
        ]
        self.assertTrue(math.isinf(max_logprob_diff(probs_a, probs_id_set_mismatch)))

        # Missing top_logprobs -> inf
        probs_missing_top = [{"id": 11, "logprob": -0.125, "top_logprobs": []}]
        self.assertTrue(math.isinf(max_logprob_diff(probs_a, probs_missing_top)))

        # Empty probability lists -> ValueError
        with self.assertRaises(ValueError):
            max_logprob_diff([], probs_a)
        with self.assertRaises(ValueError):
            max_logprob_diff(probs_a, [])

    def test_step0_logprob_shift_rejects_empty_and_computes_shift(self) -> None:
        valid_a = [
            {
                "id": 10,
                "logprob": -0.05,
                "top_logprobs": [{"id": 10, "logprob": -0.05}, {"id": 22, "logprob": -3.2}],
            }
        ]
        valid_b = [
            {
                "id": 22,
                "logprob": -0.10,
                "top_logprobs": [{"id": 22, "logprob": -0.10}],
            }
        ]
        with self.assertRaises(ValueError):
            step0_logprob_shift([], valid_b)
        with self.assertRaises(ValueError):
            step0_logprob_shift(valid_a, [])
        with self.assertRaises(ValueError):
            step0_logprob_shift([{"id": 10, "logprob": -0.05, "top_logprobs": []}], valid_b)
        with self.assertRaises(ValueError):
            step0_logprob_shift([{"id": 10, "logprob": -0.05}], valid_b)

        shift = step0_logprob_shift(valid_a, valid_b)
        self.assertAlmostEqual(shift, 3.1, places=9)
        self.assertEqual(step0_logprob_shift(valid_a, valid_a), 0.0)

    def test_external_grader_exit_code_and_max_corruption_reconciliation(self) -> None:
        # Clean exit 0 + 0 internal + 0 external -> pass
        res_clean = reconcile_mixed_grader_result(
            internal_formal_corruptions=0,
            internal_prose_leaks=0,
            returncode=0,
            stdout=json.dumps(
                {
                    "corrupted_formal_blocks": 0,
                    "prose_or_zone_leaks": 0,
                    "phase6_tc2_isolation_gate": True,
                }
            ),
        )
        self.assertTrue(res_clean["passed"])
        self.assertEqual(res_clean["formal_block_corruptions"], 0)
        self.assertEqual(res_clean["prose_rule_leaks"], 0)

        # Exit code 1 claiming 0 corruptions MUST still fail the gate
        res_rc1 = reconcile_mixed_grader_result(
            internal_formal_corruptions=0,
            internal_prose_leaks=0,
            returncode=1,
            stdout=json.dumps({"corrupted_formal_blocks": 0, "prose_or_zone_leaks": 0}),
        )
        self.assertFalse(res_rc1["passed"])

        # Authoritative internal detection: external JSON 0s cannot zero out internal counts!
        res_internal_kept = reconcile_mixed_grader_result(
            internal_formal_corruptions=2,
            internal_prose_leaks=1,
            returncode=0,
            stdout=json.dumps({"corrupted_formal_blocks": 0, "prose_or_zone_leaks": 0}),
        )
        self.assertFalse(res_internal_kept["passed"])
        self.assertEqual(res_internal_kept["formal_block_corruptions"], 2)
        self.assertEqual(res_internal_kept["prose_rule_leaks"], 1)

        # Single-mode retention: exit 1 with plausible counts is still a failed gate.
        single_stdout = json.dumps({"total_count": 4, "total_passed": 4, "accuracy_pct": 100.0})
        single_ok, single_payload = parse_and_validate_grader_process(
            1,
            single_stdout,
            "",
            grader_name="retention_grader",
            required_int_keys=("total_count",),
            any_of_int_keys=(("total_passed", "passed_count", "correct"),),
        )
        self.assertFalse(single_ok)
        self.assertEqual(single_payload["total_passed"], 4)
        self.assertFalse(single_mode_retention_exit_ok(single_ok, True, True))
        self.assertTrue(single_mode_retention_exit_ok(True, True, True))
        holdout_ok, _holdout_payload = parse_and_validate_grader_process(
            1,
            json.dumps({"total_count": 4, "total_passed": 3}),
            "",
            grader_name="holdout_grader",
            required_int_keys=("total_count",),
            any_of_int_keys=(("total_passed", "passed_count", "overall_passed"),),
        )
        self.assertFalse(holdout_ok)

        # Crash exit code (2) or invalid JSON schema raises RuntimeError
        with self.assertRaises(RuntimeError):
            parse_and_validate_grader_process(2, "{}", "boom", grader_name="test_grader")
        with self.assertRaises(RuntimeError):
            parse_and_validate_grader_process(0, "not-json", "", grader_name="test_grader")
        with self.assertRaises(RuntimeError):
            reconcile_mixed_grader_result(
                internal_formal_corruptions=0,
                internal_prose_leaks=0,
                returncode=0,
                stdout=json.dumps({"unexpected_schema": True}),
            )

    def test_gguf_file_type_quantization_and_ssm_parsing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcproof_gguf_hdr_") as td:
            tmp = Path(td)
            # File named Q4_K_M on disk, but header general.file_type == 7 (Q8_0) -> must report Q8_0!
            q8_path = tmp / "misleading-Q4_K_M-name.gguf"
            q8_path.write_bytes(
                _build_minimal_gguf_header_bytes(
                    {
                        "general.architecture": "qwen35",
                        "general.file_type": 7,
                        "qwen35.ssm.state_size": 128,
                    }
                )
            )
            meta_q8 = read_gguf_header_metadata(q8_path)
            self.assertEqual(parse_gguf_quantization(q8_path), "Q8_0")
            self.assertTrue(meta_q8["has_ssm"])

            f16_path = tmp / "adapter_or_base.gguf"
            f16_path.write_bytes(
                _build_minimal_gguf_header_bytes(
                    {
                        "general.architecture": "llama",
                        "general.file_type": 1,
                    }
                )
            )
            meta_f16 = read_gguf_header_metadata(f16_path)
            self.assertEqual(parse_gguf_quantization(meta_f16), "F16")
            self.assertFalse(meta_f16["has_ssm"])

            q4_path = tmp / "companion.gguf"
            q4_path.write_bytes(
                _build_minimal_gguf_header_bytes(
                    {
                        "general.architecture": "qwen35",
                        "general.file_type": 15,
                    }
                )
            )
            self.assertEqual(parse_gguf_quantization(q4_path), "Q4_K_M")

            # Unknown or missing file_type fails closed (never guesses from filename)
            unknown_path = tmp / "Qwen3.5-4B-Q8_0.gguf"
            unknown_path.write_bytes(
                _build_minimal_gguf_header_bytes({"general.architecture": "qwen35", "general.file_type": 999})
            )
            with self.assertRaises(ValueError):
                parse_gguf_quantization(unknown_path)
            with self.assertRaises(ValueError):
                parse_gguf_quantization({"general.architecture": "qwen35"})
            with self.assertRaises(ValueError):
                parse_gguf_quantization({"general.file_type": True})

    def test_llama_version_parser_fails_closed_without_commit(self) -> None:
        parsed = parse_llama_server_version_output("version: 0.5.0 (build 11146, commit 7fe450e19)\n")
        self.assertEqual(parsed["commit"], "7fe450e19")
        with self.assertRaises(RuntimeError):
            parse_llama_server_version_output("version: 0.5.0 (custom local build without hash)\n")
        with self.assertRaises(RuntimeError):
            parse_llama_server_version_output("")

    def test_tc1_live_retention_and_disjoint_tensors_diagnostic(self) -> None:
        # weft-eido live drift (~0.0611) >> solo shift (~0.0019) -> 0.0% live retention (fails >=90% gate)
        ret_eido = compute_live_step0_retention_pct(solo_shift=0.00192213, drift_from_solo=0.06107306)
        self.assertEqual(ret_eido, 0.0)
        self.assertLess(ret_eido, 90.0)

        ret_exact = compute_live_step0_retention_pct(solo_shift=0.1797455, drift_from_solo=0.0)
        self.assertEqual(ret_exact, 100.0)

        # Disjoint tensors return None + "not_applicable_disjoint_tensors", never hardcoded 100.0
        disjoint = compute_shared_subspace_diagnostic(
            {"blk.30.ffn_up.weight": (np.ones((4, 2)), np.ones((2, 4)))},
            {"blk.31.ffn_up.weight": (np.ones((4, 2)), np.ones((2, 4)))},
        )
        self.assertEqual(disjoint["status"], "not_applicable_disjoint_tensors")
        self.assertIsNone(disjoint["weft_eido_pct"])
        self.assertIsNone(disjoint["formal_verification_pct"])

    def test_tc5_negative_overhead_anomaly_and_slots_n_ctx_gate(self) -> None:
        # Stack 26% faster than base -> signed -26.11%, benchmark_anomaly=True, gate fails!
        anom = compute_latency_overhead_metrics([27.92, 27.90, 27.95], [35.21, 35.18, 35.25])
        self.assertAlmostEqual(anom["latency_overhead_pct"], -26.11, places=2)
        self.assertTrue(anom["benchmark_anomaly"])
        self.assertFalse(anom["overhead_gate_passed"])

        # Mild negative measurement noise (-2.0% >= -5.0%) -> reported signed, no anomaly, passes
        mild_neg = compute_latency_overhead_metrics([35.0, 35.0, 35.0], [35.7, 35.7, 35.7])
        self.assertAlmostEqual(mild_neg["latency_overhead_pct"], -2.0, places=2)
        self.assertFalse(mild_neg["benchmark_anomaly"])
        self.assertTrue(mild_neg["overhead_gate_passed"])

        # Excessive positive overhead (20% > 15%) -> fails gate
        slow = compute_latency_overhead_metrics([35.0, 35.0, 35.0], [28.0, 28.0, 28.0])
        self.assertAlmostEqual(slow["latency_overhead_pct"], 20.0, places=2)
        self.assertFalse(slow["benchmark_anomaly"])
        self.assertFalse(slow["overhead_gate_passed"])

        # /slots n_ctx extraction requires explicit integer n_ctx in raw_slots[0]
        self.assertIsNone(extract_verified_slot_n_ctx([]))
        self.assertIsNone(extract_verified_slot_n_ctx([{"id": 0, "is_processing": False}]))
        self.assertIsNone(extract_verified_slot_n_ctx([{"id": 0, "n_ctx": True}]))
        self.assertEqual(extract_verified_slot_n_ctx([{"id": 0, "n_ctx": 8192}]), 8192)

        with tempfile.TemporaryDirectory(prefix="mcproof_vram_cfg_") as td:
            cfg_p = Path(td) / "config.json"
            cfg_p.write_text(
                json.dumps(
                    {
                        "text_config": {
                            "layer_types": ["linear_attention"] * 24 + ["full_attention"] * 8,
                            "num_key_value_heads": 4,
                            "head_dim": 256,
                            "intermediate_size": 9216,
                        }
                    }
                ),
                encoding="utf-8",
            )
            proj = compute_analytical_vram_projection_gib(
                base_gguf_bytes=4_482_403_488,
                lora_total_bytes=567_776,
                kv_ctx_tokens=8192,
                kv_cache_type="f16",
                geometry={"block_count": 32, "feed_forward_length": 9216},
                config_json_path=cfg_p,
            )
            self.assertEqual(proj["vram_measurement_kind"], "analytical_projection_not_nvml")
            self.assertEqual(proj["layer_count_source"], "config.json")
            self.assertEqual(proj["full_attention_layers"], 8)
            self.assertEqual(proj["linear_attention_ssm_layers"], 24)
            self.assertIsNone(proj["companion_q4_k_m_headless_projection_gib"])

    def test_checkpoint_flags_and_rederivation_verification(self) -> None:
        st_sha = "1" * 64
        gguf_sha = "2" * 64
        other_sha = "3" * 64
        layout_sha = "4" * 64
        ckpt = _FakeCkpt(weights_sha256=st_sha, layout_sha256=layout_sha, has_ssm_recurrent=True)

        with tempfile.TemporaryDirectory(prefix="mcproof_ckpt_bind_") as td:
            tmp = Path(td)
            st_dir = tmp / "st"
            st_dir.mkdir()
            p2_report = tmp / "phase2_hardware_checkpoint_report.json"
            p2_report.write_text(
                json.dumps(
                    {
                        "pinned_checkpoint": {
                            "gguf_sha256": gguf_sha,
                            "safetensors_identity": {"fingerprint": st_sha, "layout_sha256": layout_sha},
                        }
                    }
                ),
                encoding="utf-8",
            )

            verify_supplied_checkpoint_against_served_gguf(
                ckpt,
                served_gguf_sha256=gguf_sha,
                live_quantization="Q8_0",
                live_has_ssm=True,
                safetensors_dir=st_dir,
                phase2_report_path=p2_report,
                identify_checkpoint_fn=lambda _d, full=True: _FakeStIdent(fingerprint=st_sha, layout_sha256=layout_sha),
            )

            # Unverified GGUF sha fails closed!
            with self.assertRaises(RuntimeError):
                verify_supplied_checkpoint_against_served_gguf(
                    ckpt,
                    served_gguf_sha256=other_sha,
                    live_quantization="Q8_0",
                    live_has_ssm=True,
                    safetensors_dir=st_dir,
                    phase2_report_path=p2_report,
                    identify_checkpoint_fn=lambda _d, full=True: _FakeStIdent(
                        fingerprint=st_sha, layout_sha256=layout_sha
                    ),
                )

            # RuntimeFlags mismatch fails closed!
            live_flags = _FakeFlags("7fe450e19", "Q8_0", 8192, "f16", True)
            cross_check_supplied_runtime_flags(live_flags, live_flags)
            with self.assertRaises(RuntimeError):
                cross_check_supplied_runtime_flags(
                    _FakeFlags("deadbeef0", "Q8_0", 8192, "f16", True),
                    live_flags,
                )

            # Rederivation receipt defaults False unless attested on disk
            self.assertFalse(verify_rederivation_receipt(None))
            self.assertFalse(verify_rederivation_receipt(tmp / "missing.json"))
            rec_path = tmp / "rederivation_receipt.json"
            rec_path.write_text(
                json.dumps(
                    {
                        "zero_byte_diff_all": True,
                        "files": {
                            "formal.gguf": {
                                "zero_byte_diff": True,
                                "byte_diff_count": 0,
                                "expected_sha256": gguf_sha,
                                "rederived_sha256": gguf_sha,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(verify_rederivation_receipt(rec_path, expected_gguf_sha256=gguf_sha))
            self.assertFalse(verify_rederivation_receipt(rec_path, expected_gguf_sha256=other_sha))

    def test_phase4_live_rejection_tally_rejects_unrejected_stage3_mount(self) -> None:
        rejections: dict[str, dict[str, Any]] = {}
        record_live_rejection(rejections, "forged_cert_digest", "ERR_CERT_INVALID")
        record_live_rejection(rejections, "behavioral_corruptor_stage3", "ERR_CANARY_FAILED")
        summary_ok = summarize_live_rejections(rejections)
        self.assertEqual(summary_ok["tamper_rejected_count"], 2)
        self.assertEqual(summary_ok["tamper_total_count"], 2)
        self.assertTrue(summary_ok["all_rejected"])

        record_live_rejection(rejections, "compiler_goodhart_patch", "MOUNTED_STAGE3_NOT_REJECTED_BY_CANARIES")
        summary_fail = summarize_live_rejections(rejections)
        self.assertEqual(summary_fail["tamper_rejected_count"], 2)
        self.assertEqual(summary_fail["tamper_total_count"], 3)
        self.assertFalse(summary_fail["all_rejected"])
        self.assertFalse(rejections["compiler_goodhart_patch"]["passed"])

    def test_cli_flags_parse(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(
            [
                "all",
                "--compiler-manifest",
                "artifacts/MANIFEST.json",
                "--formal-gguf",
                "artifacts/p2b/formal-verification.p2b.f16.gguf",
                "--canary-jsonl",
                "warp_canaries_16.json",
                "--phase6-canary-jsonl",
                "warp_canaries_multidomain.json",
                "--canary-cmd",
                "python3 grade_canaries.py --server-url {server_url} --lora-json {lora_json}",
                "--mixed-jsonl",
                "mixed_composition_30.jsonl",
                "--mixed-grader-cmd",
                "python3 grade_mixed.py --responses {responses_jsonl}",
                "--retention-jsonl",
                "general_retention_100.jsonl",
                "--retention-grader-cmd",
                "python3 grade_retention.py --baseline-responses {baseline_jsonl} --candidate-responses {candidate_jsonl}",
                "--formal-eval-jsonl",
                "validation.jsonl",
                "--holdout-grader-cmd",
                "python3 grade_holdout.py --responses {responses_jsonl}",
                "--parallel-slots",
                "8",
            ]
        )
        self.assertEqual(ns.subcommand, "all")
        self.assertEqual(ns.phase6_canary_jsonl, "warp_canaries_multidomain.json")
        self.assertEqual(ns.parallel_slots, 8)
        self.assertIn("{responses_jsonl}", ns.mixed_grader_cmd)
        self.assertIn("{baseline_jsonl}", ns.retention_grader_cmd)


class TestMcproofStackLabIntegration(unittest.TestCase):
    """Integration checks that execute when sibling lab repositories & binaries are available."""

    def test_step_4_1_mde_zones_and_pokayoke_code_audit(self) -> None:
        paths = _discover_lab_paths_or_skip(self)
        with tempfile.TemporaryDirectory(prefix="mcproof_test_4_1_") as td:
            res = verify_step_4_1_mde_zones_and_code_audit(paths, Path(td))
            self.assertTrue(res["passed"])
            self.assertTrue(res["manifest_id"].startswith("sha256:"))
            self.assertEqual(res["classified_zones"]["lean_file"], "formal_proof")
            self.assertEqual(res["classified_zones"]["condensed_json"], "condensed_json")
            self.assertEqual(
                set(res["code_audit_negative_caught_rules"]),
                {"bare_assert", "bare_except", "duplicate_json_key", "silent_except_swallow"},
            )

    def test_canary_min_preservation_not_weakened_and_lineage_pin(self) -> None:
        paths = _discover_lab_paths_or_skip(self)
        from warp_modeld.canary import CanaryConfigError

        with tempfile.TemporaryDirectory(prefix="mcproof_test_can_") as td:
            tmp = Path(td)
            weak_json = tmp / "weak_4_pres.json"
            weak_json.write_text(
                json.dumps(
                    {
                        "canaries": [
                            {
                                "canary_id": f"pres-{i}",
                                "category": "preservation",
                                "prompt": "Compute 2 + 2.",
                                "must_contain": ["4"],
                            }
                            for i in range(4)
                        ]
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(weak_json, 0o600)
            with self.assertRaises(CanaryConfigError):
                load_canary_suite(paths, weak_json, min_preservation=8)

            cmd = build_canary_command(paths, min_preservation=8)
            self.assertIn("{server_url}", cmd)
            self.assertIn("{lora_json}", cmd)

        zm_doc = json.loads(paths.zone_manifest_path.read_text(encoding="utf-8"))
        zm_id = str(zm_doc["manifest_id"])
        lineage_file = paths.stack_root.parent / "spec" / "lineage.json"
        if not lineage_file.is_file():
            lineage_file = paths.stack_root.parent / "repo" / "spec" / "lineage.json"
        repo_lineage = json.loads(lineage_file.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="mcproof_test_lin_") as td:
            env = build_checkpoint_and_weft_suite(
                paths,
                work_dir=Path(td),
                base_gguf=paths.default_base_gguf,
                zone_manifest_id=zm_id,
            )
            self.assertTrue(env["checkpoint"].has_ssm_recurrent)
            self.assertEqual(env["warp_flags"].quantization, "Q8_0")
            self.assertEqual(
                env["lineage"].corpus_tree_sha256,
                repo_lineage["source_lineage"]["corpus_tree_sha256"],
            )
            self.assertIn("gg.siliconcordat/mde", env["vendor_mde_meta"])

            p1_file = env["plane1_dir"] / "spec" / "plane1_formal_spec.md"
            p1_file.write_bytes(p1_file.read_bytes() + b"\n")
            mutated_tracked = dict(env["tracked_plane1_hashes"])
            mutated_tracked["spec/plane1_formal_spec.md"] = sha256_file(p1_file)
            mutated_tree = compute_mcproof_plane1_tree_sha256(
                mutated_tracked,
                env["upstream_repos"],
                zm_id,
            )
            self.assertNotEqual(mutated_tree, env["lineage"].corpus_tree_sha256)

    @unittest.skipUnless(
        os.environ.get("MCPROOF_LIVE_LLAMA_TESTS") == "1",
        "Set MCPROOF_LIVE_LLAMA_TESTS=1 to run full live Qwen3.5-4B llama-server Phase 4 & Phase 6 tests",
    )
    def test_live_phase4_and_phase6_end_to_end(self) -> None:
        paths = _discover_lab_paths_or_skip(self)
        with tempfile.TemporaryDirectory(prefix="mcproof_test_live_") as td:
            out_dir = Path(td) / "results"
            p4 = run_phase4_live_mount(paths, output_dir=out_dir)
            self.assertTrue(p4["passed"])
            self.assertEqual(p4["step_4_4_drift_and_rollback"]["post_kill_switch_max_logprob_diff"], 0.0)

            p6 = run_phase6_composition(paths, output_dir=out_dir)
            self.assertEqual(p6["gates"]["T_C2_mixed_zone_isolation"]["formal_block_corruptions"], 0)
            self.assertEqual(p6["gates"]["T_C4_order_invariance_and_rollback"]["full_stack_rollback_max_logprob_diff"], 0.0)
            self.assertFalse(p6["gates"]["T_C5_serving_budget"]["benchmark_anomaly"])


if __name__ == "__main__":
    unittest.main()
