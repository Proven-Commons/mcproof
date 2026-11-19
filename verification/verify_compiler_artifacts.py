#!/usr/bin/env python3
"""Independent verification of Phase 2 & Phase 3 compiler artifacts, bindings, and controls."""

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
WARP_SRC = Path(
    os.environ.get("WARP_SRC")
    or (
        (PLANE1_ROOT.parent / "stack" / "worktrees" / "warp" / "src")
        if (PLANE1_ROOT.parent / "stack" / "worktrees" / "warp" / "src").is_dir()
        else (_SC_ROOT / "warp" / "src")
    )
)
sys.path.insert(0, str(WEFT_SRC))

from weft.binding import BindingManifest, RuntimeFlags as WeftRuntimeFlags, verify_binding  # noqa: E402
from weft.certificate import FixedRadixCertificate as Certificate, GatePolicy  # noqa: E402
from weft.slab_wire import verify_slab_wire  # noqa: E402

COMPILE_DIR = Path(os.environ.get("MCPROOF_COMPILE_DIR") or (PLANE1_ROOT / "compile"))
ART_DIR = COMPILE_DIR / "artifacts"
MDE_BIN = Path(os.environ.get("MDE_BIN") or (_SC_ROOT / "mde" / "target" / "debug" / "mde"))
PROSE_GATE = Path(os.environ.get("MCPROOF_CHECK_PROSE") or (PLANE1_ROOT / "src" / "mcproof" / "prose_gate.py"))
RECEIPT_OUT = _VERIF_DIR / "compiler_verification_receipt.json"


def _resolve_repo_or_abs(raw_path: str | Path) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    cand_repo = PLANE1_ROOT / p
    if cand_repo.exists():
        return cand_repo
    return COMPILE_DIR / p


def _resolve_safetensors_dir() -> Path:
    for cand in (
        COMPILE_DIR / "checkpoints" / "Qwen3.5-4B",
        PLANE1_ROOT.parent / "compile" / "checkpoints" / "Qwen3.5-4B",
    ):
        if cand.is_dir():
            return cand
    return COMPILE_DIR / "checkpoints" / "Qwen3.5-4B"


