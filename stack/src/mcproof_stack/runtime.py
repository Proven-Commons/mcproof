"""Runtime discovery, real llama-server 0.5.0 lifecycle, and deterministic weft adapter registry."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
from typing import Any, BinaryIO, Mapping, Sequence
import urllib.error
import urllib.request

import numpy as np

STACK_ROOT = Path(__file__).resolve().parents[2]
if (STACK_ROOT.parent / "spec" / "lineage.json").is_file():
    MCPROOF_REPO_ROOT = STACK_ROOT.parent
    LAB_ROOT = MCPROOF_REPO_ROOT.parent
else:
    LAB_ROOT = STACK_ROOT.parent
    MCPROOF_REPO_ROOT = LAB_ROOT / "repo"
SILICONCORDAT_ROOT = LAB_ROOT.parent / "siliconcordat"

DOMAIN_TO_LLAMA_ID: dict[str, int] = {
    "corpus": 0,
    "weft-eido": 1,
    "formal-verification": 2,
}

GGUF_MAGIC = b"GGUF"
GGUF_VERSION = 3

# Standard llama.cpp `llama_ftype` values stored in GGUF `general.file_type`.
GGUF_FILE_TYPE_TO_QUANTIZATION: dict[int, str] = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    7: "Q8_0",
    8: "Q5_0",
    9: "Q5_1",
    10: "Q2_K",
    11: "Q3_K_S",
    12: "Q3_K_M",
    13: "Q3_K_L",
    14: "Q4_K_S",
    15: "Q4_K_M",
    16: "Q5_K_S",
    17: "Q5_K_M",
    18: "Q6_K",
    19: "IQ2_XXS",
    20: "IQ2_XS",
    21: "Q2_K_S",
    22: "IQ3_XS",
    23: "IQ3_XXS",
    24: "IQ1_S",
    25: "IQ4_NL",
    26: "IQ3_S",
    27: "IQ3_M",
    28: "IQ2_S",
    29: "IQ2_M",
    30: "IQ4_XS",
    31: "IQ1_M",
    32: "BF16",
}

_GGUF_SCALAR_FORMATS: dict[int, tuple[int, str]] = {
    0: (1, "<B"),
    1: (1, "<b"),
    2: (2, "<H"),
    3: (2, "<h"),
    4: (4, "<I"),
    5: (4, "<i"),
    6: (4, "<f"),
    7: (1, "<?"),
    10: (8, "<Q"),
    11: (8, "<q"),
    12: (8, "<d"),
}

_COMMIT_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_HOME_PATH_RE = re.compile(r"/(?:Users|home)/[^/,\s:\"]+")
_TMP_PATH_RE = re.compile(r"(?:/private)?/var/folders/[^/]+/[^/]+/T/[^/,\s:\"]+|(?:/private)?/tmp/[^/,\s:\"]+")


def ensure(condition: bool, message: str) -> None:
    """Fail-closed runtime invariant check (never stripped under python3 -O)."""
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def sanitize_receipt_paths(payload: Any) -> Any:
    """Scrub workstation home, lab root, and ephemeral temp paths from receipt objects."""
    if isinstance(payload, Mapping):
        return {str(k): sanitize_receipt_paths(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [sanitize_receipt_paths(v) for v in payload]
    if isinstance(payload, tuple):
        return [sanitize_receipt_paths(v) for v in payload]
    if isinstance(payload, str):
        s = payload
        repo_prefix = str(MCPROOF_REPO_ROOT.resolve()) + "/"
        if repo_prefix in s:
            s = s.replace(repo_prefix, "")
        lab_prefix = str(LAB_ROOT.resolve())
        if lab_prefix and lab_prefix != "/" and lab_prefix in s:
            s = s.replace(lab_prefix, "<workspace>/mcproof-lab")
        s = _TMP_PATH_RE.sub("<tmpdir>", s)
        s = _HOME_PATH_RE.sub("<workspace>", s)
        return s
    return payload


def _read_exact_gguf(fh: BinaryIO, n: int) -> bytes:
    raw = fh.read(n)
    if len(raw) != n:
        raise ValueError(f"Truncated GGUF header (expected {n} bytes, got {len(raw)})")
    return raw


def _read_gguf_string(fh: BinaryIO, *, max_len: int = 16 * 1024 * 1024) -> str:
    (slen,) = struct.unpack("<Q", _read_exact_gguf(fh, 8))
    if slen > max_len:
        raise ValueError(f"GGUF string length exceeds safety cap: {slen}")
    return _read_exact_gguf(fh, slen).decode("utf-8", errors="replace")


def _read_or_skip_gguf_value(fh: BinaryIO, vtype: int, *, keep: bool, file_size: int) -> Any:
    if vtype in _GGUF_SCALAR_FORMATS:
        nbytes, fmt = _GGUF_SCALAR_FORMATS[vtype]
        raw = _read_exact_gguf(fh, nbytes)
        if not keep:
            return None
        val = struct.unpack(fmt, raw)[0]
        if vtype == 7:
            return bool(val)
        if vtype in (6, 12):
            return float(val)
        return int(val)
    if vtype == 8:  # GGUF_TYPE_STRING
        if keep:
            return _read_gguf_string(fh)
        (slen,) = struct.unpack("<Q", _read_exact_gguf(fh, 8))
        if fh.tell() + slen > file_size:
            raise ValueError("GGUF string extends past EOF")
        fh.seek(slen, 1)
        return None
    if vtype == 9:  # GGUF_TYPE_ARRAY
        elem_type, count = struct.unpack("<IQ", _read_exact_gguf(fh, 12))
        if count > 1_000_000:
            raise ValueError(f"GGUF array count exceeds safety cap: {count}")
        if elem_type in _GGUF_SCALAR_FORMATS:
            skip = _GGUF_SCALAR_FORMATS[elem_type][0] * count
            if fh.tell() + skip > file_size:
                raise ValueError("GGUF scalar array extends past EOF")
            fh.seek(skip, 1)
            return f"<array:{count}>" if keep else None
        if elem_type == 8:
            for _ in range(count):
                (slen,) = struct.unpack("<Q", _read_exact_gguf(fh, 8))
                if fh.tell() + slen > file_size:
                    raise ValueError("GGUF string array extends past EOF")
                fh.seek(slen, 1)
            return f"<str_array:{count}>" if keep else None
        for _ in range(count):
            _read_or_skip_gguf_value(fh, elem_type, keep=False, file_size=file_size)
        return f"<nested_array:{count}>" if keep else None
    raise ValueError(f"Unsupported GGUF metadata value type: {vtype}")


def read_gguf_header_metadata(path: str | Path) -> dict[str, Any]:
    """Read GGUF v3 header KV metadata and derive `has_ssm` without loading tensor payloads."""
    gguf_path = Path(path)
    if not gguf_path.is_file():
        raise FileNotFoundError(f"GGUF file not found: {gguf_path}")
    file_size = gguf_path.stat().st_size
    with gguf_path.open("rb") as fh:
        magic, version, n_tensors, n_kv = struct.unpack("<4sIQQ", _read_exact_gguf(fh, 24))
        if magic != GGUF_MAGIC:
            raise ValueError(f"Invalid GGUF magic in {gguf_path.name}: {magic!r}")
        if version != GGUF_VERSION:
            raise ValueError(f"Unsupported GGUF version in {gguf_path.name}: {version}")
        if n_tensors > 100_000 or n_kv > 100_000:
            raise ValueError(f"GGUF header counts exceed safety cap: tensors={n_tensors}, kv={n_kv}")

        meta: dict[str, Any] = {}
        for _ in range(n_kv):
            key = _read_gguf_string(fh)
            (vtype,) = struct.unpack("<I", _read_exact_gguf(fh, 4))
            keep = not key.startswith("tokenizer.")
            val = _read_or_skip_gguf_value(fh, vtype, keep=keep, file_size=file_size)
            if keep:
                meta[key] = val

    arch = str(meta.get("general.architecture", "unknown"))
    has_ssm_keys = any(".ssm." in k or k.endswith(".ssm") or k.startswith("ssm.") for k in meta)
    explicit_ssm = meta.get("has_ssm") if type(meta.get("has_ssm")) is bool else False
    meta["has_ssm"] = bool(explicit_ssm or has_ssm_keys or arch in ("qwen35", "qwen3_5", "qwen3next"))
    meta["_n_tensors"] = int(n_tensors)
    return meta


def parse_gguf_quantization(gguf_or_meta: str | Path | Mapping[str, Any]) -> str:
    """Parse quantization string strictly from GGUF `general.file_type` header enum (fail closed)."""
    meta = (
        read_gguf_header_metadata(gguf_or_meta)
        if isinstance(gguf_or_meta, (str, Path))
        else gguf_or_meta
    )
    raw_ft = meta.get("general.file_type")
    if type(raw_ft) is not int:
        raise ValueError(
            f"GGUF header missing integer 'general.file_type' metadata (got {raw_ft!r}); refusing filename guess"
        )
    quant = GGUF_FILE_TYPE_TO_QUANTIZATION.get(raw_ft)
    if quant is None:
        raise ValueError(
            f"Unknown GGUF general.file_type enum value {raw_ft}; refusing filename guess"
        )
    return quant


@dataclass(frozen=True)
class StackPaths:
    """Resolved paths across isolated worktrees and read-only sibling repositories."""

    stack_root: Path
    mde_bin: Path
    zone_manifest_path: Path
    exo_src: Path
    warp_src: Path
    weft_src: Path
    weft_eido_root: Path
    llama_server_bin: Path
    synthetic_canaries_path: Path
    default_base_gguf: Path
    default_safetensors_dir: Path | None

    @classmethod
    def discover(cls, *, base_gguf_override: str | Path | None = None) -> StackPaths:
        raw_mde = os.environ.get("MDE_BIN")
        if raw_mde:
            mde_bin = Path(raw_mde).expanduser().resolve()
        else:
            mde_bin = SILICONCORDAT_ROOT / "mde" / "target" / "debug" / "mde"
        ensure(mde_bin.is_file(), f"mde binary not found at {mde_bin}")

        zone_manifest_path = Path(
            os.environ.get(
                "MDE_ZONE_MANIFEST",
                str(SILICONCORDAT_ROOT / "mde" / "schemas" / "zone-manifest.v0.1.json"),
            )
        ).resolve()
        ensure(zone_manifest_path.is_file(), f"zone-manifest.v0.1.json not found at {zone_manifest_path}")

        wt_base = (
            (STACK_ROOT / "worktrees")
            if (STACK_ROOT / "worktrees").is_dir()
            else (LAB_ROOT / "stack" / "worktrees")
        )
        exo_src = (
            (wt_base / "exo" / "src").resolve()
            if (wt_base / "exo" / "src").is_dir()
            else (SILICONCORDAT_ROOT / "exo" / "src").resolve()
        )
        warp_src = (
            (wt_base / "warp" / "src").resolve()
            if (wt_base / "warp" / "src").is_dir()
            else (SILICONCORDAT_ROOT / "warp" / "src").resolve()
        )
        weft_src = Path(os.environ.get("WEFT_SRC", str(SILICONCORDAT_ROOT / "weft" / "src"))).resolve()
        weft_eido_root = (
            (wt_base / "weft-eido").resolve()
            if (wt_base / "weft-eido").is_dir()
            else (LAB_ROOT / "deps" / "weft-eido").resolve()
        )
        for p, label in (
            (exo_src, "worktrees/exo/src"),
            (warp_src, "worktrees/warp/src"),
            (weft_src, "weft/src"),
            (weft_eido_root, "worktrees/weft-eido"),
        ):
            ensure(p.is_dir(), f"required directory missing ({label}): {p}")

        raw_llama = os.environ.get("LLAMA_SERVER_BIN") or "/opt/homebrew/bin/llama-server"
        resolved_llama = shutil.which(raw_llama) if "/" not in raw_llama else raw_llama
        ensure(resolved_llama is not None and Path(resolved_llama).is_file(), f"llama-server missing: {raw_llama}")
        llama_server_bin = Path(str(resolved_llama)).resolve()

        synthetic_canaries_path = (STACK_ROOT / "configs" / "synthetic_host_canaries_16.json").resolve()
        ensure(synthetic_canaries_path.is_file(), f"synthetic canaries missing: {synthetic_canaries_path}")

        if base_gguf_override is not None:
            base_gguf = Path(base_gguf_override).expanduser().resolve()
        elif os.environ.get("MCPROOF_BASE_GGUF"):
            base_gguf = Path(os.environ["MCPROOF_BASE_GGUF"]).expanduser().resolve()
        else:
            qwen35_gguf = (
                LAB_ROOT / "compile" / "checkpoints" / "Qwen3.5-4B-GGUF" / "Qwen3.5-4B-Q8_0.gguf"
            )
            ensure(
                qwen35_gguf.is_file(),
                f"expected Qwen3.5-4B GGUF checkpoint missing at {qwen35_gguf}; "
                "pass explicit --base-gguf or set MCPROOF_BASE_GGUF",
            )
            base_gguf = qwen35_gguf.resolve()
        ensure(base_gguf.is_file(), f"base GGUF checkpoint not found: {base_gguf}")

        st_candidate = LAB_ROOT / "compile" / "checkpoints" / "Qwen3.5-4B"
        st_dir = st_candidate.resolve() if st_candidate.is_dir() else None

        return cls(
            stack_root=STACK_ROOT,
            mde_bin=mde_bin,
            zone_manifest_path=zone_manifest_path,
            exo_src=exo_src,
            warp_src=warp_src,
            weft_src=weft_src,
            weft_eido_root=weft_eido_root,
            llama_server_bin=llama_server_bin,
            synthetic_canaries_path=synthetic_canaries_path,
            default_base_gguf=base_gguf,
            default_safetensors_dir=st_dir,
        )

    def inject_sys_path(self) -> None:
        """Ensure isolated worktree packages (exo, warp), weft, and mcproof oracles are importable."""
        for src_dir in (self.weft_src, self.warp_src, self.exo_src):
            s = str(src_dir)
            if s in sys.path:
                sys.path.remove(s)
            sys.path.insert(0, s)
        repo_src = (MCPROOF_REPO_ROOT / "src").resolve()
        if repo_src.is_dir() and str(repo_src) not in sys.path:
            sys.path.append(str(repo_src))


def load_canary_suite(paths: StackPaths, canary_path: str | Path | None, *, min_preservation: int = 8) -> tuple[Any, str]:
    """Load verifier CanarySuite from either .json (warp_canaries_*.json) or .jsonl (canaries_16.jsonl).

    Honors caller's `min_preservation` without silent weakening for explicit canary files.
    """
    ensure(type(min_preservation) is int and min_preservation >= 1, "min_preservation must be a positive int")
    paths.inject_sys_path()
    from warp_modeld.canary import CanarySuite

    if canary_path is None:
        return (
            CanarySuite.from_verifier_file(paths.synthetic_canaries_path, min_preservation=min_preservation),
            "synthetic_host_16",
        )
    resolved = Path(canary_path).expanduser().resolve()
    if resolved.suffix.lower() == ".jsonl":
        return CanarySuite.from_jsonl_file(resolved, min_preservation=min_preservation), f"jsonl:{resolved.name}"
    return CanarySuite.from_verifier_file(resolved, min_preservation=min_preservation), f"json:{resolved.name}"


def build_canary_command(
    paths: StackPaths,
    canary_path: str | Path | None = None,
    *,
    min_preservation: int = 8,
    max_tokens: int = 80,
) -> list[str]:
    """Build an opaque Stage 3 canary command emitting full per-canary `outcomes` with >= `min_preservation` items."""
    ensure(type(min_preservation) is int and min_preservation >= 1, "min_preservation must be a positive int")
    suite_file = (
        Path(canary_path).expanduser().resolve()
        if canary_path is not None
        else paths.synthetic_canaries_path
    )
    ensure(suite_file.is_file(), f"canary file missing for build_canary_command: {suite_file}")
    script = (
        "import json, sys\n"
        f"sys.path[:0] = [{str(paths.warp_src)!r}]\n"
        "from pathlib import Path\n"
        "from warp_modeld.canary import CanarySuite\n"
        "from warp_modeld.llama_client import LlamaServerClient\n"
        "suite_p = Path(sys.argv[1])\n"
        "min_pres = int(sys.argv[2])\n"
        "max_tok = int(sys.argv[3])\n"
        "url = sys.argv[4]\n"
        "lora = json.loads(sys.argv[5])\n"
        "domains = json.loads(sys.argv[6])\n"
        "slot_id = int(sys.argv[7])\n"
        "suite = CanarySuite.from_jsonl_file(suite_p, min_preservation=min_pres) if suite_p.suffix.lower() == '.jsonl' "
        "else CanarySuite.from_verifier_file(suite_p, min_preservation=min_pres)\n"
        "selected = suite.select_for_domains(domains)\n"
        "client = LlamaServerClient(url, timeout_seconds=30.0, require_localhost=True)\n"
        "outcomes = []\n"
        "pres_total = 0\n"
        "pres_passed = 0\n"
        "for spec in selected:\n"
        "    client.erase_slot(slot_id)\n"
        "    msgs = ([{'role': 'system', 'content': spec.system_prompt}] if spec.system_prompt else []) + "
        "[{'role': 'user', 'content': spec.prompt}]\n"
        "    resp = client.chat_completion(msgs, lora=lora, temperature=0.0, top_p=1.0, seed=42, "
        "max_tokens=spec.max_tokens or max_tok, cache_prompt=False, id_slot=slot_id)\n"
        "    txt = resp['choices'][0]['message']['content']\n"
        "    fails = spec.evaluate(txt)\n"
        "    ok = len(fails) == 0\n"
        "    if spec.category == 'preservation':\n"
        "        pres_total += 1\n"
        "        if ok:\n"
        "            pres_passed += 1\n"
        "    outcomes.append({'canary_id': spec.canary_id, 'category': spec.category, 'passed': ok, 'failures': fails})\n"
        "client.erase_slot(slot_id)\n"
        "all_ok = pres_total >= min_pres and pres_passed == pres_total and all(o['passed'] for o in outcomes)\n"
        "print(json.dumps({'suite_sha256': suite.suite_sha256, 'passed': all_ok, "
        "'preservation_passed': pres_passed, 'preservation_total': pres_total, 'outcomes': outcomes}))\n"
        "raise SystemExit(0 if all_ok else 1)\n"
    )
    return [
        sys.executable,
        "-c",
        script,
        str(suite_file),
        str(min_preservation),
        str(int(max_tokens)),
        "{server_url}",
        "{lora_json}",
        "{domains_json}",
        "{slot_id}",
    ]


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def parse_llama_server_version_output(combined_output: str) -> dict[str, str]:
    """Extract `version_line` and `commit` from `llama-server --version` output; fail closed if missing."""
    version_line: str | None = None
    commit: str | None = None
    for line in combined_output.splitlines():
        if "version:" in line.lower():
            version_line = line.strip()
            if "commit " in line:
                candidate = line.split("commit ", 1)[1].rstrip(")").strip()
                if candidate and _COMMIT_TOKEN_RE.match(candidate):
                    commit = candidate.lower()
            break
    ensure(
        version_line is not None and commit is not None,
        f"failed to parse commit from llama-server --version output: {combined_output.strip()!r}",
    )
    return {"version_line": str(version_line), "commit": str(commit)}


def query_llama_server_version(llama_bin: Path) -> dict[str, str]:
    proc = subprocess.run(
        [str(llama_bin), "--version"],
        capture_output=True,
        text=True,
        timeout=25.0,
        check=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ensure(
        proc.returncode == 0,
        f"llama-server --version exited with code {proc.returncode}: {combined.strip()}",
    )
    return parse_llama_server_version_output(combined)


def measure_process_rss_mib(pid: int) -> float:
    proc = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0 or not raw:
        return 0.0
    try:
        rss_kib = int(raw.splitlines()[0].strip())
    except ValueError:
        return 0.0
    return round(rss_kib / 1024.0, 2)


class LiveLlamaProcess:
    """Context-managed real `llama-server 0.5.0` instance with fail-closed Phase 4 flags."""

    def __init__(
        self,
        *,
        llama_bin: Path,
        base_gguf: Path,
        adapter_paths: Sequence[Path],
        slot_save_dir: Path,
        ctx_size: int = 8192,
        n_gpu_layers: int = 99,
        parallel_slots: int = 1,
        disable_thinking: bool = True,
        kv_cache_type: str = "f16",
    ) -> None:
        self.llama_bin = llama_bin
        self.base_gguf = base_gguf
        self.adapter_paths = tuple(Path(p).resolve() for p in adapter_paths)
        self.slot_save_dir = slot_save_dir.resolve()
        self.ctx_size = int(ctx_size)
        self.n_gpu_layers = int(n_gpu_layers)
        self.parallel_slots = int(parallel_slots)
        self.disable_thinking = bool(disable_thinking)
        self.kv_cache_type = str(kv_cache_type)
        self.port = pick_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen[str] | None = None
        self._log_fh: Any | None = None
        self.log_path: Path = self.slot_save_dir.parent / f"llama_server_{self.port}.log"
        self.boot_ms: float = 0.0
        self.cli_args: list[str] = []

    def build_command(self) -> list[str]:
        self.slot_save_dir.mkdir(parents=True, exist_ok=True)
        total_ctx = int(self.ctx_size) * max(1, int(self.parallel_slots))
        cmd = [
            str(self.llama_bin),
            "-m",
            str(self.base_gguf),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "-c",
            str(total_ctx),
            "-ngl",
            str(self.n_gpu_layers),
            "-np",
            str(self.parallel_slots),
            "--cache-type-k",
            self.kv_cache_type,
            "--cache-type-v",
            self.kv_cache_type,
            "--slots",
            "--slot-save-path",
            str(self.slot_save_dir),
            "--no-cache-idle-slots",
            "--slot-prompt-similarity",
            "0.0",
            "--ctx-checkpoints",
            "0",
        ]
        if self.disable_thinking:
            cmd.extend(["--chat-template-kwargs", '{"enable_thinking":false}'])
        if self.adapter_paths:
            scaled_spec = ",".join(f"{p}:0.0" for p in self.adapter_paths)
            cmd.extend(["--lora-scaled", scaled_spec, "--lora-init-without-apply"])
        self.cli_args = cmd
        return cmd

    def start(self, *, timeout_s: float = 90.0) -> str:
        cmd = self.build_command()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = self.log_path.open("w", encoding="utf-8")
        t0 = time.perf_counter()
        self.proc = subprocess.Popen(
            cmd,
            stdout=self._log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                rc = self.proc.returncode
                self.stop()
                tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-1500:] if self.log_path.is_file() else ""
                raise RuntimeError(f"llama-server exited early ({rc}):\n{tail}")
            try:
                with urllib.request.urlopen(f"{self.base_url}/health", timeout=0.75) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read().decode("utf-8"))
                        if isinstance(payload, dict) and payload.get("status") == "ok":
                            self.boot_ms = (time.perf_counter() - t0) * 1000.0
                            return self.base_url
            except urllib.error.HTTPError as he:
                he.close()
                time.sleep(0.15)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                time.sleep(0.15)

        self.stop()
        tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-1500:] if self.log_path.is_file() else ""
        raise RuntimeError(f"timed out after {timeout_s}s waiting for llama-server /health at {self.base_url}:\n{tail}")

    @property
    def rss_mib(self) -> float:
        if self.proc is None or self.proc.poll() is not None:
            return 0.0
        return measure_process_rss_mib(self.proc.pid)

    def stop(self) -> None:
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
            self.proc = None
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            except OSError as exc:
                sys.stderr.write(f"warning: failed closing llama log file: {exc}\n")
            self._log_fh = None

    def __enter__(self) -> LiveLlamaProcess:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()


def assert_nonempty_completion_probs(
    probs: Sequence[Mapping[str, Any]],
    *,
    label: str = "completion_probabilities",
) -> None:
    """Fail-closed check ensuring non-empty completion probabilities with step-0 top_logprobs."""
    if not isinstance(probs, Sequence) or isinstance(probs, (str, bytes)) or len(probs) == 0:
        raise ValueError(f"{label} must be a non-empty list of token probability entries")
    top0 = probs[0].get("top_logprobs")
    if not isinstance(top0, Sequence) or isinstance(top0, (str, bytes)) or len(top0) == 0:
        raise ValueError(f"{label}[0] is missing non-empty top_logprobs")


def step0_logprob_shift(probs_a: Sequence[Mapping[str, Any]], probs_b: Sequence[Mapping[str, Any]]) -> float:
    """Finite step-0 logprob shift even when greedy token trajectories diverge.

    Raises `ValueError` when either probability list or step-0 `top_logprobs` is empty.
    """
    assert_nonempty_completion_probs(probs_a, label="probs_a")
    assert_nonempty_completion_probs(probs_b, label="probs_b")
    p0_a = probs_a[0]
    p0_b = probs_b[0]
    if int(p0_a["id"]) == int(p0_b["id"]):
        return abs(float(p0_a["logprob"]) - float(p0_b["logprob"]))
    ref_id = int(p0_b["id"])
    for cand in p0_a["top_logprobs"]:
        if isinstance(cand, Mapping) and int(cand.get("id", -1)) == ref_id:
            return abs(float(cand["logprob"]) - float(p0_b["logprob"]))
    return abs(float(p0_a["logprob"]) - float(p0_b["logprob"])) + 1.0


def compute_mcproof_plane1_tree_sha256(
    tracked_hashes: Mapping[str, str],
    upstream_repos: Mapping[str, Any],
    zone_manifest_id: str,
) -> str:
    """Compute canonical mcproof-plane1-tree/v0.1 SHA-256 matching repo/src/mcproof/lineage.py."""
    upstream_commits = {
        repo_name: str(info["commit"])
        for repo_name, info in sorted(upstream_repos.items())
    }
    envelope = {
        "schema": "mcproof-plane1-tree/v0.1",
        "zone_manifest_id": zone_manifest_id,
        "tracked_plane1_files": dict(sorted(tracked_hashes.items())),
        "upstream_commits": upstream_commits,
    }
    return sha256_json(envelope)


def max_logprob_diff(probs_a: Sequence[Mapping[str, Any]], probs_b: Sequence[Mapping[str, Any]]) -> float:
    """Compute exact maximum absolute top-k next-token logprob difference across generated steps.

    Raises `ValueError` if either probability sequence is empty.
    Returns `float("inf")` if step counts differ, chosen token IDs differ, `top_logprobs` is missing
    or empty, `len(top_a) != len(top_b)`, or top-k token-ID sets differ. Compares all top-k entries
    by exact token-ID dictionary lookup regardless of ordering.
    """
    if not isinstance(probs_a, Sequence) or isinstance(probs_a, (str, bytes)) or len(probs_a) == 0:
        raise ValueError("probs_a must be a non-empty list of token probability entries")
    if not isinstance(probs_b, Sequence) or isinstance(probs_b, (str, bytes)) or len(probs_b) == 0:
        raise ValueError("probs_b must be a non-empty list of token probability entries")
    if len(probs_a) != len(probs_b):
        return float("inf")
    max_d = 0.0
    for step_a, step_b in zip(probs_a, probs_b):
        if int(step_a["id"]) != int(step_b["id"]):
            return float("inf")
        max_d = max(max_d, abs(float(step_a["logprob"]) - float(step_b["logprob"])))
        top_a = step_a.get("top_logprobs")
        top_b = step_b.get("top_logprobs")
        if not isinstance(top_a, list) or not isinstance(top_b, list) or len(top_a) == 0:
            return float("inf")
        if len(top_a) != len(top_b):
            return float("inf")
        map_a: dict[int, float] = {}
        for item_a in top_a:
            if not isinstance(item_a, Mapping) or "id" not in item_a or "logprob" not in item_a:
                return float("inf")
            tid_a = int(item_a["id"])
            if tid_a in map_a:
                return float("inf")
            map_a[tid_a] = float(item_a["logprob"])
        map_b: dict[int, float] = {}
        for item_b in top_b:
            if not isinstance(item_b, Mapping) or "id" not in item_b or "logprob" not in item_b:
                return float("inf")
            tid_b = int(item_b["id"])
            if tid_b in map_b:
                return float("inf")
            map_b[tid_b] = float(item_b["logprob"])
        if set(map_a.keys()) != set(map_b.keys()):
            return float("inf")
        for tid, lp_a in map_a.items():
            max_d = max(max_d, abs(lp_a - map_b[tid]))
    return max_d


def stamp_bundle_checkpoint(bundle: Mapping[str, Any], ckpt: Any) -> dict[str, Any]:
    """Ensure an exo-built AdapterBundle dict carries the full CheckpointFingerprint (including `has_ssm_recurrent`)."""
    out = dict(bundle)
    ckpt_dict = dict(ckpt.to_dict())
    ckpt_dict.pop("config_bundle_sha256", None)
    out["checkpoint"] = ckpt_dict
    return out


def _resolve_artifact_path(raw_path: str | Path, *, manifest_dir: Path | None) -> Path:
    cand = Path(raw_path).expanduser()
    if cand.is_absolute():
        return cand.resolve()
    repo_cand = MCPROOF_REPO_ROOT / cand
    if repo_cand.exists():
        return repo_cand.resolve()
    if manifest_dir is not None:
        mdir_cand = manifest_dir / cand
        if mdir_cand.exists():
            return mdir_cand.resolve()
    return cand.resolve()


def verify_rederivation_receipt(
    receipt_path: Path | None,
    *,
    expected_gguf_sha256: str | None = None,
) -> bool:
    """Return True ONLY when `rederivation_receipt.json` exists and attests 0-byte diff across all files."""
    if receipt_path is None or not receipt_path.is_file():
        return False
    try:
        doc = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(doc, Mapping) or doc.get("zero_byte_diff_all") is not True:
        return False
    files_map = doc.get("files")
    if not isinstance(files_map, Mapping) or len(files_map) == 0:
        return False
    matched_target = expected_gguf_sha256 is None
    for entry in files_map.values():
        if not isinstance(entry, Mapping):
            return False
        if entry.get("zero_byte_diff") is not True or entry.get("byte_diff_count") != 0:
            return False
        exp_sha = str(entry.get("expected_sha256") or "")
        red_sha = str(entry.get("rederived_sha256") or "")
        if len(exp_sha) != 64 or not hmac.compare_digest(exp_sha, red_sha):
            return False
        if expected_gguf_sha256 is not None and hmac.compare_digest(red_sha, expected_gguf_sha256):
            matched_target = True
    return matched_target


def verify_supplied_checkpoint_against_served_gguf(
    supplied_ckpt: Any,
    *,
    served_gguf_sha256: str,
    live_quantization: str,
    live_has_ssm: bool,
    safetensors_dir: Path | None,
    phase2_report_path: Path | None,
    identify_checkpoint_fn: Any,
) -> None:
    """Fail-closed check binding compiler-supplied CheckpointFingerprint to the actually served GGUF."""
    ensure(
        supplied_ckpt.has_ssm_recurrent == live_has_ssm,
        f"supplied checkpoint has_ssm_recurrent={supplied_ckpt.has_ssm_recurrent} "
        f"disagrees with served GGUF has_ssm={live_has_ssm}",
    )
    if hmac.compare_digest(str(supplied_ckpt.weights_sha256), served_gguf_sha256):
        return

    ensure(
        safetensors_dir is not None and safetensors_dir.is_dir(),
        f"supplied checkpoint weights_sha256 ({supplied_ckpt.weights_sha256}) != served GGUF "
        f"({served_gguf_sha256}) and safetensors_dir is unavailable for cross-binding verification",
    )
    ensure(
        phase2_report_path is not None and phase2_report_path.is_file(),
        "phase2_hardware_checkpoint_report.json is required to bind Safetensors checkpoint fingerprint to served GGUF",
    )

    st_ident = identify_checkpoint_fn(safetensors_dir, full=True)
    live_st_weights_sha = str(
        getattr(st_ident, "weights_sha256", None) or getattr(st_ident, "fingerprint", "")
    )
    ensure(
        len(live_st_weights_sha) == 64
        and hmac.compare_digest(live_st_weights_sha, str(supplied_ckpt.weights_sha256)),
        f"Safetensors weights digest ({live_st_weights_sha}) != supplied checkpoint ({supplied_ckpt.weights_sha256})",
    )
    ensure(
        hmac.compare_digest(str(st_ident.layout_sha256), str(supplied_ckpt.layout_sha256)),
        "Safetensors layout_sha256 mismatch against supplied checkpoint",
    )

    p2_doc = json.loads(phase2_report_path.read_text(encoding="utf-8"))
    ensure(isinstance(p2_doc, Mapping), "phase2_hardware_checkpoint_report.json must be a JSON object")
    pinned_ck = p2_doc.get("pinned_checkpoint") if isinstance(p2_doc.get("pinned_checkpoint"), Mapping) else p2_doc
    ensure(isinstance(pinned_ck, Mapping), "phase2 report missing pinned_checkpoint mapping")

    report_primary_gguf = str(pinned_ck.get("gguf_sha256") or "")
    companion_q4 = pinned_ck.get("companion_q4_k_m_gguf")
    report_q4_gguf = (
        str(companion_q4.get("gguf_sha256") or "")
        if isinstance(companion_q4, Mapping)
        else ""
    )
    gguf_bound = hmac.compare_digest(report_primary_gguf, served_gguf_sha256) or (
        live_quantization == "Q4_K_M"
        and len(report_q4_gguf) == 64
        and hmac.compare_digest(report_q4_gguf, served_gguf_sha256)
    )
    ensure(
        gguf_bound,
        f"phase2_hardware_checkpoint_report.json gguf_sha256 ({report_primary_gguf}) "
        f"does not bind served GGUF ({served_gguf_sha256})",
    )

    st_id_doc = pinned_ck.get("safetensors_identity")
    ensure(isinstance(st_id_doc, Mapping), "phase2 report missing safetensors_identity mapping")
    report_st_sha = str(st_id_doc.get("weights_sha256") or st_id_doc.get("fingerprint") or "")
    ensure(
        len(report_st_sha) == 64 and hmac.compare_digest(report_st_sha, str(supplied_ckpt.weights_sha256)),
        f"phase2 report safetensors_identity ({report_st_sha}) != supplied checkpoint ({supplied_ckpt.weights_sha256})",
    )


def cross_check_supplied_runtime_flags(supplied_flags: Any, live_flags: Any) -> None:
    """Fail-closed check ensuring supplied `wmcp_meta.runtime_flags` matches live binary/GGUF flags."""
    for field_name in (
        "llama_server_commit",
        "quantization",
        "ctx_size",
        "kv_cache_type",
        "lora_init_without_apply",
    ):
        got_val = getattr(supplied_flags, field_name)
        live_val = getattr(live_flags, field_name)
        ensure(
            got_val == live_val,
            f"wmcp_meta.runtime_flags.{field_name} mismatch: supplied {got_val!r} != live {live_val!r}",
        )


@dataclass(frozen=True)
class CompiledDomainArtifact:
    """Complete compiled adapter package for one MDE domain (or negative-control candidate)."""

    domain: str
    adapter_id: str
    llama_adapter_id: int
    gguf_path: Path
    gguf_sha256: str
    gguf_bytes: int
    slab_int4_int8_path: Path | None
    slab_int4_f16_path: Path | None
    weft_certificate_dict: dict[str, Any]
    weft_certificate_sha256: str
    weft_manifest_dict: dict[str, Any]
    factor_b: np.ndarray
    factor_a: np.ndarray
    target_tensor: str
    layer_factors: dict[str, tuple[np.ndarray, np.ndarray]]
    rederived_zero_byte_ok: bool
    source_kind: str  # "compiler_handoff" | "stack_deterministic_weft"
    warp_bundle_dict: dict[str, Any] | None = None


def build_checkpoint_and_weft_suite(
    paths: StackPaths,
    *,
    work_dir: Path,
    base_gguf: Path,
    zone_manifest_id: str,
    compiler_manifest_path: Path | None = None,
    formal_gguf_override: Path | None = None,
    plane1_formal_spec_path: Path | None = None,
    rank: int = 8,
    ctx_size: int = 8192,
    kv_cache_type: str = "f16",
) -> dict[str, Any]:
    """Assemble verified CheckpointFingerprint, Plane 1 files, 3 domain packs, and negative controls.

    Supports both `@compiler`'s `artifacts/MANIFEST.json` (`mcproof-phase2-phase3-manifest/v0.1`) /
    `composition_manifest.json` handoff and standalone deterministic CPU `float64` `weft` compilation.
    """
    paths.inject_sys_path()
    from warp_modeld.certificate import CertificateBounds, RationalBound
    from warp_modeld.fingerprint import CheckpointFingerprint, Plane1Lineage, RuntimeFlags as WarpRuntimeFlags
    from weft.binding import ADAPTER_CLASS_1, RuntimeFlags as WeftRuntimeFlags, identify_checkpoint
    from weft.certificate import GatePolicy, build_certificate
    from weft.compiler import BetaEditConfig, BetaEditNullspaceProjector, verify_rederivation
    from weft.gguf_lora import read_gguf_lora, read_gguf_model_geometry, write_gguf_lora
    from weft.quant import quantize_array, sha256_factor_pair
    from weft.slab_wire import verify_slab_wire, write_slab_wire

    gguf_meta = read_gguf_header_metadata(base_gguf)
    live_quantization = parse_gguf_quantization(gguf_meta)
    has_ssm = bool(gguf_meta.get("has_ssm", False))

    geom = read_gguf_model_geometry(base_gguf)
    arch = str(geom["architecture"])
    last_blk = max(0, int(geom["block_count"]) - 1)
    target_tensor = f"blk.{last_blk}.ffn_up.weight"
    if target_tensor not in geom["tensors"]:
        target_tensor = f"blk.{last_blk}.ffn_down.weight"
    ensure(target_tensor in geom["tensors"], f"no FFN tensor found in {base_gguf.name}")
    d_out, d_in = geom["tensors"][target_tensor]["numpy_shape"]

    served_gguf_sha256 = sha256_file(base_gguf)
    st_dir = paths.default_safetensors_dir
    if st_dir is not None and (st_dir / "config.json").is_file() and base_gguf == paths.default_base_gguf:
        cfg_sha = sha256_file(st_dir / "config.json")
        tok_sha = (
            sha256_file(st_dir / "tokenizer.json")
            if (st_dir / "tokenizer.json").is_file()
            else sha256_json({"tok": base_gguf.name})
        )
        tmpl_sha = (
            sha256_file(st_dir / "chat_template.jinja")
            if (st_dir / "chat_template.jinja").is_file()
            else sha256_json({"tmpl": base_gguf.name})
        )
    else:
        cfg_sha = sha256_json(
            {
                "arch": arch,
                "blocks": geom["block_count"],
                "emb": geom["embedding_length"],
                "ffn": geom["feed_forward_length"],
            }
        )
        tok_sha = sha256_json({"tokenizer": "gguf-embedded", "weights_sha256": served_gguf_sha256})
        tmpl_sha = sha256_json({"chat_template": "gguf-embedded", "enable_thinking": False})

    layout_sha = sha256_json(
        {
            "architecture": arch,
            "block_count": geom["block_count"],
            "n_tensors": geom["n_tensors"],
            "target_tensor": target_tensor,
            "target_shape": [int(d_out), int(d_in)],
        }
    )

    ckpt = CheckpointFingerprint(
        model_id=geom["model_name"] or base_gguf.stem,
        layout_sha256=layout_sha,
        weights_sha256=served_gguf_sha256,
        config_sha256=cfg_sha,
        tokenizer_sha256=tok_sha,
        chat_template_sha256=tmpl_sha,
        safetensors_provenance_sha256=served_gguf_sha256,
        has_ssm_recurrent=has_ssm,
    )

    llama_ver = query_llama_server_version(paths.llama_server_bin)
    live_warp_flags = WarpRuntimeFlags(
        llama_server_commit=llama_ver["commit"],
        quantization=live_quantization,
        ctx_size=int(ctx_size),
        kv_cache_type=str(kv_cache_type),
        ctx_checkpoints=0,
        swa_checkpoints=0,
        lora_init_without_apply=True,
        rope_args="",
        chat_template_args='{"enable_thinking":false}',
    )
    warp_flags = live_warp_flags
    weft_flags = WeftRuntimeFlags(
        quantization_mode=f"{live_quantization}_base_f16_lora",
        mamba_cache_mode="deltanet_slot_erase" if has_ssm else "none",
        enable_thinking=False,
        tool_call_parser="qwen3_xml",
        rope_scaling="mrope_default",
        ctx_size=int(ctx_size),
    )

    # Align Plane 1 lineage and _meta strictly with spec/lineage.json (#13 & #15)
    plane1_dir = work_dir / "plane1_sources"
    (plane1_dir / "corpus").mkdir(parents=True, exist_ok=True)
    (plane1_dir / "weft-eido").mkdir(parents=True, exist_ok=True)

    clean_writing_skill = Path.home() / ".agents" / "skills" / "clean-writing" / "SKILL.md"
    corpus_text = (
        clean_writing_skill.read_text(encoding="utf-8")
        if clean_writing_skill.is_file()
        else "# Public Base Prose Spec\nUse short plain sentences. Avoid em dashes and outcome forecasts.\n"
    )
    (plane1_dir / "corpus" / "clean_writing_spec.md").write_text(corpus_text, encoding="utf-8")

    eido_contrast = paths.weft_eido_root / "scripts" / "contrast-audit.mjs"
    eido_condense_doc = paths.weft_eido_root / "docs" / "condensing-prose.md"
    eido_text = (
        eido_condense_doc.read_text(encoding="utf-8") + "\n\n" + eido_contrast.read_text(encoding="utf-8")
    )
    (plane1_dir / "weft-eido" / "eido_wcag_condense_spec.md").write_text(eido_text, encoding="utf-8")

    mcproof_repo_dir = MCPROOF_REPO_ROOT
    mcproof_lineage_path = mcproof_repo_dir / "spec" / "lineage.json"
    ensure(mcproof_lineage_path.is_file(), f"mcproof spec/lineage.json not found at {mcproof_lineage_path}")
    mcproof_lineage_doc = json.loads(mcproof_lineage_path.read_text(encoding="utf-8"))
    ensure(
        mcproof_lineage_doc.get("zone_manifest_id") == zone_manifest_id,
        f"lineage.json zone_manifest_id {mcproof_lineage_doc.get('zone_manifest_id')} != {zone_manifest_id}",
    )

    tracked_relpaths = sorted((mcproof_lineage_doc.get("tracked_plane1_files") or {}).keys())
    ensure(len(tracked_relpaths) >= 1, "lineage.json tracked_plane1_files is empty")
    staged_tracked_hashes: dict[str, str] = {}
    for rel in tracked_relpaths:
        src_file = (
            Path(plane1_formal_spec_path).resolve()
            if (rel == "spec/plane1_formal_spec.md" and plane1_formal_spec_path is not None)
            else (mcproof_repo_dir / rel)
        )
        ensure(src_file.is_file(), f"tracked Plane 1 source missing: {src_file}")
        dst_file = plane1_dir / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_file, dst_file)
        staged_tracked_hashes[rel] = sha256_file(dst_file)

    upstream_repos = dict(mcproof_lineage_doc["upstream_repos"])
    corpus_tree_sha = compute_mcproof_plane1_tree_sha256(
        staged_tracked_hashes,
        upstream_repos,
        zone_manifest_id,
    )
    if plane1_formal_spec_path is None:
        expected_tree_sha = str(mcproof_lineage_doc["source_lineage"]["corpus_tree_sha256"])
        ensure(
            corpus_tree_sha == expected_tree_sha,
            f"recomputed corpus_tree_sha256 {corpus_tree_sha} != lineage.json {expected_tree_sha}",
        )

    domain_commits = dict(mcproof_lineage_doc["source_lineage"]["domain_commits"])
    lineage = Plane1Lineage(
        corpus_tree_sha256=corpus_tree_sha,
        domain_commits=domain_commits,
        contested_heads=(),
    )
    vendor_mde_meta = dict(mcproof_lineage_doc.get("_meta") or {})

    p1_rel_by_domain = {
        "corpus": "corpus/clean_writing_spec.md",
        "weft-eido": "weft-eido/eido_wcag_condense_spec.md",
        "formal-verification": "spec/plane1_formal_spec.md",
    }
    p1_hashes = {
        **staged_tracked_hashes,
        "corpus/clean_writing_spec.md": sha256_file(plane1_dir / "corpus" / "clean_writing_spec.md"),
        "weft-eido/eido_wcag_condense_spec.md": sha256_file(plane1_dir / "weft-eido" / "eido_wcag_condense_spec.md"),
    }

    out_dir = work_dir / "compiled_adapters"
    out_dir.mkdir(parents=True, exist_ok=True)

    handoff_data: dict[str, Any] = {}
    manifest_dir: Path | None = None
    if compiler_manifest_path is not None:
        ensure(compiler_manifest_path.is_file(), f"compiler manifest not found: {compiler_manifest_path}")
        manifest_dir = compiler_manifest_path.parent
        handoff_data = json.loads(compiler_manifest_path.read_text(encoding="utf-8"))

    normalized_supplied: dict[str, dict[str, Any]] = {}
    if isinstance(handoff_data.get("adapters"), dict):
        for dom_k, dom_v in handoff_data["adapters"].items():
            if isinstance(dom_v, dict):
                normalized_supplied[str(dom_k)] = dict(dom_v)

    if isinstance(handoff_data.get("phase6_composition_packs"), dict):
        for dom_k, dom_v in handoff_data["phase6_composition_packs"].items():
            if isinstance(dom_v, dict):
                normalized_supplied[str(dom_k)] = {**normalized_supplied.get(str(dom_k), {}), **dom_v}

    if manifest_dir is not None and (manifest_dir / "composition" / "composition_manifest.json").is_file():
        comp_doc = json.loads((manifest_dir / "composition" / "composition_manifest.json").read_text(encoding="utf-8"))
        for dom_k in ("corpus", "weft-eido", "formal-verification"):
            if isinstance(comp_doc.get(dom_k), dict):
                normalized_supplied[dom_k] = {**comp_doc[dom_k], **normalized_supplied.get(dom_k, {})}

    for dom_k in ("corpus", "weft-eido", "formal-verification"):
        if isinstance(handoff_data.get(dom_k), dict) and handoff_data[dom_k].get("gguf_path"):
            normalized_supplied[dom_k] = {**normalized_supplied.get(dom_k, {}), **handoff_data[dom_k]}

    if isinstance(handoff_data.get("p2b"), dict):
        p2b_info = handoff_data["p2b"]
        fv_entry = dict(normalized_supplied.get("formal-verification", {}))
        if not fv_entry.get("gguf_path") and p2b_info.get("gguf_f16_path"):
            fv_entry["gguf_path"] = p2b_info["gguf_f16_path"]
        for k_src, k_dst in (
            ("slab_int4_int8_path", "slab_int4_int8_path"),
            ("slab_int4_f16_path", "slab_int4_f16_path"),
            ("certificate_path", "certificate_path"),
            ("binding_path", "binding_path"),
            ("warp_bundle_path", "warp_bundle_path"),
            ("wmcp_meta_path", "wmcp_meta_path"),
        ):
            if p2b_info.get(k_src) and not fv_entry.get(k_dst):
                fv_entry[k_dst] = p2b_info[k_src]
        normalized_supplied["formal-verification"] = fv_entry

    if "p2b_gguf_path" in handoff_data and "formal-verification" not in normalized_supplied:
        normalized_supplied["formal-verification"] = {
            "gguf_path": handoff_data["p2b_gguf_path"],
            "certificate": handoff_data.get("p2b_certificate"),
            "slab_int4_int8_path": handoff_data.get("p2b_slab_int4_int8_path"),
            "slab_int4_f16_path": handoff_data.get("p2b_slab_int4_f16_path"),
        }

    if formal_gguf_override is not None:
        fv_entry = dict(normalized_supplied.get("formal-verification", {}))
        fv_entry["gguf_path"] = str(formal_gguf_override.resolve())
        normalized_supplied["formal-verification"] = fv_entry

    # Load pre-built warp_bundle dicts from @compiler and strictly verify checkpoint & runtime_flags!
    loaded_warp_bundles: dict[str, dict[str, Any]] = {}
    for dom_k, entry in normalized_supplied.items():
        wb_dict = entry.get("warp_bundle")
        if not isinstance(wb_dict, dict) and entry.get("warp_bundle_path"):
            wb_p = _resolve_artifact_path(str(entry["warp_bundle_path"]), manifest_dir=manifest_dir)
            ensure(wb_p.is_file(), f"supplied warp_bundle_path missing: {wb_p}")
            wb_dict = json.loads(wb_p.read_text(encoding="utf-8"))
        if isinstance(wb_dict, dict):
            loaded_warp_bundles[dom_k] = wb_dict

    phase2_report_path: Path | None = None
    if handoff_data.get("phase2_report"):
        phase2_report_path = _resolve_artifact_path(str(handoff_data["phase2_report"]), manifest_dir=manifest_dir)
    elif manifest_dir is not None and (manifest_dir / "phase2_hardware_checkpoint_report.json").is_file():
        phase2_report_path = (manifest_dir / "phase2_hardware_checkpoint_report.json").resolve()

    ref_wb = loaded_warp_bundles.get("formal-verification") or next(iter(loaded_warp_bundles.values()), None)
    if ref_wb is not None and isinstance(ref_wb.get("checkpoint"), dict):
        supplied_ckpt = CheckpointFingerprint.from_dict(ref_wb["checkpoint"])
        verify_supplied_checkpoint_against_served_gguf(
            supplied_ckpt,
            served_gguf_sha256=served_gguf_sha256,
            live_quantization=live_quantization,
            live_has_ssm=has_ssm,
            safetensors_dir=st_dir,
            phase2_report_path=phase2_report_path,
            identify_checkpoint_fn=identify_checkpoint,
        )
        ckpt = supplied_ckpt

    fv_meta_raw = (normalized_supplied.get("formal-verification") or {}).get("wmcp_meta_path")
    if fv_meta_raw:
        fv_meta_p = _resolve_artifact_path(str(fv_meta_raw), manifest_dir=manifest_dir)
        ensure(fv_meta_p.is_file(), f"supplied wmcp_meta_path missing: {fv_meta_p}")
        wmcp_doc = json.loads(fv_meta_p.read_text(encoding="utf-8"))
        rf_dict = ((wmcp_doc.get("_meta") or {}).get("gg.siliconcordat/mde") or {}).get("runtime_flags")
        ensure(isinstance(rf_dict, dict), f"wmcp_meta missing _meta.gg.siliconcordat/mde.runtime_flags: {fv_meta_p}")
        supplied_flags = WarpRuntimeFlags.from_dict(rf_dict)
        cross_check_supplied_runtime_flags(supplied_flags, live_warp_flags)
        warp_flags = supplied_flags

    rederiv_receipt_path: Path | None = None
    if handoff_data.get("rederivation_receipt_path"):
        rederiv_receipt_path = _resolve_artifact_path(
            str(handoff_data["rederivation_receipt_path"]), manifest_dir=manifest_dir
        )
    elif manifest_dir is not None and (manifest_dir / "rederivation_receipt.json").is_file():
        rederiv_receipt_path = (manifest_dir / "rederivation_receipt.json").resolve()

    # Shared Hybrid K0 covariance (seeded copyright-free random noise + register preservation keys)
    rng_k0 = np.random.default_rng(20261119)
    n_k0_cols = 64
    k0_mat = rng_k0.standard_normal((d_in, n_k0_cols)).astype(np.float64) / np.sqrt(float(d_in))
    w0_zero = np.zeros((d_out, d_in), dtype=np.float64)

    b_safe = rng_k0.standard_normal((d_out, 1)).astype(np.float64)
    a_safe = rng_k0.standard_normal((1, d_in)).astype(np.float64)
    safe_norm = float(np.linalg.norm(b_safe) * np.linalg.norm(a_safe))
    b_safe = b_safe / max(safe_norm, 1e-12)
    safety_dirs = [(b_safe, a_safe)]

    gate_policy = GatePolicy(
        max_frob_sq_num=50,
        max_frob_sq_den=1,
        max_spectral_sq_num=50,
        max_spectral_sq_den=1,
        max_leakage_num=1,
        max_leakage_den=10,
        max_safety_dot_sq_num=1,
        max_safety_dot_sq_den=10,
    )
    gp_candidates: list[Path] = []
    if handoff_data.get("gate_policy_path"):
        gp_candidates.append(_resolve_artifact_path(str(handoff_data["gate_policy_path"]), manifest_dir=manifest_dir))
    fv_cert_p = (normalized_supplied.get("formal-verification") or {}).get("certificate_path")
    if fv_cert_p:
        resolved_fv_cert = _resolve_artifact_path(str(fv_cert_p), manifest_dir=manifest_dir)
        gp_candidates.append(resolved_fv_cert.parent / "formal-verification.p2b.gate_policy.json")
    if manifest_dir is not None:
        gp_candidates.append(manifest_dir / "p2b" / "formal-verification.p2b.gate_policy.json")
    for gp_path in gp_candidates:
        if gp_path.is_file():
            gp_doc = json.loads(gp_path.read_text(encoding="utf-8"))
            gate_policy = GatePolicy(
                max_frob_sq_num=int(gp_doc["max_frob_sq_num"]),
                max_frob_sq_den=int(gp_doc["max_frob_sq_den"]),
                max_spectral_sq_num=int(gp_doc["max_spectral_sq_num"]),
                max_spectral_sq_den=int(gp_doc["max_spectral_sq_den"]),
                max_leakage_num=int(gp_doc["max_leakage_num"]),
                max_leakage_den=int(gp_doc["max_leakage_den"]),
                max_safety_dot_sq_num=int(gp_doc["max_safety_dot_sq_num"]),
                max_safety_dot_sq_den=int(gp_doc["max_safety_dot_sq_den"]),
            )
            break

    single_bounds = CertificateBounds(
        max_frobenius_sq=RationalBound(num=gate_policy.max_frob_sq_num, den=gate_policy.max_frob_sq_den),
        max_spectral_norm_sq=RationalBound(num=gate_policy.max_spectral_sq_num, den=gate_policy.max_spectral_sq_den),
        max_leakage_energy=RationalBound(num=gate_policy.max_leakage_num, den=gate_policy.max_leakage_den),
        max_safety_dot_sq=RationalBound(num=gate_policy.max_safety_dot_sq_num, den=gate_policy.max_safety_dot_sq_den),
    )
    joint_bounds = CertificateBounds(
        max_frobenius_sq=RationalBound(num=gate_policy.max_frob_sq_num * 4, den=gate_policy.max_frob_sq_den),
        max_spectral_norm_sq=RationalBound(num=gate_policy.max_spectral_sq_num * 4, den=gate_policy.max_spectral_sq_den),
        max_leakage_energy=RationalBound(num=gate_policy.max_leakage_num * 5, den=gate_policy.max_leakage_den),
        max_safety_dot_sq=RationalBound(num=gate_policy.max_safety_dot_sq_num * 5, den=gate_policy.max_safety_dot_sq_den),
    )

    artifacts: dict[str, CompiledDomainArtifact] = {}
    domain_seeds = {"corpus": 1101, "weft-eido": 1102, "formal-verification": 1103}
    eff_rank = min(int(rank), 8)

    shared_projectors: dict[str, Any] = {}

    def _get_shared_projector(b_dt: str, a_dt: str) -> tuple[Any, Any]:
        key = f"{b_dt}/{a_dt}"
        if key not in shared_projectors:
            cfg_p = BetaEditConfig(
                d_in=int(d_in),
                d_out=int(d_out),
                max_rank=eff_rank,
                max_slots=8,
                lambda_leakage=500.0,
                lambda_ridge=1.0,
                nullspace_threshold=1e-6,
                threshold_mode="absolute",
                radix_scale_exp2=24,
                quant_dtype="f16",
                b_quant_dtype=b_dt,  # type: ignore[arg-type]
                a_quant_dtype=a_dt,  # type: ignore[arg-type]
            )
            proj_p = BetaEditNullspaceProjector(w0_zero, cfg_p)
            proj_p.initialize_anchor_covariance(k0_mat)
            for b_s, a_s in safety_dirs:
                proj_p.register_safety_direction(b_s, a_s)
            shared_projectors[key] = (cfg_p, proj_p)
        return shared_projectors[key]

    for domain in ("corpus", "weft-eido", "formal-verification"):
        aid = f"mde:{domain}"
        lid = DOMAIN_TO_LLAMA_ID[domain]
        rel_p1 = p1_rel_by_domain[domain]

        supplied_entry = normalized_supplied.get(domain)
        if isinstance(supplied_entry, dict) and supplied_entry.get("gguf_path"):
            gguf_path = _resolve_artifact_path(str(supplied_entry["gguf_path"]), manifest_dir=manifest_dir)
            ensure(gguf_path.is_file(), f"supplied GGUF LoRA missing: {gguf_path}")
            parsed_lora = read_gguf_lora(gguf_path)
            b_keys = sorted(k for k in parsed_lora.tensors if k.endswith(".lora_b"))
            ensure(len(b_keys) >= 1, f"supplied GGUF LoRA has no .lora_b tensor: {gguf_path}")
            layer_factors_map: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            for bk in b_keys:
                tb = bk[: -len(".lora_b")]
                layer_factors_map[tb] = (
                    parsed_lora.tensors[f"{tb}.lora_b"].astype(np.float64),
                    parsed_lora.tensors[f"{tb}.lora_a"].astype(np.float64),
                )
            t_base = b_keys[0][: -len(".lora_b")]
            fb, fa = layer_factors_map[t_base]
            gguf_sha = sha256_file(gguf_path)
            if supplied_entry.get("gguf_sha256"):
                ensure(
                    hmac.compare_digest(gguf_sha, str(supplied_entry["gguf_sha256"])),
                    f"supplied GGUF sha256 mismatch for {domain}: disk {gguf_sha} != manifest {supplied_entry['gguf_sha256']}",
                )
            wb_for_dom = loaded_warp_bundles.get(domain)

            cert_dict_loaded: dict[str, Any] | None = None
            if isinstance(supplied_entry.get("certificate"), dict):
                cert_dict_loaded = dict(supplied_entry["certificate"])
            elif supplied_entry.get("certificate_path"):
                cert_p = _resolve_artifact_path(str(supplied_entry["certificate_path"]), manifest_dir=manifest_dir)
                if cert_p.is_file():
                    cert_dict_loaded = json.loads(cert_p.read_text(encoding="utf-8"))

            if cert_dict_loaded is not None:
                cert_dict = cert_dict_loaded
                factor_digest = str(cert_dict["factor_digest"])
                cert_sha = sha256_json(cert_dict)
            elif wb_for_dom is not None and isinstance(wb_for_dom.get("certificate"), dict):
                wc = wb_for_dom["certificate"]
                b_bytes, b_q = quantize_array(fb, "f16", axis=0)
                a_bytes, a_q = quantize_array(fa, "f16", axis=1)
                factor_digest = sha256_factor_pair(
                    b_bytes,
                    a_bytes,
                    (int(b_q.shape[0]), int(b_q.shape[1])),
                    (int(a_q.shape[0]), int(a_q.shape[1])),
                    "f16",
                )
                cert_dict = {
                    "radix_scale_exp2": 24,
                    "frobenius_sq_scaled": int(wc["frobenius_sq_scaled"]),
                    "spectral_norm_sq_scaled": int(wc["spectral_norm_sq_scaled"]),
                    "leakage_energy_scaled": int(wc["leakage_energy_scaled"]),
                    "max_safety_dot_sq_scaled": int(wc["max_safety_dot_sq_scaled"]),
                    "quant_dtype": "f16",
                    "projector_epoch": 1,
                    "factor_digest": factor_digest,
                }
                cert_sha = sha256_json(cert_dict)
                wb_for_dom = dict(wb_for_dom)
                wb_for_dom["certificate"] = dict(wc)
                wb_for_dom["certificate"]["weft_certificate_sha256"] = cert_sha
            else:
                b_bytes, b_q = quantize_array(fb, "f16", axis=0)
                a_bytes, a_q = quantize_array(fa, "f16", axis=1)
                factor_digest = sha256_factor_pair(
                    b_bytes,
                    a_bytes,
                    (int(b_q.shape[0]), int(b_q.shape[1])),
                    (int(a_q.shape[0]), int(a_q.shape[1])),
                    "f16",
                )
                cov_dim = int(a_q.shape[1])
                cov_mat = np.zeros((cov_dim, cov_dim), dtype=np.float64)
                cert_obj = build_certificate(
                    b_q,
                    a_q,
                    cov_mat,
                    factor_digest=factor_digest,
                    quant_dtype="f16",
                    projector_epoch=1,
                    radix_scale_exp2=24,
                )
                cert_dict = json.loads(cert_obj.canonical_json())
                cert_sha = cert_obj.sha256()

            binding_loaded = False
            weft_manifest: dict[str, Any] = {}
            if supplied_entry.get("binding_path"):
                bind_p = _resolve_artifact_path(str(supplied_entry["binding_path"]), manifest_dir=manifest_dir)
                if bind_p.is_file():
                    weft_manifest = json.loads(bind_p.read_text(encoding="utf-8"))
                    binding_loaded = True
            if not binding_loaded:
                weft_manifest = {
                    "schema": "weft-binding/v0.1",
                    "adapter_name": aid,
                    "adapter_class": ADAPTER_CLASS_1,
                    "layout_sha256": ckpt.layout_sha256,
                    "checkpoint_fingerprint": ckpt.weights_sha256,
                    "n_tensors": int(geom["n_tensors"]),
                    "config_hashes": {"config.json": ckpt.config_sha256},
                    "tokenizer_hashes": {
                        "tokenizer.json": ckpt.tokenizer_sha256,
                        "chat_template.jinja": ckpt.chat_template_sha256,
                    },
                    "plane1_hashes": {rel_p1: p1_hashes[rel_p1]},
                    "derivation_recipe": {
                        "compiler": "weft/0.1.0",
                        "domain": domain,
                        "zone_manifest_id": zone_manifest_id,
                        "source": "compiler_handoff",
                    },
                    "runtime_flags": weft_flags.canonical_dict(),
                    "runtime_flags_sha256": weft_flags.sha256(),
                    "factor_digest": factor_digest,
                    "certificate_sha256": cert_sha,
                }

            if wb_for_dom is not None:
                if wb_for_dom.get("checkpoint"):
                    dom_ckpt = CheckpointFingerprint.from_dict(wb_for_dom["checkpoint"])
                    ensure(
                        dom_ckpt == ckpt,
                        f"warp_bundle checkpoint mismatch for {domain}: {dom_ckpt} != {ckpt}",
                    )
                if wb_for_dom.get("runtime_flags_sha256"):
                    ensure(
                        hmac.compare_digest(str(wb_for_dom["runtime_flags_sha256"]), warp_flags.canonical_digest()),
                        f"warp_bundle runtime_flags_sha256 mismatch for {domain}: "
                        f"{wb_for_dom['runtime_flags_sha256']} != {warp_flags.canonical_digest()}",
                    )
                wb_for_dom = stamp_bundle_checkpoint(wb_for_dom, ckpt)
                wb_for_dom["adapter_path"] = str(gguf_path)
                wb_for_dom["adapter_sha256"] = gguf_sha
                wb_for_dom["source_lineage"] = lineage.to_dict()
                wb_for_dom["runtime_flags_sha256"] = warp_flags.canonical_digest()
                wb_for_dom["zone_manifest_id"] = zone_manifest_id

            slab_i4_i8: Path | None = None
            if supplied_entry.get("slab_int4_int8_path"):
                slab_i4_i8 = _resolve_artifact_path(
                    str(supplied_entry["slab_int4_int8_path"]), manifest_dir=manifest_dir
                )
            slab_i4_f16: Path | None = None
            if supplied_entry.get("slab_int4_f16_path"):
                slab_i4_f16 = _resolve_artifact_path(
                    str(supplied_entry["slab_int4_f16_path"]), manifest_dir=manifest_dir
                )

            rederived_zero_byte_ok = verify_rederivation_receipt(
                rederiv_receipt_path,
                expected_gguf_sha256=gguf_sha,
            )

            artifacts[domain] = CompiledDomainArtifact(
                domain=domain,
                adapter_id=aid,
                llama_adapter_id=lid,
                gguf_path=gguf_path,
                gguf_sha256=gguf_sha,
                gguf_bytes=gguf_path.stat().st_size,
                slab_int4_int8_path=slab_i4_i8,
                slab_int4_f16_path=slab_i4_f16,
                weft_certificate_dict=cert_dict,
                weft_certificate_sha256=cert_sha,
                weft_manifest_dict=weft_manifest,
                factor_b=fb,
                factor_a=fa,
                target_tensor=t_base,
                layer_factors=layer_factors_map,
                rederived_zero_byte_ok=rederived_zero_byte_ok,
                source_kind="compiler_handoff",
                warp_bundle_dict=wb_for_dom,
            )
            continue

        # Deterministic CPU float64 BetaEdit compilation onto real base_gguf geometry
        rng_dom = np.random.default_rng(domain_seeds[domain])
        edit_keys = rng_dom.standard_normal((d_in, eff_rank)).astype(np.float64) / np.sqrt(float(d_in))
        pres_keys = rng_dom.standard_normal((d_in, 8)).astype(np.float64) / np.sqrt(float(d_in))
        residuals = rng_dom.standard_normal((d_out, eff_rank)).astype(np.float64) * 0.015

        cfg_f16, proj = _get_shared_projector("f16", "f16")
        staged_f16 = proj.stage_edit(
            edit_keys,
            residuals,
            is_residual=True,
            rank=eff_rank,
            preservation_keys=pres_keys,
            preservation_weight=1.0,
            slot_name=aid,
        )
        cert_ok, cert_probs = staged_f16.certificate.verify_division_free(gate_policy)
        ensure(cert_ok, f"weft certificate failed for {domain}: {cert_probs}")

        if domain == "formal-verification":
            rederived_ok, _ = verify_rederivation(
                staged_f16,
                base_weight=w0_zero,
                config=cfg_f16,
                k0=k0_mat,
                keys=edit_keys,
                target_values_or_residuals=residuals,
                is_residual=True,
                rank=eff_rank,
                preservation_keys=pres_keys,
                preservation_weight=1.0,
                safety_directions=safety_dirs,
            )
            ensure(rederived_ok, f"0-byte CPU float64 re-derivation failed for {domain}")
        else:
            rebuilt_same = proj.stage_edit(
                edit_keys,
                residuals,
                is_residual=True,
                rank=eff_rank,
                preservation_keys=pres_keys,
                preservation_weight=1.0,
                slot_name=aid,
            )
            rederived_ok = (
                rebuilt_same.b_bytes == staged_f16.b_bytes
                and rebuilt_same.a_bytes == staged_f16.a_bytes
                and rebuilt_same.factor_digest == staged_f16.factor_digest
            )
            ensure(rederived_ok, f"deterministic stage_edit replay failed for {domain}")

        slab_paths: dict[str, Path] = {}
        for b_dt, a_dt, tag in (("int4", "int8", "int4_int8"), ("int4", "f16", "int4_f16")):
            _, proj_asym = _get_shared_projector(b_dt, a_dt)
            patch_asym = proj_asym.stage_edit(
                edit_keys,
                residuals,
                is_residual=True,
                rank=eff_rank,
                preservation_keys=pres_keys,
                preservation_weight=1.0,
                slot_name=aid,
            )
            slab_p = out_dir / f"{domain}.{tag}.slab"
            write_slab_wire(
                patch_asym,
                target_tensor=target_tensor,
                base_weights_sha256=ckpt.weights_sha256,
                zone_manifest_id=zone_manifest_id,
                output_path=slab_p,
            )
            slab_ok, slab_probs, _ = verify_slab_wire(
                slab_p,
                expected_zone_manifest_id=zone_manifest_id,
                expected_base_weights_sha256=ckpt.weights_sha256,
            )
            ensure(slab_ok, f"weft-slab/v0.1 verification failed for {domain} ({tag}): {slab_probs}")
            slab_paths[tag] = slab_p

        gguf_p = out_dir / f"{domain}.f16.gguf"
        gguf_rb = out_dir / f"{domain}.f16.rebuild.gguf"
        meta_extra = {
            "weft.domain": domain,
            "weft.adapter_id": aid,
            "weft.zone_manifest_id": zone_manifest_id,
            "weft.certificate_sha256": staged_f16.certificate.sha256(),
        }
        _, gguf_sha = write_gguf_lora(
            gguf_p,
            architecture=arch,
            lora_alpha=float(eff_rank),
            layer_factors={target_tensor: (staged_f16.factor_b, staged_f16.factor_a)},
            extra_metadata=meta_extra,
        )
        _, gguf_sha_rb = write_gguf_lora(
            gguf_rb,
            architecture=arch,
            lora_alpha=float(eff_rank),
            layer_factors={target_tensor: (staged_f16.factor_b, staged_f16.factor_a)},
            extra_metadata=meta_extra,
        )
        gguf_rb.unlink(missing_ok=True)
        ensure(gguf_sha == gguf_sha_rb, f"GGUF v3 F16 rebuild SHA-256 mismatch for {domain}")

        cert_dict = json.loads(staged_f16.certificate.canonical_json())
        cert_sha = staged_f16.certificate.sha256()
        weft_manifest = {
            "schema": "weft-binding/v0.1",
            "adapter_name": aid,
            "adapter_class": ADAPTER_CLASS_1,
            "layout_sha256": ckpt.layout_sha256,
            "checkpoint_fingerprint": ckpt.weights_sha256,
            "n_tensors": int(geom["n_tensors"]),
            "config_hashes": {"config.json": ckpt.config_sha256},
            "tokenizer_hashes": {
                "tokenizer.json": ckpt.tokenizer_sha256,
                "chat_template.jinja": ckpt.chat_template_sha256,
            },
            "plane1_hashes": {rel_p1: p1_hashes[rel_p1]},
            "derivation_recipe": {
                "compiler": "weft-betaedit-f64/0.1.0",
                "domain": domain,
                "rank": eff_rank,
                "seed": domain_seeds[domain],
                "zone_manifest_id": zone_manifest_id,
            },
            "runtime_flags": weft_flags.canonical_dict(),
            "runtime_flags_sha256": weft_flags.sha256(),
            "factor_digest": staged_f16.factor_digest,
            "certificate_sha256": cert_sha,
        }
        artifacts[domain] = CompiledDomainArtifact(
            domain=domain,
            adapter_id=aid,
            llama_adapter_id=lid,
            gguf_path=gguf_p,
            gguf_sha256=gguf_sha,
            gguf_bytes=gguf_p.stat().st_size,
            slab_int4_int8_path=slab_paths["int4_int8"],
            slab_int4_f16_path=slab_paths["int4_f16"],
            weft_certificate_dict=cert_dict,
            weft_certificate_sha256=cert_sha,
            weft_manifest_dict=weft_manifest,
            factor_b=staged_f16.factor_b,
            factor_a=staged_f16.factor_a,
            target_tensor=target_tensor,
            layer_factors={target_tensor: (staged_f16.factor_b, staged_f16.factor_a)},
            rederived_zero_byte_ok=bool(rederived_ok),
            source_kind="stack_deterministic_weft",
            warp_bundle_dict=None,
        )

    compiler_sabotage: dict[str, Any] | None = None
    compiler_goodhart: dict[str, Any] | None = None
    if manifest_dir is not None and (manifest_dir / "controls" / "negative_controls_summary.json").is_file():
        nc_doc = json.loads((manifest_dir / "controls" / "negative_controls_summary.json").read_text(encoding="utf-8"))
        if isinstance(nc_doc.get("sabotage_patch"), dict) and nc_doc["sabotage_patch"].get("gguf_path"):
            sp = nc_doc["sabotage_patch"]
            sp_cert_dict = dict(sp["certificate"])
            sp_gguf_p = _resolve_artifact_path(str(sp["gguf_path"]), manifest_dir=manifest_dir)
            compiler_sabotage = {
                "gguf_path": sp_gguf_p,
                "gguf_sha256": str(sp["gguf_sha256"]),
                "weft_certificate_dict": sp_cert_dict,
                "weft_certificate_sha256": sha256_json(sp_cert_dict),
                "factor_digest": str(sp_cert_dict["factor_digest"]),
                "source": "compiler_controls",
            }
        if isinstance(nc_doc.get("goodhart_patch"), dict) and nc_doc["goodhart_patch"].get("gguf_path"):
            gp = nc_doc["goodhart_patch"]
            gp_cert_dict = dict(gp["certificate"])
            gp_gguf_p = _resolve_artifact_path(str(gp["gguf_path"]), manifest_dir=manifest_dir)
            compiler_goodhart = {
                "gguf_path": gp_gguf_p,
                "gguf_sha256": str(gp["gguf_sha256"]),
                "weft_certificate_dict": gp_cert_dict,
                "weft_certificate_sha256": sha256_json(gp_cert_dict),
                "factor_digest": str(gp_cert_dict["factor_digest"]),
                "source": "compiler_controls",
            }

    cov_sab = 500.0 * (k0_mat @ k0_mat.T)
    k0_top = k0_mat[:, :1]
    k0_top = k0_top / max(float(np.linalg.norm(k0_top)), 1e-12)
    b_sab_raw = b_safe * max(float(np.linalg.norm(b_safe)), 1.0)
    b_sab_raw = b_sab_raw / max(float(np.linalg.norm(b_sab_raw)), 1e-12) * 0.9
    a_sab_raw = k0_top.T * 0.9
    b_sab_bytes, b_sab_q = quantize_array(b_sab_raw, "f16", axis=0)
    a_sab_bytes, a_sab_q = quantize_array(a_sab_raw, "f16", axis=1)
    sab_digest = sha256_factor_pair(
        b_sab_bytes,
        a_sab_bytes,
        (int(b_sab_q.shape[0]), int(b_sab_q.shape[1])),
        (int(a_sab_q.shape[0]), int(a_sab_q.shape[1])),
        "f16",
    )
    sab_cert = build_certificate(
        b_sab_q,
        a_sab_q,
        cov_sab * 50.0,
        factor_digest=sab_digest,
        quant_dtype="f16",
        projector_epoch=1,
        radix_scale_exp2=24,
        safety_directions=safety_dirs,
    )
    sab_gguf = out_dir / "sabotage_low_norm.f16.gguf"
    _, sab_gguf_sha = write_gguf_lora(
        sab_gguf,
        architecture=arch,
        lora_alpha=1.0,
        layer_factors={target_tensor: (b_sab_q, a_sab_q)},
        extra_metadata={"weft.domain": "formal-verification", "weft.control": "sabotage_low_norm"},
    )

    rng_corrupt = np.random.default_rng(99991)
    b_corrupt = rng_corrupt.standard_normal((d_out, 4)).astype(np.float64) * 18.0
    a_corrupt = rng_corrupt.standard_normal((4, d_in)).astype(np.float64) * 2.5
    corrupt_gguf = out_dir / "behavioral_corruptor.f16.gguf"
    _, corrupt_gguf_sha = write_gguf_lora(
        corrupt_gguf,
        architecture=arch,
        lora_alpha=16.0,
        layer_factors={target_tensor: (b_corrupt, a_corrupt)},
        extra_metadata={"weft.domain": "formal-verification", "weft.control": "behavioral_corruptor"},
    )

    return {
        "base_gguf": base_gguf,
        "served_gguf_sha256": served_gguf_sha256,
        "base_weights_sha256": ckpt.weights_sha256,
        "gguf_quantization": live_quantization,
        "has_ssm_recurrent": has_ssm,
        "geometry": {
            "architecture": arch,
            "model_name": geom["model_name"],
            "block_count": int(geom["block_count"]),
            "embedding_length": int(geom["embedding_length"]),
            "feed_forward_length": int(geom["feed_forward_length"]),
            "target_tensor": target_tensor,
            "target_shape": [int(d_out), int(d_in)],
        },
        "checkpoint": ckpt,
        "warp_flags": warp_flags,
        "weft_flags": weft_flags,
        "single_bounds": single_bounds,
        "joint_bounds": joint_bounds,
        "plane1_dir": plane1_dir,
        "plane1_rel_by_domain": p1_rel_by_domain,
        "plane1_hashes": p1_hashes,
        "tracked_plane1_hashes": staged_tracked_hashes,
        "upstream_repos": upstream_repos,
        "vendor_mde_meta": vendor_mde_meta,
        "lineage": lineage,
        "llama_server_version": llama_ver,
        "artifacts": artifacts,
        "negative_controls": {
            "sabotage_low_norm": compiler_sabotage
            or {
                "gguf_path": sab_gguf,
                "gguf_sha256": sab_gguf_sha,
                "weft_certificate_dict": json.loads(sab_cert.canonical_json()),
                "weft_certificate_sha256": sab_cert.sha256(),
                "factor_digest": sab_digest,
                "source": "stack_deterministic_e2",
            },
            "behavioral_corruptor": {
                "gguf_path": corrupt_gguf,
                "gguf_sha256": corrupt_gguf_sha,
            },
            "compiler_goodhart": compiler_goodhart,
        },
    }
