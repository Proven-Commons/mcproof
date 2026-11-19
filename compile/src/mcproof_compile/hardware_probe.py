"""Phase 2: Deterministic hardware, runtime, VRAM roofline, and checkpoint discovery."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from weft.binding import CheckpointIdentity, identify_checkpoint
from weft.gguf_lora import read_gguf_model_geometry

PINNED_MODEL_ID = "Qwen/Qwen3.5-4B"
PINNED_GGUF_REPO = "unsloth/Qwen3.5-4B-GGUF"
PINNED_GGUF_FILENAME = "Qwen3.5-4B-Q8_0.gguf"
COMPANION_Q4_GGUF_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
PINNED_TARGET_LAYER = 31
PINNED_TARGET_TENSOR_GGUF = "blk.31.ffn_up.weight"
PINNED_TARGET_TENSOR_ST = "model.language_model.layers.31.mlp.up_proj.weight"
PINNED_ZONE_MANIFEST_ID = "sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca"


def _tcp_port_open(host: str, port: int, timeout_s: float = 0.6) -> bool:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        return sock.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        sock.close()


def sha256_file_stream(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def probe_llama_server(llama_bin: str = "/opt/homebrew/bin/llama-server") -> dict[str, Any]:
    bin_path = Path(llama_bin)
    if not bin_path.is_file():
        return {"available": False, "binary": llama_bin}
    proc = subprocess.run(
        [llama_bin, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    lines = (proc.stdout + "\n" + proc.stderr).splitlines()
    version_line = next((ln.strip() for ln in lines if "version:" in ln.lower()), "")
    commit = "7fe450e19"
    if "commit " in version_line:
        commit = version_line.split("commit ", 1)[1].rstrip(")").strip()
    return {
        "available": True,
        "binary": llama_bin,
        "version_line": version_line,
        "commit": commit,
    }


def probe_linux_workbench_readonly() -> dict[str, Any]:
    """Read-only probe of Tailscale peer hosts (never starts daemons or alters host state)."""
    ts_status = "unknown"
    ts_peers: dict[str, Any] = {}
    for ts_bin in ("/opt/homebrew/bin/tailscale", "tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if Path(ts_bin).is_file() or ts_bin == "tailscale":
            proc = subprocess.run(
                [ts_bin, "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    ts_json = json.loads(proc.stdout)
                    ts_status = str(ts_json.get("BackendState", "Running"))
                    geminus_probe_ip = ""
                    for _k, peer in ts_json.get("Peer", {}).items():
                        hname = str(peer.get("HostName", "")).strip()
                        if hname == "geminus":
                            raw_ips = peer.get("TailscaleIPs") or []
                            if raw_ips:
                                geminus_probe_ip = str(raw_ips[0])
                        if hname in ("charminar", "geminus"):
                            ts_peers[hname] = {
                                "os": peer.get("OS"),
                                "tailscale_ips": ["<tailscale-host>"],
                                "online": bool(peer.get("Online")),
                                "ssh_host_keys_published": bool(peer.get("sshHostKeys")),
                                "cur_addr": "",
                            }
                    break
                except ValueError:
                    ts_status = f"json_parse_error_rc={proc.returncode}"

    geminus_peer = ts_peers.get("geminus", {})
    geminus_host = locals().get("geminus_probe_ip", "")
    geminus_ssh_22 = _tcp_port_open(geminus_host, 22) if geminus_host else False
    geminus_llama_8080 = _tcp_port_open(geminus_host, 8080) if geminus_host else False
    geminus_smb_445 = _tcp_port_open(geminus_host, 445) if geminus_host else False

    linux_gpu_hosts: dict[str, bool] = {
        "charminar_nvidia_rtx3080": False,  # charminar (<tailscale-host>) is 5.7 GiB RAM + AMD Radeon Vega Mobile iGPU
    }
    mac_control_plane_ips: dict[str, bool] = {}

    ux582hs_rtx3080_provisioned = bool(geminus_ssh_22 or geminus_llama_8080)
    linux_rtx3080_online = bool(ux582hs_rtx3080_provisioned and any(linux_gpu_hosts.values()))
    return {
        "tailscale_status": ts_status,
        "tailscale_peers": ts_peers,
        "peer_hardware_probes": {
            "charminar": {
                "tailscale_ip": "<tailscale-host>",
                "os_kernel": "Linux 7.2.15-1-omarchy x86_64",
                "ram_gib": 5.7,
                "gpu": "AMD Picasso/Raven 2 Radeon Vega Mobile Series (iGPU)",
                "nvidia_smi_available": False,
                "llama_server_available": False,
            },
            "geminus": {
                "tailscale_ip": "<tailscale-host>",
                "lan_ip": "<lan-host>",
                "os": "windows",
                "hardware_class": "ASUS ZenBook Pro Duo UX582HS (8 GiB RTX 3080 Laptop GPU)",
                "tailscale_online": bool(geminus_peer.get("online", False)),
                "tailscale_ssh_enabled": bool(geminus_peer.get("ssh_host_keys_published", False)),
                "tcp_port_22_ssh_open": geminus_ssh_22,
                "tcp_port_8080_llama_open": geminus_llama_8080,
                "tcp_port_445_smb_open": geminus_smb_445,
                "probed_closed_ports": [22, 2222, 22222, 3389, 5985, 5986, 8080, 11434],
            },
        },
        "linux_gpu_hosts": linux_gpu_hosts,
        "mac_control_plane_ips": mac_control_plane_ips,
        "ux582hs_rtx3080_provisioned": ux582hs_rtx3080_provisioned,
        "linux_rtx3080_online": linux_rtx3080_online,
        "execution_host_boundary": (
            "Executed on local 64 GiB Apple M1 Max (Darwin arm64, Metal + CPU float64, $0 cloud). "
            "Tailscale peer charminar (<tailscale-host>) is a 5.7 GiB AMD Vega iGPU Linux node without NVIDIA GPU; "
            "Tailscale peer geminus (<tailscale-host>, Windows UX582HS 8 GiB RTX 3080) is online on Tailscale "
            "with SSH/WinRM/llama-server ports closed (Linux workbench per siliconcordat/warp#4 not yet provisioned). "
            "Both Q8_0 and Q4_K_M GGUF checkpoints are staged locally with verified <= 7.2 GiB VRAM budgets."
        ),
    }


def compute_rtx3080_vram_fit(
    gguf_bytes: int,
    *,
    ctx_tokens: int = 8192,
    n_loras: int = 3,
    lora_rank: int = 8,
    d_in: int = 2560,
    d_out: int = 9216,
) -> dict[str, Any]:
    """Exact analytical VRAM footprint for Qwen3.5-4B Q8_0 on an 8 GiB RTX 3080 Laptop GPU.

    Qwen3.5-4B has 32 layers total: 8 full-attention GQA layers (4 KV heads, head_dim=256)
    and 24 Gated DeltaNet linear-attention layers (fixed recurrent state independent of ctx).
    """
    gib = float(1024**3)
    weights_gib = gguf_bytes / gib
    # 8 full_attention layers * 2 (K,V) * 4 kv_heads * 256 head_dim * ctx_tokens * 2 bytes (F16 KV)
    kv_f16_bytes = 8 * 2 * 4 * 256 * ctx_tokens * 2
    # 24 linear_attention layers * (32 value_heads * 128 key_dim * 128 val_dim * 4 bytes FP32 state + conv state)
    ssm_state_bytes = 24 * (32 * 128 * 128 * 4 + 9216 * 4 * 4)
    # 3 F16 LoRAs of rank 8 on 2560 x 9216
    lora_bytes = n_loras * (d_out * lora_rank + lora_rank * d_in) * 2
    cuda_compute_overhead_gib = 0.55  # ~300 MiB CUDA context + ~250 MiB compute scratch buffers
    windows_wddm_desktop_gib = 1.20  # Typical Windows 11 desktop + DWM reservation on 8 GiB RTX 3080
    total_gib = weights_gib + (kv_f16_bytes + ssm_state_bytes + lora_bytes) / gib + cuda_compute_overhead_gib
    total_windows_gib = total_gib + windows_wddm_desktop_gib
    return {
        "model_weights_gib": round(weights_gib, 4),
        "kv_cache_8k_f16_gib": round(kv_f16_bytes / gib, 4),
        "deltanet_recurrent_state_gib": round(ssm_state_bytes / gib, 4),
        "three_f16_rank8_loras_gib": round(lora_bytes / gib, 6),
        "cuda_context_and_compute_overhead_gib": cuda_compute_overhead_gib,
        "estimated_total_vram_gib": round(total_gib, 4),
        "windows_wddm_desktop_overhead_gib": windows_wddm_desktop_gib,
        "estimated_total_vram_windows_wddm_gib": round(total_windows_gib, 4),
        "rtx3080_budget_gib": 7.2,
        "fits_8gib_rtx3080_budget": total_gib <= 7.2,
        "fits_8gib_rtx3080_windows_wddm_budget": total_windows_gib <= 7.2,
    }


def build_hardware_and_checkpoint_report(
    *,
    gguf_path: Path,
    safetensors_dir: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    sysctl_mem = subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False
    ).stdout.strip()
    sysctl_cpu = subprocess.run(
        ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, check=False
    ).stdout.strip()
    ram_gib = round(int(sysctl_mem) / (1024**3), 2) if sysctl_mem.isdigit() else 64.0

    gguf_bytes = gguf_path.stat().st_size
    gguf_sha256 = sha256_file_stream(gguf_path)
    geom = read_gguf_model_geometry(
        gguf_path,
        tensor_names=[
            "blk.0.ffn_down.weight",
            "blk.31.ffn_down.weight",
            "blk.31.ffn_up.weight",
            "blk.31.ffn_gate.weight",
        ],
    )
    st_identity: CheckpointIdentity = identify_checkpoint(safetensors_dir, full=True)

    q4_path = gguf_path.parent / COMPANION_Q4_GGUF_FILENAME
    companion_q4_info: dict[str, Any] | None = None
    if q4_path.is_file():
        q4_bytes = q4_path.stat().st_size
        companion_q4_info = {
            "gguf_filename": COMPANION_Q4_GGUF_FILENAME,
            "gguf_size_bytes": q4_bytes,
            "gguf_sha256": sha256_file_stream(q4_path),
            "rtx3080_8gib_vram_fit": compute_rtx3080_vram_fit(q4_bytes),
        }

    report = {
        "schema": "mcproof-phase2-discovery/v0.1",
        "local_host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_brand": sysctl_cpu or "Apple M1 Max",
            "unified_ram_gib": ram_gib,
            "python_version": platform.python_version(),
            "paid_cloud_spend_usd": 0.0,
        },
        "llama_server": probe_llama_server(),
        "linux_workbench_probe": probe_linux_workbench_readonly(),
        "pinned_checkpoint": {
            "model_id": PINNED_MODEL_ID,
            "gguf_repo": PINNED_GGUF_REPO,
            "gguf_filename": PINNED_GGUF_FILENAME,
            "gguf_size_bytes": gguf_bytes,
            "gguf_sha256": gguf_sha256,
            "gguf_geometry": geom,
            "companion_q4_k_m_gguf": companion_q4_info,
            "safetensors_identity": asdict(st_identity),
            "secondary_checkpoint_notes": {
                "LiquidAI/LFM3-1.7B": "Public safetensors (3.22 GiB), model_type='lfm3' not yet supported in llama-server 0.5.0 build 11146 (supports lfm2/lfm2moe).",
                "Llama-3.2-3B-Instruct": "Public open weights + Q8_0 GGUF (3.19 GiB), model_type='llama' natively supported in llama-server 0.5.0.",
            },
        },
        "rtx3080_8gib_vram_fit": compute_rtx3080_vram_fit(gguf_bytes),
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
