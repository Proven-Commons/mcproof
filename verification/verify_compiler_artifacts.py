#!/usr/bin/env python3
"""Independent verification of `@compiler` Phase 2 & Phase 3 artifacts, bindings, and controls."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

_VERIF_DIR = Path(__file__).resolve().parent
PLANE1_ROOT = _VERIF_DIR.parent
_SC_ROOT = Path(os.environ.get("SILICONCORDAT_ROOT") or (PLANE1_ROOT.parents[1] / "siliconcordat"))
WEFT_SRC = Path(os.environ.get("WEFT_SRC") or (_SC_ROOT / "weft" / "src"))
sys.path.insert(0, str(WEFT_SRC))

from weft.binding import BindingManifest, RuntimeFlags as WeftRuntimeFlags, verify_binding  # noqa: E402
from weft.certificate import FixedRadixCertificate as Certificate, GatePolicy  # noqa: E402
from weft.slab_wire import verify_slab_wire  # noqa: E402

COMPILE_DIR = Path(os.environ.get("MCPROOF_COMPILE_DIR") or (PLANE1_ROOT / "compile"))
ART_DIR = COMPILE_DIR / "artifacts"
SAFETENSORS_DIR = COMPILE_DIR / "checkpoints" / "Qwen3.5-4B"
MDE_BIN = Path(os.environ.get("MDE_BIN") or (_SC_ROOT / "mde" / "target" / "debug" / "mde"))
CHECK_PROSE = Path(os.environ.get("CHECK_PROSE_SCRIPT") or (Path.home() / ".hermes" / "team-skills" / "scripts" / "check-prose.py"))
RECEIPT_OUT = _VERIF_DIR / "compiler_verification_receipt.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    defects: list[str] = []

    manifest_path = ART_DIR / "MANIFEST.json"
    comp_manifest_path = ART_DIR / "compiler_manifest.json"
    if not manifest_path.is_file() or not comp_manifest_path.is_file():
        raise FileNotFoundError("Missing MANIFEST.json or compiler_manifest.json")

    manifest_bytes = manifest_path.read_bytes()
    comp_manifest_bytes = comp_manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_bytes != comp_manifest_bytes:
        defects.append("MANIFEST.json and compiler_manifest.json differ in bytes")

    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not manifest.get("rederivation_zero_byte_diff"):
        defects.append("manifest.rederivation_zero_byte_diff is not true")
    if manifest.get("validation_scorecard") is None:
        defects.append("manifest.validation_scorecard is null (stale pre-evaluation manifest)")

    # 1. Verify every SHA-256 recorded in MANIFEST.json matches actual disk bytes
    p2b = manifest["p2b"]
    p2a = manifest["p2a"]
    hash_checks: list[tuple[str, Path, str]] = [
        ("p2b.gguf_f16", Path(p2b["gguf_f16_path"]), str(p2b["gguf_f16_sha256"])),
        ("p2b.slab_int4_int8", Path(p2b["slab_int4_int8_path"]), str(p2b["slab_int4_int8_sha256"])),
        ("p2b.slab_int4_f16", Path(p2b["slab_int4_f16_path"]), str(p2b["slab_int4_f16_sha256"])),
        ("p2b.slab_f16", Path(p2b["slab_f16_path"]), str(p2b["slab_f16_sha256"])),
        ("p2a.gguf_f16", Path(p2a["gguf_f16_path"]), str(p2a["gguf_f16_sha256"])),
        ("p2a.slab_f16", Path(p2a["slab_f16_path"]), str(p2a["slab_f16_sha256"])),
        (
            "harvested_activations.npz",
            ART_DIR / "harvested_activations.npz",
            str(manifest["harvest_summary"]["npz_sha256"]),
        ),
        (
            "constant_logit_bias.json",
            ART_DIR / "ablations" / "constant_logit_bias.json",
            str(manifest["constant_logit_bias_sha256"]),
        ),
        (
            "sabotage_gguf",
            ART_DIR / "controls" / "formal-verification.sabotage.f16.gguf",
            str(manifest["negative_controls"]["sabotage_gguf_sha256"]),
        ),
        (
            "goodhart_gguf",
            ART_DIR / "controls" / "formal-verification.goodhart.f16.gguf",
            str(manifest["negative_controls"]["goodhart_gguf_sha256"]),
        ),
    ]
    for dom, pack in manifest["phase6_composition_packs"].items():
        hash_checks.append((f"phase6.{dom}.gguf", Path(pack["gguf_path"]), str(pack["gguf_sha256"])))

    verified_hashes: dict[str, str] = {}
    for label, fpath, exp_sha in hash_checks:
        if not fpath.is_file():
            defects.append(f"missing_artifact:{label}:{fpath}")
            continue
        got_sha = sha256_file(fpath)
        verified_hashes[label] = got_sha
        if got_sha != exp_sha:
            defects.append(f"sha256_mismatch:{label}:got_{got_sha}_exp_{exp_sha}")

    # 2. Verify Hard Veto 1 recipe completeness + 5-layer Weft BindingManifest
    bind_raw = json.loads(Path(p2b["binding_path"]).read_text(encoding="utf-8"))
    recipe = bind_raw["derivation_recipe"]
    required_recipe_keys = (
        "compiler",
        "method",
        "target_layer",
        "target_tensor_safetensors",
        "target_tensor_gguf",
        "rank",
        "lambda_leakage",
        "lambda_ridge",
        "preservation_weight",
        "output_gain",
        "harvested_activations_npz_sha256",
        "harvested_activations_meta_sha256",
        "rel_step0_weight",
        "zone_manifest_id",
    )
    for rk in required_recipe_keys:
        if rk not in recipe:
            defects.append(f"missing_derivation_recipe_key:{rk}")

    meta_sha_actual = sha256_file(ART_DIR / "harvested_activations.meta.json")
    if "harvested_activations_meta_sha256" in recipe and recipe["harvested_activations_meta_sha256"] != meta_sha_actual:
        defects.append("harvested_activations_meta_sha256 mismatch in derivation_recipe")

    bind_obj = BindingManifest(**bind_raw)
    weft_flags = WeftRuntimeFlags(**bind_raw["runtime_flags"])
    cert_raw = json.loads(Path(p2b["certificate_path"]).read_text(encoding="utf-8"))
    p2b_cert = Certificate(**cert_raw)
    if p2b_cert.sha256() != str(p2b["certificate_sha256"]):
        defects.append(f"canonical_cert_sha256_mismatch:{p2b_cert.sha256()}!={p2b['certificate_sha256']}")
    if bind_obj.sha256() != str(p2b["binding_sha256"]):
        defects.append(f"canonical_binding_sha256_mismatch:{bind_obj.sha256()}!={p2b['binding_sha256']}")
    verified_hashes["p2b.certificate_canonical"] = p2b_cert.sha256()
    verified_hashes["p2b.certificate_file"] = sha256_file(Path(p2b["certificate_path"]))
    verified_hashes["p2b.binding_canonical"] = bind_obj.sha256()
    verified_hashes["p2b.binding_file"] = sha256_file(Path(p2b["binding_path"]))
    bind_res = verify_binding(
        bind_obj,
        checkpoint_dir=SAFETENSORS_DIR,
        runtime_flags=weft_flags,
        plane1_root=PLANE1_ROOT,
        expected_factor_digest=p2b_cert.factor_digest,
        expected_certificate_sha256=p2b_cert.sha256(),
    )
    if not bind_res.ok:
        defects.append(f"verify_binding_failed:{bind_res.problems}")

    # 3. Verify GatePolicy division-free integer check across P2-B slabs, P2-A, sabotage, and Goodhart
    gp_raw = json.loads((ART_DIR / "p2b" / "formal-verification.p2b.gate_policy.json").read_text(encoding="utf-8"))
    gate_policy = GatePolicy(**gp_raw)
    ok_p2b_cert, probs_p2b_cert = p2b_cert.verify_division_free(gate_policy)
    if not ok_p2b_cert:
        defects.append(f"p2b_cert_failed_gate_policy:{probs_p2b_cert}")

    slab_checks: dict[str, bool] = {}
    for s_label, s_key in (
        ("int4_int8", "slab_int4_int8_path"),
        ("int4_f16", "slab_int4_f16_path"),
        ("f16", "slab_f16_path"),
    ):
        s_ok, s_probs, _ = verify_slab_wire(
            Path(p2b[s_key]),
            gate_policy=gate_policy,
            expected_zone_manifest_id=str(recipe["zone_manifest_id"]),
            expected_base_weights_sha256=bind_obj.checkpoint_fingerprint,
        )
        slab_checks[s_label] = bool(s_ok)
        if not s_ok:
            defects.append(f"slab_wire_failed:{s_label}:{s_probs}")

    p2a_cert = Certificate(**p2a["certificate"])
    ok_p2a_cert, probs_p2a_cert = p2a_cert.verify_division_free(gate_policy)
    if ok_p2a_cert:
        defects.append("unprojected P2-A unexpectedly passed nullspace GatePolicy")

    nc_doc = json.loads((ART_DIR / "controls" / "negative_controls_summary.json").read_text(encoding="utf-8"))
    sab_cert = Certificate(**nc_doc["sabotage_patch"]["certificate"])
    ok_sab_cert, probs_sab_cert = sab_cert.verify_division_free(gate_policy)
    if ok_sab_cert:
        defects.append("sabotage_patch unexpectedly passed Stage 2 GatePolicy")
    sab_frob_passes = (
        sab_cert.frobenius_sq_scaled * gate_policy.max_frob_sq_den
        <= gate_policy.max_frob_sq_num * (1 << sab_cert.radix_scale_exp2)
    )
    if not sab_frob_passes:
        defects.append("sabotage_patch did not stay under Frobenius norm cap")

    gh_cert = Certificate(**nc_doc["goodhart_patch"]["certificate"])
    ok_gh_cert, probs_gh_cert = gh_cert.verify_division_free(gate_policy)
    if not ok_gh_cert:
        defects.append(f"goodhart_patch failed Stage 2 GatePolicy:{probs_gh_cert}")

    # 4. Verify Phase 2 hardware report + loud-column ablation invariants
    hw_doc = json.loads((ART_DIR / "phase2_hardware_checkpoint_report.json").read_text(encoding="utf-8"))
    rtx_online = bool(hw_doc["linux_workbench_probe"]["linux_rtx3080_online"])
    if rtx_online:
        defects.append("phase2_hardware_checkpoint_report falsely claims linux_rtx3080_online=True while SSH is closed")

    lc_doc = json.loads((ART_DIR / "ablations" / "loud_column_ablation.json").read_text(encoding="utf-8"))
    if len(lc_doc["per_layer_ffn_down_outlier_profile"]) != 32:
        defects.append("loud_column_ablation did not profile all 32 layers")

    # 5. Run pytest, mde guard --code-audit, and check-prose.py on compile/
    pytest_proc = subprocess.run(
        [str(COMPILE_DIR / ".venv" / "bin" / "pytest"), str(COMPILE_DIR / "tests"), "-W", "error", "-q"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        check=False,
    )
    if pytest_proc.returncode != 0:
        defects.append(f"compile_pytest_failed:{pytest_proc.stdout[-400:]}")

    guard_proc = subprocess.run(
        [
            str(MDE_BIN),
            "guard",
            "--code-audit",
            str(COMPILE_DIR / "src"),
            str(COMPILE_DIR / "tests"),
            str(ART_DIR),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if guard_proc.returncode != 0:
        defects.append(f"compile_mde_guard_failed:{guard_proc.stdout[-400:]}")

    readme_p = COMPILE_DIR / "README.md"
    prose_p1 = subprocess.run(["python3", str(CHECK_PROSE), str(readme_p)], capture_output=True, text=True, check=False)
    prose_p2 = subprocess.run(
        ["python3", str(CHECK_PROSE), "--dupes", str(readme_p)], capture_output=True, text=True, check=False
    )
    if prose_p1.returncode != 0 or prose_p2.returncode != 0:
        defects.append(f"compile_readme_prose_failed:{prose_p1.stdout}{prose_p2.stdout}")

    receipt: dict[str, Any] = {
        "schema": "verifier-compiler-verification-receipt/v0.1",
        "overall_passed": len(defects) == 0,
        "defects": defects,
        "manifest_sha256": manifest_sha256,
        "verified_hashes": verified_hashes,
        "binding_5layer_ok": bind_res.ok,
        "slab_wire_checks": slab_checks,
        "gate_policy_verdicts": {
            "p2b_passes": ok_p2b_cert,
            "p2a_rejected_reasons": probs_p2a_cert,
            "sabotage_frob_norm_passes": sab_frob_passes,
            "sabotage_rejected_reasons": probs_sab_cert,
            "goodhart_passes_stage2": ok_gh_cert,
        },
        "loud_column_headline": lc_doc["headline_ratios"],
        "validation_scorecard": manifest.get("validation_scorecard"),
        "pytest_exit_code": pytest_proc.returncode,
        "mde_guard_exit_code": guard_proc.returncode,
        "readme_prose_clean": prose_p1.returncode == 0 and prose_p2.returncode == 0,
    }
    RECEIPT_OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": receipt["overall_passed"], "defects": defects}, indent=2))
    return 0 if not defects else 1


if __name__ == "__main__":
    raise SystemExit(main())
