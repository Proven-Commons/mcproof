"""Unit and integration tests for deterministic CPU float64 compilation, slabs, GGUF, and controls."""

from __future__ import annotations

import json
import socket
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from warp_modeld.canary import reject_adapter_supplied_canaries
from warp_modeld.certificate import CertificateBounds, RationalBound, verify_stack_division_free
from warp_modeld.errors import (
    CertificateError,
    ForgedCanaryError,
    StaleLineageError,
    ZoneManifestDriftError,
)
from warp_modeld.fingerprint import (
    AdapterBundle,
    CheckpointFingerprint,
    Plane1Lineage,
    verify_stage1,
)
from weft.slab_wire import verify_slab_wire

from mcproof_compile.ablations import build_sabotage_and_goodhart_controls
from mcproof_compile.activation_harvester import exact_up_proj_swiglu_residual_f64
from mcproof_compile.compiler_suite import compile_p2a_baseline, compile_p2b_deterministic
from mcproof_compile.evaluator import _start_server, _stop_server
from mcproof_compile.hardware_probe import (
    PINNED_TARGET_TENSOR_ST,
    PINNED_ZONE_MANIFEST_ID,
    probe_linux_workbench_readonly,
)
from mcproof_compile.rederive import run_independent_rederivation


def _require(cond: bool, msg: str = "check failed") -> None:
    if not cond:
        raise AssertionError(msg)


