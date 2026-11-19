"""Phase 2: Deterministic hardware, runtime, analytical VRAM projection, and checkpoint discovery."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import socket
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Sequence

PINNED_MODEL_ID = "Qwen/Qwen3.5-4B"
PINNED_GGUF_REPO = "unsloth/Qwen3.5-4B-GGUF"
PINNED_GGUF_FILENAME = "Qwen3.5-4B-Q8_0.gguf"
COMPANION_Q4_GGUF_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
PINNED_TARGET_LAYER = 31
PINNED_TARGET_TENSOR_GGUF = "blk.31.ffn_up.weight"
PINNED_TARGET_TENSOR_ST = "model.language_model.layers.31.mlp.up_proj.weight"
PINNED_ZONE_MANIFEST_ID = "sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca"

PROBED_WORKBENCH_PORTS: tuple[int, ...] = (22, 445, 2222, 22222, 3389, 5985, 5986, 8080, 11434)
_COMMIT_PARSE_RE = re.compile(r"\bcommit\s+([0-9a-f]{7,64})\b", re.IGNORECASE)

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str] | None]
PortProbe = Callable[[str, int], bool]


def _default_run_cmd(cmd: list[str], timeout_s: float = 5.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        return None


def _sanitize_binary_label(bin_str: str) -> str:
    p = Path(bin_str)
    try:
        home = Path.home().resolve()
        resolved = p.resolve()
        if resolved.is_relative_to(home):
            return f"<user-home>/{resolved.relative_to(home).as_posix()}"
    except OSError:
        resolved = None
    if ("/" + "Users/") in bin_str or "\\Users\\" in bin_str:
        return p.name
    return bin_str


def _tcp_port_open(host: str, port: int, timeout_s: float = 0.25) -> bool:
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


def probe_llama_server(
    llama_bin: str = "/opt/homebrew/bin/llama-server",
    *,
    run_cmd: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = run_cmd or (lambda argv: _default_run_cmd(argv, timeout_s=10.0))
    chosen_bin = llama_bin
    if run_cmd is None and not Path(chosen_bin).is_file():
        found = shutil.which("llama-server")
        if found:
            chosen_bin = found
        else:
            return {
                "available": False,
                "binary": _sanitize_binary_label(chosen_bin),
                "version_line": None,
                "commit": None,
            }

    proc = runner([chosen_bin, "--version"])
    if proc is None:
        return {
            "available": False,
            "binary": _sanitize_binary_label(chosen_bin),
            "version_line": None,
            "commit": None,
        }

    lines = ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines()
    version_line = next((ln.strip() for ln in lines if "version:" in ln.lower()), "")
    commit: str | None = None
    for candidate_line in ([version_line] if version_line else []) + lines:
        match = _COMMIT_PARSE_RE.search(candidate_line)
        if match is not None:
            commit = match.group(1).lower()
            break
    return {
        "available": True,
        "binary": _sanitize_binary_label(chosen_bin),
        "returncode": int(proc.returncode),
        "version_line": version_line or None,
        "commit": commit,
    }


def probe_local_host_facts(
    *,
    run_cmd: CommandRunner | None = None,
    proc_meminfo_path: Path = Path("/proc/meminfo"),
    proc_cpuinfo_path: Path = Path("/proc/cpuinfo"),
) -> dict[str, Any]:
    """Measure local host RAM and CPU without hardcoded machine-model or RAM fallbacks."""
    runner = run_cmd or _default_run_cmd
    ram_gib: float | None = None
    cpu_brand: str | None = None

    mem_proc = runner(["sysctl", "-n", "hw.memsize"])
    if mem_proc is not None and mem_proc.returncode == 0:
        mem_txt = (mem_proc.stdout or "").strip()
        if mem_txt.isdigit():
            ram_gib = round(int(mem_txt) / float(1024**3), 2)

    cpu_proc = runner(["sysctl", "-n", "machdep.cpu.brand_string"])
    if cpu_proc is not None and cpu_proc.returncode == 0:
        cpu_txt = (cpu_proc.stdout or "").strip()
        if cpu_txt:
            cpu_brand = cpu_txt

    if ram_gib is None and run_cmd is None and proc_meminfo_path.is_file():
        try:
            for ln in proc_meminfo_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if ln.startswith("MemTotal:"):
                    parts = ln.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        ram_gib = round((int(parts[1]) * 1024) / float(1024**3), 2)
                    break
        except OSError:
            ram_gib = None

    if cpu_brand is None and run_cmd is None and proc_cpuinfo_path.is_file():
        try:
            for ln in proc_cpuinfo_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if ":" in ln and ln.lower().startswith("model name"):
                    val = ln.split(":", 1)[1].strip()
                    if val:
                        cpu_brand = val
                        break
        except OSError:
            cpu_brand = None

    if cpu_brand is None and run_cmd is None:
        proc_str = platform.processor().strip()
        cpu_brand = proc_str or None

    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_brand": cpu_brand,
        "unified_ram_gib": ram_gib,
        "python_version": platform.python_version(),
    }


def _redact_tailscale_ip_list(raw_ips: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for ip_val in raw_ips:
        s = str(ip_val).strip()
        if not s:
            continue
        if ":" in s:
            if "<tailscale-ipv6>" not in out:
                out.append("<tailscale-ipv6>")
        else:
            if "<tailscale-host>" not in out:
                out.append("<tailscale-host>")
    return out or ["<tailscale-host>"]


def _pick_ipv4(raw_ips: Sequence[Any]) -> str:
    for ip_val in raw_ips:
        s = str(ip_val).strip()
        if s and ":" not in s:
            return s
    return ""


def probe_linux_workbench_readonly(
    *,
    run_cmd: CommandRunner | None = None,
    port_probe: PortProbe | None = None,
    ports_to_probe: Sequence[int] = PROBED_WORKBENCH_PORTS,
    tailscale_candidates: Sequence[str] = (
        "/opt/homebrew/bin/tailscale",
        "tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ),
) -> dict[str, Any]:
    """Read-only probe of Tailscale peer reachability separating measured facts from static notes."""
    runner = run_cmd or _default_run_cmd
    tcp_check = port_probe or (lambda host, port: _tcp_port_open(host, port, timeout_s=0.25))
    ordered_ports = [int(p) for p in ports_to_probe]

    ts_status = "unavailable"
    ts_peers: dict[str, dict[str, Any]] = {}
    peer_ipv4_in_memory: dict[str, str] = {}

    for ts_bin in tailscale_candidates:
        proc = runner([ts_bin, "status", "--json"])
        if proc is None:
            continue
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            ts_status = f"command_failed_rc={proc.returncode}"
            continue
        try:
            ts_json = json.loads(proc.stdout)
        except ValueError:
            ts_status = f"json_parse_error_rc={proc.returncode}"
            continue

        ts_status = str(ts_json.get("BackendState", "Running"))
        peer_map = ts_json.get("Peer")
        if isinstance(peer_map, dict):
            for _k, peer in peer_map.items():
                if not isinstance(peer, dict):
                    continue
                hname = str(peer.get("HostName", "")).strip()
                if not hname:
                    continue
                raw_ips = peer.get("TailscaleIPs")
                ip_list = raw_ips if isinstance(raw_ips, list) else []
                ipv4 = _pick_ipv4(ip_list)
                if ipv4:
                    peer_ipv4_in_memory[hname] = ipv4
                if hname in ("charminar", "geminus"):
                    ts_peers[hname] = {
                        "os": str(peer.get("OS") or "").strip().lower() or None,
                        "tailscale_ips": _redact_tailscale_ip_list(ip_list),
                        "online": bool(peer.get("Online", False)),
                        "ssh_host_keys_published": bool(peer.get("sshHostKeys")),
                    }
        break

    peer_port_probes: dict[str, dict[str, Any]] = {}
    for peer_name in sorted(ts_peers.keys()):
        peer_info = ts_peers[peer_name]
        ipv4 = peer_ipv4_in_memory.get(peer_name, "")
        port_status_map: dict[str, bool] = {}
        open_ports: list[int] = []
        closed_ports: list[int] = []
        ports_actually_probed: list[int] = []
        if ipv4:
            for port in ordered_ports:
                is_open = bool(tcp_check(ipv4, port))
                ports_actually_probed.append(port)
                port_status_map[str(port)] = is_open
                if is_open:
                    open_ports.append(port)
                else:
                    closed_ports.append(port)
        peer_port_probes[peer_name] = {
            "tailscale_ip": "<tailscale-host>",
            "tailscale_os": peer_info["os"],
            "tailscale_online": peer_info["online"],
            "tailscale_ssh_keys_published": peer_info["ssh_host_keys_published"],
            "ports_probed": ports_actually_probed,
            "port_open_map": port_status_map,
            "probed_open_ports": open_ports,
            "probed_closed_ports": closed_ports,
        }

    geminus_probe = peer_port_probes.get("geminus", {})
    geminus_open = set(geminus_probe.get("probed_open_ports", ()))
    geminus_online = bool(geminus_probe.get("tailscale_online", False))
    geminus_os = str(geminus_probe.get("tailscale_os") or "").lower()

    ux582hs_rtx3080_provisioned = bool(geminus_online and (22 in geminus_open or 8080 in geminus_open))
    linux_rtx3080_online = bool(ux582hs_rtx3080_provisioned and geminus_os == "linux")

    measured_facts = {
        "tailscale_status": ts_status,
        "tailscale_peers": ts_peers,
        "peer_port_probes": peer_port_probes,
        "ux582hs_rtx3080_provisioned": ux582hs_rtx3080_provisioned,
        "linux_rtx3080_online": linux_rtx3080_online,
    }
    static_notes = {
        "peer_inventory_notes": {
            "charminar": (
                "Operator inventory note (not probed via SSH here): x86_64 Linux node with AMD Radeon Vega "
                "Mobile iGPU and 5.7 GiB RAM; no NVIDIA RTX 3080 GPU."
            ),
            "geminus": (
                "Operator inventory note (not probed via SSH here): ASUS ZenBook Pro Duo UX582HS with "
                "8 GiB NVIDIA RTX 3080 Laptop GPU; Linux workbench provisioning tracked in siliconcordat/warp#4."
            ),
        },
        "cloud_policy_note": "Zero paid cloud compute policy enforced by operator configuration.",
    }
    return {
        "measured_host_facts": measured_facts,
        "static_reference_notes": static_notes,
        "tailscale_status": ts_status,
        "tailscale_peers": ts_peers,
        "peer_port_probes": peer_port_probes,
        "ux582hs_rtx3080_provisioned": ux582hs_rtx3080_provisioned,
        "linux_rtx3080_online": linux_rtx3080_online,
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
    """Analytical VRAM projection for Qwen3.5-4B on an 8 GiB RTX 3080 Laptop GPU (not live NVML).

    Qwen3.5-4B has 32 layers total: 8 full-attention GQA layers (4 KV heads, head_dim=256)
    and 24 Gated DeltaNet linear-attention layers (fixed recurrent state independent of ctx).
    """
    gib = float(1024**3)
    weights_gib = gguf_bytes / gib
    kv_f16_bytes = 8 * 2 * 4 * 256 * ctx_tokens * 2
    ssm_state_bytes = 24 * (32 * 128 * 128 * 4 + 9216 * 4 * 4)
    lora_bytes = n_loras * (d_out * lora_rank + lora_rank * d_in) * 2
    cuda_compute_overhead_gib = 0.55
    windows_wddm_desktop_gib = 1.20
    total_gib = weights_gib + (kv_f16_bytes + ssm_state_bytes + lora_bytes) / gib + cuda_compute_overhead_gib
    total_windows_gib = total_gib + windows_wddm_desktop_gib
    return {
        "measurement_kind": "analytical_projection_not_live_nvml",
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
    llama_bin: str = "/opt/homebrew/bin/llama-server",
) -> dict[str, Any]:
    from weft.binding import CheckpointIdentity, identify_checkpoint
    from weft.gguf_lora import read_gguf_model_geometry

    local_facts = probe_local_host_facts()
    llama_facts = probe_llama_server(llama_bin=llama_bin)
    workbench_probe = probe_linux_workbench_readonly()

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
            "analytical_rtx3080_8gib_vram_projection": compute_rtx3080_vram_fit(q4_bytes),
        }

    vram_projection = compute_rtx3080_vram_fit(gguf_bytes)
    measured_host_facts = {
        "local_host": local_facts,
        "llama_server": llama_facts,
        "tailscale_workbench_probe": workbench_probe["measured_host_facts"],
        "checkpoint_digests": {
            "model_id": PINNED_MODEL_ID,
            "gguf_filename": PINNED_GGUF_FILENAME,
            "gguf_size_bytes": gguf_bytes,
            "gguf_sha256": gguf_sha256,
            "gguf_geometry": geom,
            "safetensors_identity": asdict(st_identity),
        },
    }
    static_reference_notes = {
        "workbench_notes": workbench_probe["static_reference_notes"],
        "secondary_checkpoint_notes": {
            "LiquidAI/LFM3-1.7B": "Public safetensors (3.22 GiB); model_type='lfm3' unsupported by llama-server 0.5.0 build 11146.",
            "Llama-3.2-3B-Instruct": "Public open weights + Q8_0 GGUF (3.19 GiB); model_type='llama' supported by llama-server 0.5.0.",
        },
        "analytical_rtx3080_8gib_vram_projection": vram_projection,
    }

    report = {
        "schema": "mcproof-phase2-discovery/v0.2",
        "measured_host_facts": measured_host_facts,
        "static_reference_notes": static_reference_notes,
        "local_host": local_facts,
        "llama_server": llama_facts,
        "linux_workbench_probe": workbench_probe,
        "pinned_checkpoint": {
            "model_id": PINNED_MODEL_ID,
            "gguf_repo": PINNED_GGUF_REPO,
            "gguf_filename": PINNED_GGUF_FILENAME,
            "gguf_size_bytes": gguf_bytes,
            "gguf_sha256": gguf_sha256,
            "gguf_geometry": geom,
            "companion_q4_k_m_gguf": companion_q4_info,
            "safetensors_identity": asdict(st_identity),
        },
        "rtx3080_8gib_vram_fit": vram_projection,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
