"""Unit and integration tests for deterministic CPU float64 compilation, slabs, GGUF, and controls."""

from __future__ import annotations

import hashlib
import json
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_COMPILE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_COMPILE_SRC) not in sys.path:
    sys.path.insert(0, str(_COMPILE_SRC))

from mcproof_compile.activation_harvester import (  # noqa: E402
    exact_up_proj_swiglu_residual_f64,
    verify_cached_activations_npz,
)
from mcproof_compile.evaluator import (  # noqa: E402
    _start_server,
    _stop_server,
    build_validation_scorecard_summary,
    grade_validation_record,
    resolve_datasets_root,
    validate_and_resolve_oracle_cmd,
    verify_b1_repeat_parity,
)
from mcproof_compile.hardware_probe import (  # noqa: E402
    PINNED_TARGET_TENSOR_ST,
    PINNED_ZONE_MANIFEST_ID,
    PROBED_WORKBENCH_PORTS,
    probe_linux_workbench_readonly,
    probe_llama_server,
    probe_local_host_facts,
)
from mcproof_compile.safetensors_io import load_safetensors_tensor_f64  # noqa: E402


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
    (ck_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_5",
                "text_config": {"layer_types": ["linear_attention", "full_attention"]},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
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


def test_safetensors_io_enforces_traversal_and_offset_bounds() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ck = root / "ckpt"
        ck.mkdir()
        _write_synthetic_qwen35_fixture(ck, d_out=8, d_in=4)

        loaded = load_safetensors_tensor_f64(ck, PINNED_TARGET_TENSOR_ST)
        _require(loaded.shape == (8, 4) and loaded.dtype == np.float64, "valid load failed")

        # 1. Path traversal in model.safetensors.index.json weight_map
        outside = root / "outside.safetensors"
        outside.write_bytes((ck / "model.safetensors").read_bytes())
        (ck / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {PINNED_TARGET_TENSOR_ST: "../outside.safetensors"}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="escapes checkpoint dir"):
            load_safetensors_tensor_f64(ck, PINNED_TARGET_TENSOR_ST)

        # 2. Absolute path in weight_map
        (ck / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {PINNED_TARGET_TENSOR_ST: str(outside.resolve())}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="escapes checkpoint dir"):
            load_safetensors_tensor_f64(ck, PINNED_TARGET_TENSOR_ST)
        (ck / "model.safetensors.index.json").unlink()

        # 3. Out-of-bounds and inverted data_offsets in safetensors header
        bad_ck = root / "bad_ckpt"
        bad_ck.mkdir()
        for bad_offsets in ([-4, 128], [64, 32], [0, 999999]):
            hdr = json.dumps(
                {
                    "w": {
                        "dtype": "F32",
                        "shape": [8, 4],
                        "data_offsets": bad_offsets,
                    }
                }
            ).encode("utf-8")
            with (bad_ck / "model.safetensors").open("wb") as fh:
                fh.write(struct.pack("<Q", len(hdr)))
                fh.write(hdr)
                fh.write(b"\x00" * 128)
            with pytest.raises(ValueError, match="out of bounds"):
                load_safetensors_tensor_f64(bad_ck, "w")


def test_cached_activations_npz_hmac_sha256_verification() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        npz_path = root / "harvested_activations.npz"
        np.savez_compressed(npz_path, k0_noise=np.ones((4, 4), dtype=np.float64))
        true_sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()

        # Missing sidecar fails closed
        with pytest.raises(FileNotFoundError):
            verify_cached_activations_npz(npz_path)

        meta_path = npz_path.with_suffix(".meta.json")
        provenance = {
            "torch_version": "2.8.0",
            "device": "cpu",
            "forward_dtype": "bfloat16",
            "platform": "test-platform",
        }
        # Provenance-less sidecars fail closed even when the NPZ digest matches.
        meta_path.write_text(json.dumps({"npz_sha256": true_sha}) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="harvest_runtime"):
            verify_cached_activations_npz(npz_path)
        meta_path.write_text(
            json.dumps({"harvest_runtime": provenance, "npz_sha256": true_sha}) + "\n",
            encoding="utf-8",
        )
        verified = verify_cached_activations_npz(npz_path)
        _require(verified["npz_sha256"] == true_sha, "expected matching npz_sha256")
        _require(verified["harvest_runtime"]["device"] == "cpu", "expected harvest_runtime.device")

        # 1-byte tamper in cached NPZ fails closed via hmac.compare_digest
        raw = bytearray(npz_path.read_bytes())
        raw[-1] ^= 0x01
        npz_path.write_bytes(bytes(raw))
        with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
            verify_cached_activations_npz(npz_path)


def test_hardware_probe_injected_tailscale_ports_and_missing_binaries() -> None:
    # 1. Online Windows peer with all ports closed: probes every listed port, redacts IP, False rtx3080
    probed_calls: list[tuple[str, int]] = []
    fake_ts_win = json.dumps(
        {
            "BackendState": "Running",
            "Peer": {
                "node_1": {
                    "HostName": "geminus",
                    "OS": "windows",
                    "Online": True,
                    "TailscaleIPs": ["192.0.2.42", "2001:db8::42"],
                    "sshHostKeys": [],
                },
                "node_2": {
                    "HostName": "charminar",
                    "OS": "linux",
                    "Online": True,
                    "TailscaleIPs": ["192.0.2.43"],
                    "sshHostKeys": ["ssh-ed25519 AAAA"],
                },
            },
        }
    )

    def _fake_runner_win(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout=fake_ts_win, stderr="")

    def _fake_port_closed(host: str, port: int) -> bool:
        probed_calls.append((host, port))
        return False

    rep_win = probe_linux_workbench_readonly(
        run_cmd=_fake_runner_win,
        port_probe=_fake_port_closed,
        tailscale_candidates=("tailscale",),
    )
    _require(rep_win["linux_rtx3080_online"] is False, "windows offline SSH must be False")
    _require(rep_win["ux582hs_rtx3080_provisioned"] is False, "closed ports must be False")
    _require("measured_host_facts" in rep_win and "static_reference_notes" in rep_win, "missing split")
    gem_ports = rep_win["peer_port_probes"]["geminus"]["probed_closed_ports"]
    _require(gem_ports == list(PROBED_WORKBENCH_PORTS), "expected every listed port to be probed")
    _require("192.0.2.42" not in json.dumps(rep_win), "raw peer IP leaked into report")

    # 2. Online Linux RTX 3080 workbench with port 22 and 8080 open -> True (proves non-tautological!)
    fake_ts_linux = json.dumps(
        {
            "BackendState": "Running",
            "Peer": {
                "node_1": {
                    "HostName": "geminus",
                    "OS": "linux",
                    "Online": True,
                    "TailscaleIPs": ["192.0.2.42"],
                    "sshHostKeys": ["ssh-ed25519 AAAA"],
                }
            },
        }
    )
    rep_linux = probe_linux_workbench_readonly(
        run_cmd=lambda cmd: subprocess.CompletedProcess(cmd, 0, stdout=fake_ts_linux, stderr=""),
        port_probe=lambda _host, port: port in (22, 8080),
        tailscale_candidates=("tailscale",),
    )
    _require(rep_linux["ux582hs_rtx3080_provisioned"] is True, "expected provisioned=True")
    _require(rep_linux["linux_rtx3080_online"] is True, "expected linux_rtx3080_online=True")
    _require(rep_linux["peer_port_probes"]["geminus"]["probed_open_ports"] == [22, 8080], "open ports mismatch")

    # 3. Missing tailscale / sysctl binaries and unparseable llama-server --version -> no fallbacks
    rep_missing = probe_linux_workbench_readonly(
        run_cmd=lambda _cmd: None,
        tailscale_candidates=("tailscale",),
    )
    _require(rep_missing["tailscale_status"] == "unavailable", "expected unavailable tailscale")

    host_missing = probe_local_host_facts(run_cmd=lambda _cmd: None)
    _require(host_missing["unified_ram_gib"] is None, "must not fallback to 64.0")
    _require(host_missing["cpu_brand"] is None, "must not fallback to Apple M1 Max")

    llama_unparsed = probe_llama_server(
        llama_bin="llama-server",
        run_cmd=lambda cmd: subprocess.CompletedProcess(cmd, 0, stdout="version: 0.5.0 (custom build)\n", stderr=""),
    )
    _require(llama_unparsed["available"] is True and llama_unparsed["commit"] is None, "commit must be None")


def test_evaluator_b1_exact_parity_and_fail_closed_oracle_grading() -> None:
    # 1. Exact B1 repeat parity: empty -> False, prefix containment -> False, exact -> True
    ok_empty, n_empty = verify_b1_repeat_parity([], [])
    _require(ok_empty is False and n_empty == 0, "empty parity check must be False")

    ok_prefix, n_prefix = verify_b1_repeat_parity(["theorem t : True := trivial -- full"], ["theorem t : True"])
    _require(ok_prefix is False and n_prefix == 1, "prefix-only match must fail exact parity")

    ok_exact, n_exact = verify_b1_repeat_parity(["abc", "def"], ["abc", "def"])
    _require(ok_exact is True and n_exact == 2, "exact match across all items must pass")

    ok_partial, n_partial = verify_b1_repeat_parity(["abc", "def"], ["abc", "xyz"])
    _require(ok_partial is False and n_partial == 2, "single item mismatch must fail")

    # 2. Scorecard summary: factual SOP tokens, no savings-ratio tautology, negative efficacy surfaced
    arm_template = {
        "by_family": {},
        "failure_rate": 0.9,
        "mean_elapsed_ms": 10.0,
        "pass_rate": 0.1,
        "passed": 4,
        "sop_injected_tokens_per_prompt": 0,
        "surface_hygiene_rates": {},
        "top_failure_rules": {},
        "total": 48,
    }
    arms = {
        "B0": {**arm_template, "passed": 4},
        "B1": {**arm_template, "passed": 8, "sop_injected_tokens_per_prompt": 32216},
        "P2-A": {**arm_template, "passed": 0},
        "P2-B": {**arm_template, "passed": 2},
        "goodhart": {**arm_template, "passed": 4},
        "logit_bias": {**arm_template, "passed": 6},
    }
    sc = build_validation_scorecard_summary(
        arm_summaries=arms,
        n_prompts=48,
        max_tokens=1024,
        spec_token_count=32216,
        b1_prefix_cache_exact=False,
        b1_prefix_cache_tested_items=0,
        p2b_scale=1.0,
        safety_probe_results={},
        grading_paths_used={"datasets_grade_item_script": 288},
    )
    _require("p2b_sop_token_savings_ratio" not in json.dumps(sc), "tautological token savings must be removed")
    _require(sc["p2b_sop_tokens_injected"] == 0 and sc["b1_sop_tokens_injected"] == 32216, "SOP token counts")
    _require(sc["b1_prefix_cache_parity_verified"] is False, "must reflect False parity honestly")
    _require(sc["efficacy_verdict"] == "REJECTED_NEGATIVE_EFFICACY", "expected negative efficacy verdict")
    _require(
        sc["phase5_preview_on_public_validation"]["p2b_relative_failure_reduction_vs_b0"] == -0.045455,
        "expected -0.045455 relative failure reduction",
    )

    # 3. Dataset path resolution precedence, oracle_cmd allowlist, and fail-closed non-JSON output
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        sibling_ds = ws / "datasets" / "scripts"
        sibling_ds.mkdir(parents=True)
        repo = ws / "repo"
        in_repo_ds = repo / "datasets" / "scripts"
        in_repo_ds.mkdir(parents=True)

        resolved_ds = resolve_datasets_root(repo)
        _require(resolved_ds == repo / "datasets", "must prefer repo_root/datasets over sibling datasets")

        # Disallowed executable in oracle_cmd must be rejected without running
        bad_cmd, reason = validate_and_resolve_oracle_cmd(
            "bash -c 'echo {\"passed\": true}' --fixture-json x.json",
            repo_root=repo,
            ds_root=repo / "datasets",
        )
        _require(bad_cmd is None and reason is not None, "disallowed executable must be rejected")

        bad_grade = grade_validation_record(
            {"id": "CUSTOM-1", "family": "B", "oracle_cmd": "sh -c true --fixture-json f.json"},
            "def check(x): return True",
            repo_root=repo,
        )
        _require(
            bad_grade["passed"] is False
            and bad_grade["epistemic_status"] == "REJECTED"
            and bad_grade["findings"][0]["rule"] == "UNSAFE_ORACLE_CMD",
            "expected UNSAFE_ORACLE_CMD fail-closed rejection",
        )

        # Broken grade_item.py exiting 0 with non-JSON or missing 'passed' must fail closed!
        (in_repo_ds / "grade_item.py").write_text(
            "import sys\nprint('not json at all')\nsys.exit(0)\n",
            encoding="utf-8",
        )
        unparseable_res = grade_validation_record(
            {"id": "PUB-A-V01", "family": "A"},
            "candidate text",
            repo_root=repo,
        )
        _require(
            unparseable_res["passed"] is False
            and unparseable_res["epistemic_status"] == "REJECTED"
            and unparseable_res["grading_path"] == "datasets_grade_item_script"
            and unparseable_res["findings"][0]["rule"] == "ORACLE_OUTPUT_UNPARSEABLE",
            f"expected fail-closed ORACLE_OUTPUT_UNPARSEABLE, got {unparseable_res}",
        )


def test_start_server_redirects_stdout_to_log_file_avoiding_pipe_deadlock() -> None:
    # Windows releases the inherited srv.log handle shortly after _stop_server.
    # ignore_cleanup_errors avoids a deterministic WinError 32 during TemporaryDirectory teardown.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
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


def test_zero_byte_9_of_9_rederivation_tamper_and_warp_gates() -> None:
    pytest.importorskip("weft", reason="requires siliconcordat/weft on PYTHONPATH")
    pytest.importorskip("warp_modeld", reason="requires siliconcordat/warp on PYTHONPATH")
    pytest.importorskip("exo", reason="requires siliconcordat/exo on PYTHONPATH")

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
    from mcproof_compile.compiler_suite import (
        PRE_REGISTERED_GATE_POLICY,
        compile_p2a_baseline,
        compile_p2b_deterministic,
    )
    from mcproof_compile.pipeline import verify_control_gates_fail_closed
    from mcproof_compile.rederive import P2B_CHECKED_FILES, run_independent_rederivation

    with tempfile.TemporaryDirectory(prefix="mcproof_test_") as td:
        root = Path(td)
        ck_dir = root / "ckpt"
        ck_dir.mkdir()
        _write_synthetic_qwen35_fixture(ck_dir, d_out=128, d_in=64)

        lineage = {
            "corpus_tree_sha256": "a" * 64,
            "domain_commits": {
                "formal-verification": "b" * 40,
                "corpus": "c" * 40,
                "weft-eido": "d" * 40,
            },
            "contested_heads": [],
        }

        p1_dir = root / "repo"
        (p1_dir / "spec").mkdir(parents=True)
        (p1_dir / "spec" / "plane1_formal_spec.md").write_text("# Spec\nZero sorry.\n", encoding="utf-8")
        (p1_dir / "spec" / "lineage.json").write_text(
            json.dumps(
                {
                    "schema": "mcproof-lineage/v0.1",
                    "zone_manifest_id": PINNED_ZONE_MANIFEST_ID,
                    "source_lineage": lineage,
                    "tracked_plane1_files": {
                        "spec/plane1_formal_spec.md": "0" * 64,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        rng = np.random.default_rng(99)
        # Match Qwen3.5-4B geometry (2048 K0 vectors in R^2560 -> 80% K0 occupancy, 20% Null(K0))
        k0_noise = np.zeros((64, 96), dtype=np.float64)
        k0_noise[:48, :] = rng.standard_normal((48, 96)) * 2.5
        k0_anchors = np.zeros((64, 8), dtype=np.float64)
        k0_anchors[:48, :] = rng.standard_normal((48, 8))
        comp_res = np.zeros((128, 16), dtype=np.float64)
        comp_res[:64, :] = rng.standard_normal((64, 16)) * 0.30
        sab_res = np.zeros((128, 4), dtype=np.float64)
        sab_res[64:, :] = rng.standard_normal((64, 4)) * 0.85
        safety_keys = k0_noise[:, :4].copy()

        npz_path = root / "acts.npz"
        np.savez_compressed(
            npz_path,
            k0_noise=k0_noise,
            k0_anchors=k0_anchors,
            ffn_down_k0=rng.standard_normal((128, 16)),
            compile_keys=rng.standard_normal((64, 16)),
            compile_residuals=comp_res,
            compile_ffn_residuals=rng.standard_normal((64, 16)) * 0.05,
            goodhart_residuals=-comp_res,
            compile_pos_toks=np.array([1, 2, 3], dtype=np.int64),
            compile_neg_toks=np.array([4, 5, 6], dtype=np.int64),
            corpus_keys=rng.standard_normal((64, 4)),
            corpus_residuals=comp_res[:, :4] * 0.5,
            eido_keys=rng.standard_normal((64, 4)),
            eido_residuals=comp_res[:, 4:8] * 0.5,
            safety_keys=safety_keys,
            safety_sabotage_residuals=sab_res,
        )
        npz_sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()
        npz_path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "harvest_runtime": {
                        "torch_version": "2.8.0",
                        "device": "cpu",
                        "platform": "test-platform",
                    },
                    "npz_sha256": npz_sha,
                    "step_metadata": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        out_1 = p1_dir / "compile" / "artifacts" / "p2b"
        out_2 = root / "p2b_rederived"
        test_commit = "0123456789abcdef"

        # Attesting without a verified llama_server_commit must fail closed
        with pytest.raises(RuntimeError, match="llama_server_commit"):
            compile_p2b_deterministic(
                safetensors_dir=ck_dir,
                activations_npz=npz_path,
                plane1_root=p1_dir,
                plane1_rel_files=["spec/plane1_formal_spec.md", "spec/lineage.json"],
                source_lineage=lineage,
                output_dir=out_1,
                llama_server_commit=None,
            )

        res_1 = compile_p2b_deterministic(
            safetensors_dir=ck_dir,
            activations_npz=npz_path,
            plane1_root=p1_dir,
            plane1_rel_files=["spec/plane1_formal_spec.md", "spec/lineage.json"],
            source_lineage=lineage,
            output_dir=out_1,
            llama_server_commit=test_commit,
        )
        _require(res_1["gate_policy"] == PRE_REGISTERED_GATE_POLICY, "must use PRE_REGISTERED_GATE_POLICY")
        _require(
            res_1["warp_bundle"]["checkpoint"]["has_ssm_recurrent"] is True,
            "expected has_ssm_recurrent=True from linear_attention config",
        )
        _require(
            res_1["warp_bundle"]["adapter_path"] == "compile/artifacts/p2b/formal-verification.p2b.f16.gguf",
            "expected repo-relative POSIX adapter_path",
        )
        _require(
            res_1["f16_vs_float64_frob_diff"] <= res_1["f16_rounding_tolerance"],
            "expected float64 vs f16 factor diff within rounding tolerance",
        )

        # Independent 9/9 0-byte re-derivation (loading lineage from spec/lineage.json, not out_1!)
        receipt = run_independent_rederivation(
            expected_p2b_dir=out_1,
            output_dir=out_2,
            safetensors_dir=ck_dir,
            activations_npz=npz_path,
            plane1_root=p1_dir,
            llama_server_commit=test_commit,
        )
        _require(receipt["checked_file_count"] == 9, f"expected 9 checked files, got {receipt['checked_file_count']}")
        _require(set(receipt["files"].keys()) == set(P2B_CHECKED_FILES), "missing P2-B checked file")
        _require(receipt["zero_byte_diff_all"] is True, f"expected 9/9 0-byte diff: {receipt['files']}")

        # Negative test 1: 1-byte tamper on expected f16.gguf must fail re-derivation
        gguf_target = out_1 / "formal-verification.p2b.f16.gguf"
        orig_gguf = gguf_target.read_bytes()
        tampered = bytearray(orig_gguf)
        tampered[-1] ^= 0x80
        gguf_target.write_bytes(bytes(tampered))
        try:
            bad_receipt = run_independent_rederivation(
                expected_p2b_dir=out_1,
                output_dir=root / "p2b_tamper_check",
                safetensors_dir=ck_dir,
                activations_npz=npz_path,
                plane1_root=p1_dir,
                llama_server_commit=test_commit,
            )
            _require(bad_receipt["zero_byte_diff_all"] is False, "1-byte GGUF tamper must fail")
            _require(
                bad_receipt["files"]["formal-verification.p2b.f16.gguf"]["byte_diff_count"] == 1,
                "expected exact byte_diff_count == 1",
            )
        finally:
            gguf_target.write_bytes(orig_gguf)

        # Negative test 2: CRLF conversion on expected JSON surfaces crlf_only_mismatch diagnostic
        cert_target = out_1 / "formal-verification.p2b.certificate.json"
        orig_cert = cert_target.read_bytes()
        cert_target.write_bytes(orig_cert.replace(b"\n", b"\r\n"))
        try:
            crlf_receipt = run_independent_rederivation(
                expected_p2b_dir=out_1,
                output_dir=root / "p2b_crlf_check",
                safetensors_dir=ck_dir,
                activations_npz=npz_path,
                plane1_root=p1_dir,
                llama_server_commit=test_commit,
            )
            _require(crlf_receipt["zero_byte_diff_all"] is False, "CRLF bytes must not silently pass")
            _require(
                crlf_receipt["files"]["formal-verification.p2b.certificate.json"]["crlf_only_mismatch"] is True,
                "expected crlf_only_mismatch=True diagnostic",
            )
        finally:
            cert_target.write_bytes(orig_cert)

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
            output_dir=p1_dir / "compile" / "artifacts" / "p2a",
        )
        _require(p2a_res["stage2_gate_passes"] is False, "P2-A must fail PRE_REGISTERED_GATE_POLICY")

        data = np.load(npz_path)
        ctrls_dir = p1_dir / "compile" / "artifacts" / "controls"
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
            controls_dir=ctrls_dir,
        )
        gate_receipt = verify_control_gates_fail_closed(
            repo_root=p1_dir,
            p2b_res=res_1,
            p2a_res=p2a_res,
            controls_res=ctrls,
            source_lineage=lineage,
            zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            controls_dir=ctrls_dir,
        )
        _require(
            gate_receipt["all_five_tamper_and_sabotage_controls_failed_closed"] is True,
            "all 5 tamper/sabotage controls must fail closed",
        )
        _require(
            gate_receipt["in_nullspace_goodhart_boundary"]["caught_at_stage2"] is False,
            "goodhart must be documented as Stage-2-admissible",
        )

        # Direct warp_modeld type checks confirming each specific error class
        p2b_disk_bundle = {**res_1["warp_bundle"], "adapter_path": str(gguf_target)}
        p2b_bundle_obj = AdapterBundle.from_dict(p2b_disk_bundle)
        pinned_ckpt = CheckpointFingerprint.from_dict(p2b_disk_bundle["checkpoint"])
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
        forged_can_raw = json.loads((p1_dir / ctrls["warp_adversarial_bundles"]["forged_canary_warp_bundle"]).read_text())
        with pytest.raises(ForgedCanaryError):
            reject_adapter_supplied_canaries([forged_can_raw])

        stale_raw = json.loads((p1_dir / ctrls["warp_adversarial_bundles"]["stale_lineage_warp_bundle"]).read_text())
        stale_raw["adapter_path"] = str(gguf_target)
        with pytest.raises(StaleLineageError):
            verify_stage1(
                AdapterBundle.from_dict(stale_raw),
                pinned_ckpt,
                pinned_lin,
                res_1["warp_flags"],
                pinned_zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            )

        drift_raw = json.loads(
            (p1_dir / ctrls["warp_adversarial_bundles"]["drifted_zone_manifest_warp_bundle"]).read_text()
        )
        drift_raw["adapter_path"] = str(gguf_target)
        with pytest.raises(ZoneManifestDriftError):
            verify_stage1(
                AdapterBundle.from_dict(drift_raw),
                pinned_ckpt,
                pinned_lin,
                res_1["warp_flags"],
                pinned_zone_manifest_id=PINNED_ZONE_MANIFEST_ID,
            )

        for bad_key in ("sabotage_warp_bundle", "forged_cert_warp_bundle"):
            bad_raw = json.loads((p1_dir / ctrls["warp_adversarial_bundles"][bad_key]).read_text())
            with pytest.raises(CertificateError):
                bad_obj = AdapterBundle.from_dict(bad_raw)
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