def _resolve_activations_npz() -> Path:
    for cand in (
        ART_DIR / "harvested_activations.npz",
        PLANE1_ROOT.parent / "compile" / "artifacts" / "harvested_activations.npz",
    ):
        if cand.is_file():
            return cand
    return ART_DIR / "harvested_activations.npz"


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
    st_dir = _resolve_safetensors_dir()
    npz_file = _resolve_activations_npz()

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

    p2b = manifest["p2b"]
    p2a = manifest["p2a"]
    hash_checks: list[tuple[str, Path, str]] = [
        ("p2b.gguf_f16", _resolve_repo_or_abs(p2b["gguf_f16_path"]), str(p2b["gguf_f16_sha256"])),
        ("p2b.slab_int4_int8", _resolve_repo_or_abs(p2b["slab_int4_int8_path"]), str(p2b["slab_int4_int8_sha256"])),
        ("p2b.slab_int4_f16", _resolve_repo_or_abs(p2b["slab_int4_f16_path"]), str(p2b["slab_int4_f16_sha256"])),
        ("p2b.slab_f16", _resolve_repo_or_abs(p2b["slab_f16_path"]), str(p2b["slab_f16_sha256"])),
        ("p2a.gguf_f16", _resolve_repo_or_abs(p2a["gguf_f16_path"]), str(p2a["gguf_f16_sha256"])),
        ("p2a.slab_f16", _resolve_repo_or_abs(p2a["slab_f16_path"]), str(p2a["slab_f16_sha256"])),
        ("harvested_activations.npz", npz_file, str(manifest["harvest_summary"]["npz_sha256"])),
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
        hash_checks.append((f"phase6.{dom}.gguf", _resolve_repo_or_abs(pack["gguf_path"]), str(pack["gguf_sha256"])))

    verified_hashes: dict[str, str] = {}
    for label, fpath, exp_sha in hash_checks:
        if not fpath.is_file():
            defects.append(f"missing_artifact:{label}:{fpath.name}")
            continue
        got_sha = sha256_file(fpath)
        verified_hashes[label] = got_sha
        if got_sha != exp_sha:
            defects.append(f"sha256_mismatch:{label}:got_{got_sha}_exp_{exp_sha}")

    bind_file = _resolve_repo_or_abs(p2b["binding_path"])
    cert_file = _resolve_repo_or_abs(p2b["certificate_path"])
    bind_raw = json.loads(bind_file.read_text(encoding="utf-8"))
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
    cert_raw = json.loads(cert_file.read_text(encoding="utf-8"))
    p2b_cert = Certificate(**cert_raw)
    if p2b_cert.sha256() != str(p2b["certificate_sha256"]):
        defects.append(f"canonical_cert_sha256_mismatch:{p2b_cert.sha256()}!={p2b['certificate_sha256']}")
    if bind_obj.sha256() != str(p2b["binding_sha256"]):
        defects.append(f"canonical_binding_sha256_mismatch:{bind_obj.sha256()}!={p2b['binding_sha256']}")
    verified_hashes["p2b.certificate_canonical"] = p2b_cert.sha256()
    verified_hashes["p2b.certificate_file"] = sha256_file(cert_file)
    verified_hashes["p2b.binding_canonical"] = bind_obj.sha256()
    verified_hashes["p2b.binding_file"] = sha256_file(bind_file)
    bind_res = verify_binding(
        bind_obj,
        checkpoint_dir=st_dir,
        runtime_flags=weft_flags,
        plane1_root=PLANE1_ROOT,
        expected_factor_digest=p2b_cert.factor_digest,
        expected_certificate_sha256=p2b_cert.sha256(),
    )
    if not bind_res.ok:
        defects.append(f"verify_binding_failed:{bind_res.problems}")

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
            _resolve_repo_or_abs(p2b[s_key]),
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

    hw_doc = json.loads((ART_DIR / "phase2_hardware_checkpoint_report.json").read_text(encoding="utf-8"))
    probe_block = hw_doc.get("linux_workbench_probe") or hw_doc.get("measured_host_facts", {}).get("linux_workbench_probe", {})
    if bool(probe_block.get("linux_rtx3080_online", False)):
        defects.append("phase2_hardware_checkpoint_report falsely claims linux_rtx3080_online=True while SSH is closed")

    lc_doc = json.loads((ART_DIR / "ablations" / "loud_column_ablation.json").read_text(encoding="utf-8"))
    if len(lc_doc["per_layer_ffn_down_outlier_profile"]) != 32:
        defects.append("loud_column_ablation did not profile all 32 layers")

    py_env = dict(os.environ)
    py_env["PYTHONHASHSEED"] = "0"
    py_env["PYTHONPATH"] = os.pathsep.join([
        str(WEFT_SRC),
        str(WARP_SRC),
        str(_SC_ROOT / "exo" / "src"),
        str(COMPILE_DIR / "src"),
        str(PLANE1_ROOT / "src"),
    ])
    pytest_proc = subprocess.run(
        [sys.executable, "-O", "-B", "-W", "error", "-m", "pytest", str(COMPILE_DIR / "tests"), "-q"],
        cwd=PLANE1_ROOT,
        capture_output=True,
        text=True,
        env=py_env,
        check=False,
    )
    if pytest_proc.returncode != 0:
        defects.append(f"compile_pytest_failed:{pytest_proc.stdout[-400:]}{pytest_proc.stderr[-400:]}")

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
    prose_p1 = subprocess.run([sys.executable, str(PROSE_GATE), str(readme_p)], capture_output=True, text=True, check=False)
    prose_p2 = subprocess.run(
        [sys.executable, str(PROSE_GATE), "--dupes", str(readme_p)], capture_output=True, text=True, check=False
    )
    if prose_p1.returncode != 0 or prose_p2.returncode != 0:
        defects.append(f"compile_readme_prose_failed:{prose_p1.stdout}{prose_p2.stdout}")

    receipt: dict[str, Any] = {
        "schema": "verifier-compiler-verification-receipt/v0.2",
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