def _write_synthetic_qwen35_fixture(ck_dir: Path, d_out: int = 128, d_in: int = 64) -> None:
    rng = np.random.default_rng(20261119)
    tensors = {
        PINNED_TARGET_TENSOR_ST: (rng.standard_normal((d_out, d_in)) * 0.02).astype(np.float32),
        "model.language_model.norm.weight": (rng.standard_normal(d_in) * 0.05).astype(np.float32),
        "model.language_model.embed_tokens.weight": (rng.standard_normal((256, d_in)) * 0.05).astype(np.float32),
    }
    header = {}
    blobs = []
    off = 0
    for name, arr in sorted(tensors.items()):
        raw = np.ascontiguousarray(arr, dtype="<f4").tobytes()
        header[name] = {"dtype": "F32", "shape": list(arr.shape), "data_offsets": [off, off + len(raw)]}
        blobs.append(raw)
        off += len(raw)
    hdr = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with (ck_dir / "model.safetensors").open("wb") as fh:
        fh.write(struct.pack("<Q", len(hdr)))
        fh.write(hdr)
        for b in blobs:
            fh.write(b)
    (ck_dir / "config.json").write_text('{"model_type":"qwen3_5"}\n', encoding="utf-8")
    (ck_dir / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
    (ck_dir / "chat_template.jinja").write_text("{{ messages }}\n", encoding="utf-8")


def test_swiglu_residual_aligns_positively_with_unembedding_contrast() -> None:
    rng = np.random.default_rng(7)
    d_model, d_ff, vocab = 64, 128, 100
    h = rng.standard_normal(d_model)
    gate_act = np.abs(rng.standard_normal(d_ff)) + 0.1
    w_down = rng.standard_normal((d_model, d_ff)) * 0.05
    gamma_1 = 1.0 + rng.standard_normal(d_model) * 0.1
    w_embed = rng.standard_normal((vocab, d_model)) * 0.05

    r_up = exact_up_proj_swiglu_residual_f64(
        h, gate_act, 2.0, w_down, gamma_1, w_embed, [10], [20], residual_rel_scale=0.25
    )
    delta_ffn = w_down @ (gate_act * r_up)
    _require(bool(np.isclose(np.linalg.norm(delta_ffn), 0.5, rtol=1e-6)), "unexpected delta_ffn norm")

    def _margin(h_vec: np.ndarray) -> float:
        rms = np.sqrt(np.mean(h_vec * h_vec) + 1e-6)
        logits = w_embed @ (gamma_1 * (h_vec / rms))
        return float(logits[10] - logits[20])

    _require(_margin(h + delta_ffn) > _margin(h), "expected positive unembedding contrast margin increase")


def test_zero_byte_rederivation_and_warp_stage1_stage2_gates() -> None:
    with tempfile.TemporaryDirectory(prefix="mcproof_test_") as td:
        root = Path(td)
        ck_dir = root / "ckpt"
        ck_dir.mkdir()
        _write_synthetic_qwen35_fixture(ck_dir, d_out=128, d_in=64)

        p1_dir = root / "repo"
        (p1_dir / "spec").mkdir(parents=True)
        (p1_dir / "spec" / "plane1_formal_spec.md").write_text("# Spec\nZero sorry.\n", encoding="utf-8")
        (p1_dir / "spec" / "lineage.json").write_text('{"schema":"mcproof-lineage/v0.1"}\n', encoding="utf-8")

        rng = np.random.default_rng(99)
        npz_path = root / "acts.npz"
        np.savez_compressed(
            npz_path,
            k0_noise=rng.standard_normal((64, 96)),
            k0_anchors=rng.standard_normal((64, 8)),
            ffn_down_k0=rng.standard_normal((128, 16)),
            compile_keys=rng.standard_normal((64, 16)),
            compile_residuals=rng.standard_normal((128, 16)) * 0.15,
            compile_ffn_residuals=rng.standard_normal((64, 16)) * 0.10,
            goodhart_residuals=-rng.standard_normal((128, 16)) * 0.15,
            compile_pos_toks=np.array([1, 2, 3], dtype=np.int64),
            compile_neg_toks=np.array([4, 5, 6], dtype=np.int64),
            corpus_keys=rng.standard_normal((64, 4)),
            corpus_residuals=rng.standard_normal((128, 4)) * 0.1,
            eido_keys=rng.standard_normal((64, 4)),
            eido_residuals=rng.standard_normal((128, 4)) * 0.1,
            safety_keys=rng.standard_normal((64, 4)),
            safety_sabotage_residuals=rng.standard_normal((128, 4)) * 0.4,
        )

        lineage = {
            "corpus_tree_sha256": "a" * 64,
            "domain_commits": {
                "formal-verification": "b" * 40,
                "corpus": "c" * 40,
                "weft-eido": "d" * 40,
            },
            "contested_heads": [],
        }

        out_1 = root / "p2b_1"
        out_2 = root / "p2b_2"
        res_1 = compile_p2b_deterministic(
            safetensors_dir=ck_dir,
            activations_npz=npz_path,
            plane1_root=p1_dir,
            plane1_rel_files=["spec/plane1_formal_spec.md", "spec/lineage.json"],
            source_lineage=lineage,
            output_dir=out_1,
        )
        receipt = run_independent_rederivation(
            expected_p2b_dir=out_1,
            output_dir=out_2,
            safetensors_dir=ck_dir,
            activations_npz=npz_path,
            plane1_root=p1_dir,
            plane1_rel_files=["spec/plane1_formal_spec.md", "spec/lineage.json"],
            source_lineage=lineage,
        )
        _require(receipt["zero_byte_diff_all"] is True, "expected 0-byte re-derivation")

        _require(
            res_1["artifacts"]["slab_int4_int8_bytes"] < res_1["artifacts"]["gguf_f16_bytes"],
            "expected asymmetric slab to be smaller than F16 GGUF",
        )
        ok_slab, probs_slab, _ = verify_slab_wire(
            out_1 / "formal-verification.p2b.int4_int8.wfsl",
            gate_policy=res_1["gate_policy"],
            expected_zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            expected_base_weights_sha256=res_1["binding_manifest"].checkpoint_fingerprint,
        )
        _require(ok_slab and not probs_slab, f"slab wire verify failed: {probs_slab}")

        p2b_frob = float(
            np.linalg.norm(res_1["p2b_f16_patch"].factor_b @ res_1["p2b_f16_patch"].factor_a, "fro")
        )
        p2a_res = compile_p2a_baseline(
            w0_down=res_1["w0_down"],
            compile_keys=res_1["compile_keys"],
            compile_residuals=res_1["compile_residuals"],
            cov_accum_for_audit=res_1["projector"].cov_accum,
            safety_directions=res_1["safety_directions"],
            target_frob_norm=p2b_frob,
            base_weights_sha256=res_1["binding_manifest"].checkpoint_fingerprint,
            zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            output_dir=root / "p2a",
        )
        _require(
            p2a_res["certificate"]["leakage_energy_scaled"]
            > res_1["p2b_f16_patch"].certificate.leakage_energy_scaled,
            "expected P2-A leakage > P2-B leakage at matched Frobenius norm",
        )

        data = np.load(npz_path)
        ctrls = build_sabotage_and_goodhart_controls(
            cov_true_proj=res_1["projector"],
            k0_norm=res_1["k0_norm"],
            k0_anchors=res_1["k0_anchors"],
            safety_keys=data["safety_keys"],
            safety_sabotage_residuals=data["safety_sabotage_residuals"],
            compile_keys=res_1["compile_keys"],
            goodhart_residuals=data["goodhart_residuals"],
            architecture="qwen35",
            base_weights_sha256=res_1["binding_manifest"].checkpoint_fingerprint,
            zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            p2b_warp_bundle=res_1["warp_bundle"],
            gate_policy=res_1["gate_policy"],
            controls_dir=root / "controls",
        )
        _require(ctrls["sabotage_patch"]["norm_only_gate_passes"] is True, "sabotage must pass norm-only gate")
        _require(ctrls["sabotage_patch"]["stage2_certificate_passes"] is False, "sabotage must fail Stage 2")
        _require(ctrls["goodhart_patch"]["stage2_certificate_passes"] is True, "goodhart must pass Stage 2")

        p2b_bundle_obj = AdapterBundle.from_dict(res_1["warp_bundle"])
        pinned_ckpt = CheckpointFingerprint.from_dict(res_1["warp_bundle"]["checkpoint"])
        pinned_lin = Plane1Lineage.from_dict(lineage)
        s1 = verify_stage1(
            p2b_bundle_obj,
            pinned_ckpt,
            pinned_lin,
            res_1["warp_flags"],
            pinned_zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
        )
        _require(s1.adapter_file_verified is True, "Stage 1 adapter file verification failed")

        gp = res_1["gate_policy"]
        single_bounds = CertificateBounds(
            max_frobenius_sq=RationalBound(gp.max_frob_sq_num, gp.max_frob_sq_den),
            max_spectral_norm_sq=RationalBound(gp.max_spectral_sq_num or gp.max_frob_sq_num, gp.max_spectral_sq_den),
            max_leakage_energy=RationalBound(gp.max_leakage_num or 1, gp.max_leakage_den),
            max_safety_dot_sq=RationalBound(gp.max_safety_dot_sq_num or 1, gp.max_safety_dot_sq_den),
        )
        s2 = verify_stack_division_free(
            [
                (
                    p2b_bundle_obj.certificate,
                    p2b_bundle_obj.adapter_id,
                    p2b_bundle_obj.adapter_sha256,
                    p2b_bundle_obj.scale_num,
                    p2b_bundle_obj.scale_den,
                )
            ],
            single_bounds,
            single_bounds,
            expected_base_weights_sha256=pinned_ckpt.weights_sha256,
        )
        _require(len(s2.adapter_results) == 1, "expected 1 Stage 2 adapter result")

        forged_can_raw = json.loads(
            Path(ctrls["warp_adversarial_bundles"]["forged_canary_warp_bundle"]).read_text(encoding="utf-8")
        )
        with pytest.raises(ForgedCanaryError):
            reject_adapter_supplied_canaries([forged_can_raw])

        stale_obj = AdapterBundle.from_dict(
            json.loads(
                Path(ctrls["warp_adversarial_bundles"]["stale_lineage_warp_bundle"]).read_text(encoding="utf-8")
            )
        )
        with pytest.raises(StaleLineageError):
            verify_stage1(
                stale_obj,
                pinned_ckpt,
                pinned_lin,
                res_1["warp_flags"],
                pinned_zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            )

        drift_obj = AdapterBundle.from_dict(
            json.loads(
                Path(ctrls["warp_adversarial_bundles"]["drifted_zone_manifest_warp_bundle"]).read_text(
                    encoding="utf-8"
                )
            )
        )
        with pytest.raises(ZoneManifestDriftError):
            verify_stage1(
                drift_obj,
                pinned_ckpt,
                pinned_lin,
                res_1["warp_flags"],
                pinned_zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            )

        for bad_key in ("sabotage_warp_bundle", "forged_cert_warp_bundle"):
            bad_obj = AdapterBundle.from_dict(
                json.loads(Path(ctrls["warp_adversarial_bundles"][bad_key]).read_text(encoding="utf-8"))
            )
            with pytest.raises(CertificateError):
                verify_stack_division_free(
                    [
                        (
                            bad_obj.certificate,
                            bad_obj.adapter_id,
                            bad_obj.adapter_sha256,
                            bad_obj.scale_num,
                            bad_obj.scale_den,
                        )
                    ],
                    single_bounds,
                    single_bounds,
                    expected_base_weights_sha256=pinned_ckpt.weights_sha256,
                )


def test_linux_probe_separates_mac_self_ip_from_offline_rtx3080() -> None:
    rep = probe_linux_workbench_readonly()
    _require(rep["linux_rtx3080_online"] is False, "expected linux_rtx3080_online=False")
    _require("mac_control_plane_ips" in rep, "missing mac_control_plane_ips")
    _require("linux_gpu_hosts" in rep, "missing linux_gpu_hosts")


def test_start_server_redirects_stdout_to_log_file_avoiding_pipe_deadlock() -> None:
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "srv.log"
        code = (
            "import http.server, sys\n"
            "sys.stdout.write('X' * (300 * 1024) + '\\n')\n"
            "sys.stdout.flush()\n"
            "class H(http.server.BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')\n"
            "    def log_message(self, *a): return None\n"
            "http.server.HTTPServer(('127.0.0.1', %d), H).serve_forever()\n"
        )
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        proc = _start_server([sys.executable, "-c", code % port], port, log_path, timeout_s=10.0)
        try:
            _require(proc.stdout is None, "expected stdout redirected to log file")
            _require(log_path.stat().st_size >= 300 * 1024, "expected >=300 KB written to log file")
        finally:
            _stop_server(proc)
