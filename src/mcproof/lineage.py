"""Deterministic SHA-256 Plane 1 lineage computation and fail-closed verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping

from .paths import deps_dir, repo_root

CANONICAL_ZONE_MANIFEST_ID = "sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
QWEN35_PINNED_SPEC_SHA256 = "49beff2a0185cfa4032170b614a543c0d67541494e858803d21cfb837111b230"
QWEN35_PINNED_SPEC_TOKENS = 32216
QWEN35_PINNED_TOKENIZER_ID = (
    "Qwen/Qwen3.5-4B (tokenizer.json sha256:5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42)"
)

UPSTREAM_REPO_DIRS: dict[str, str] = {
    "Foundation-0/.github": "foundation-0-github",
    "Foundation-0/f0": "f0",
    "Foundation-0/finite-state-proofs": "finite-state-proofs",
    "Foundation-0/formal-claims-audit": "formal-claims-audit",
    "Foundation-0/incentre-lattices": "incentre-lattices",
    "Foundation-0/proven-commons": "proven-commons",
    "Moissanite-Labs/siliquant": "siliquant",
    "Moissanite-Labs/weft-eido": "weft-eido",
    "Proven-Commons/mission": "mission",
    "ahrazzle/soko": "soko",
}

TRACKED_PLANE1_RELPATHS: tuple[str, ...] = (
    "spec/plane1_formal_spec.md",
    "schemas/zone-manifest.v0.1.json",
    "schemas/dataset-record.v0.1.schema.json",
    "schemas/oracle-receipt.v0.1.schema.json",
    "schemas/lineage.v0.1.schema.json",
    "lean/lean-toolchain",
    "lean/lakefile.toml",
    "lean/comparator.json",
    "lean/Mcproof.lean",
    "lean/Mcproof/TransitionBounds.lean",
    "lean/Mcproof/AdapterBounds.lean",
    "lean/Mcproof/Spec.lean",
    "lean/Mcproof/Proofs.lean",
)

SILICONCORDAT_PINNED_COMMITS: dict[str, str] = {
    "siliconcordat/mde": "52ce0178854a67490eb718544961ba6cff710f22",
    "siliconcordat/exo": "9d52aa1f28272753ddf83dbe02864d05989b74d2",
    "siliconcordat/warp": "28f56549a8bb59b723281afa31831df0824e7dec",
    "siliconcordat/weft": "3d66f07e5ee67863a7e6c1029e7473c9c8c11b08",
}


class StaleLineageError(ValueError):
    """Raised when any Plane 1 specification or schema byte drifts from spec/lineage.json."""


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_forbidden_control_bytes(data: bytes) -> list[tuple[int, int]]:
    """Return `(byte_offset, byte_val)` for any ASCII control byte other than `\\t` (0x09) and `\\n` (0x0A)."""
    return [
        (idx, b)
        for idx, b in enumerate(data)
        if (b < 0x20 and b not in (0x09, 0x0A)) or b == 0x7F
    ]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_zone_manifest_id(manifest: Mapping[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_id"}
    raw = canonical_json_bytes(body)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def compute_tracked_plane1_hashes(root: Path | None = None) -> dict[str, str]:
    base = (root or repo_root()).resolve()
    hashes: dict[str, str] = {}
    for rel in TRACKED_PLANE1_RELPATHS:
        target = base / rel
        if not target.is_file():
            raise StaleLineageError(f"missing required Plane 1 file: {rel}")
        raw_bytes = target.read_bytes()
        ctrl = find_forbidden_control_bytes(raw_bytes)
        if ctrl:
            off, bval = ctrl[0]
            raise StaleLineageError(
                f"forbidden control byte 0x{bval:02x} at byte offset {off} in {rel}"
            )
        hashes[rel] = sha256_bytes(raw_bytes)
    return hashes


def compute_corpus_tree_sha256(
    tracked_hashes: Mapping[str, str],
    upstream_repos: Mapping[str, Any],
    zone_manifest_id: str,
) -> str:
    """Compute canonical Merkle-style SHA-256 over all Plane 1 files and upstream commits."""
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
    return sha256_bytes(canonical_json_bytes(envelope))


def estimate_spec_tokens(spec_text: str) -> dict[str, Any]:
    """Measure token counts using tiktoken cl100k_base when installed, without disguising byte estimates as measured tokens."""
    spec_bytes = spec_text.encode("utf-8")
    utf8_bytes = len(spec_bytes)
    words = len(spec_text.split())
    spec_sha = sha256_bytes(spec_bytes)
    result: dict[str, Any] = {
        "utf8_bytes": utf8_bytes,
        "words": words,
        "char_div4_estimate": utf8_bytes // 4,
        "cl100k_base_tokens": None,
        "cl100k_tokenizer": None,
        "qwen35_tokens": QWEN35_PINNED_SPEC_TOKENS if spec_sha == QWEN35_PINNED_SPEC_SHA256 else None,
        "qwen35_tokenizer": QWEN35_PINNED_TOKENIZER_ID if spec_sha == QWEN35_PINNED_SPEC_SHA256 else None,
    }
    try:
        import tiktoken  # type: ignore[import-not-found]

        enc = tiktoken.get_encoding("cl100k_base")
        result["cl100k_base_tokens"] = len(enc.encode(spec_text))
        ver = getattr(tiktoken, "__version__", "unknown")
        result["cl100k_tokenizer"] = f"tiktoken/{ver}:cl100k_base"
    except ImportError:
        result["cl100k_base_tokens"] = None
        result["cl100k_tokenizer"] = None
    return result


def load_upstream_deps_manifest(d_dir: Path | None = None) -> dict[str, Any]:
    target = (d_dir or deps_dir()) / "DEPS_MANIFEST.json"
    if not target.is_file():
        raise FileNotFoundError(f"DEPS_MANIFEST.json not found at {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    repos = data.get("repos")
    if not isinstance(repos, dict) or not repos:
        raise ValueError("DEPS_MANIFEST.json missing non-empty 'repos' mapping")
    return repos


def build_lineage_manifest(
    root: Path | None = None,
    d_dir: Path | None = None,
) -> dict[str, Any]:
    """Construct canonical `spec/lineage.json` from current Plane 1 files and pinned upstream SHAs."""
    base = (root or repo_root()).resolve()
    spec_path = base / "spec" / "plane1_formal_spec.md"
    if not spec_path.is_file():
        raise StaleLineageError("spec/plane1_formal_spec.md does not exist")

    zone_path = base / "schemas" / "zone-manifest.v0.1.json"
    zone_raw = json.loads(zone_path.read_text(encoding="utf-8"))
    computed_zone_id = compute_zone_manifest_id(zone_raw)
    stored_zone_id = str(zone_raw.get("manifest_id", ""))
    if not hmac.compare_digest(computed_zone_id, stored_zone_id):
        raise StaleLineageError(
            f"zone-manifest.v0.1.json digest mismatch: stored {stored_zone_id} != computed {computed_zone_id}"
        )
    if not hmac.compare_digest(computed_zone_id, CANONICAL_ZONE_MANIFEST_ID):
        raise StaleLineageError(
            f"zone_manifest_id drifted from canonical mde pin: {computed_zone_id}"
        )

    tracked = compute_tracked_plane1_hashes(base)
    upstream_raw = load_upstream_deps_manifest(d_dir)
    upstream_clean: dict[str, dict[str, Any]] = {}
    for repo_name, info in sorted(upstream_raw.items()):
        commit = str(info["commit"])
        if not COMMIT_RE.fullmatch(commit):
            raise StaleLineageError(f"upstream repo {repo_name} commit is not 40-hex: {commit!r}")
        upstream_clean[repo_name] = {
            "url": str(info["url"]),
            "commit": commit,
            "roles": list(info.get("roles", [])),
        }

    spec_bytes = spec_path.read_bytes()
    spec_sha = sha256_bytes(spec_bytes)
    spec_stats = estimate_spec_tokens(spec_bytes.decode("utf-8"))
    tree_sha = compute_corpus_tree_sha256(tracked, upstream_clean, computed_zone_id)

    # 40-hex domain commit identifier derived deterministically from Plane 1 spec SHA-256
    # so any 1-byte edit to Plane 1 immediately invalidates warp-modeld domain_commits as well.
    formal_domain_pin = spec_sha[:40]
    domain_commits = {
        "formal-verification": formal_domain_pin,
        "corpus": upstream_clean["Proven-Commons/mission"]["commit"],
        "weft-eido": upstream_clean["Moissanite-Labs/weft-eido"]["commit"],
    }

    return {
        "schema": "mcproof-lineage/v0.1",
        "domain": "formal-verification",
        "plane1_spec_path": "spec/plane1_formal_spec.md",
        "plane1_spec_sha256": spec_sha,
        "plane1_spec_bytes": len(spec_bytes),
        "plane1_spec_token_stats": spec_stats,
        "zone_manifest_id": computed_zone_id,
        "source_lineage": {
            "corpus_tree_sha256": tree_sha,
            "domain_commits": domain_commits,
            "contested_heads": [],
        },
        "upstream_repos": upstream_clean,
        "siliconcordat_commits": dict(sorted(SILICONCORDAT_PINNED_COMMITS.items())),
        "tracked_plane1_files": tracked,
        "_meta": {
            "gg.siliconcordat/mde": {
                "zone_manifest_id": computed_zone_id,
                "primary_zone": "formal_proof",
                "l1_bank_tag": 3,
                "adapter_class": "class1_rederivable",
                "hard_vetoes_enforced": [1, 2, 3, 4, 5],
            }
        },
    }


@dataclass(frozen=True)
class LineageVerificationReport:
    passed: bool
    stale_lineage: bool
    zone_manifest_drift: bool
    plane1_spec_sha256: str
    corpus_tree_sha256: str
    zone_manifest_id: str
    findings: tuple[str, ...]
    deps_manifest_verified: bool = False
    deps_checkouts_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "stale_lineage": self.stale_lineage,
            "zone_manifest_drift": self.zone_manifest_drift,
            "plane1_spec_sha256": self.plane1_spec_sha256,
            "corpus_tree_sha256": self.corpus_tree_sha256,
            "zone_manifest_id": self.zone_manifest_id,
            "deps_manifest_verified": self.deps_manifest_verified,
            "deps_checkouts_verified": self.deps_checkouts_verified,
            "findings": list(self.findings),
        }


def _git_head_sha(repo_path: Path) -> str | None:
    git_bin = shutil.which("git")
    if not git_bin or not (repo_path / ".git").exists():
        return None
    proc = subprocess.run(
        [git_bin, "-C", str(repo_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return None
    head = proc.stdout.strip()
    return head if COMMIT_RE.fullmatch(head) else None


def verify_lineage_manifest(
    root: Path | None = None,
    lineage_path: Path | None = None,
    *,
    d_dir: Path | None = None,
    require_deps: bool = False,
) -> LineageVerificationReport:
    """Recompute all Plane 1 digests from disk, cross-check pinned commits and checkouts, and fail closed (`stale_lineage`) on drift."""
    base = (root or repo_root()).resolve()
    l_path = lineage_path or (base / "spec" / "lineage.json")
    findings: list[str] = []
    stale = False
    zone_drift = False
    deps_manifest_verified = False
    deps_checkouts_verified = False

    if not l_path.is_file():
        return LineageVerificationReport(
            passed=False,
            stale_lineage=True,
            zone_manifest_drift=False,
            plane1_spec_sha256="",
            corpus_tree_sha256="",
            zone_manifest_id="",
            findings=(f"missing lineage manifest: {l_path.name}",),
        )

    try:
        stored = json.loads(l_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return LineageVerificationReport(
            passed=False,
            stale_lineage=True,
            zone_manifest_drift=False,
            plane1_spec_sha256="",
            corpus_tree_sha256="",
            zone_manifest_id="",
            findings=(f"invalid lineage JSON: {exc}",),
        )

    if stored.get("schema") != "mcproof-lineage/v0.1":
        findings.append(f"unexpected lineage schema: {stored.get('schema')!r}")
        stale = True

    meta = stored.get("_meta")
    if not isinstance(meta, dict) or list(meta.keys()) != ["gg.siliconcordat/mde"]:
        findings.append("Hard Veto 4 violation: _meta must contain only vendor key 'gg.siliconcordat/mde'")
        stale = True

    zone_file = base / "schemas" / "zone-manifest.v0.1.json"
    computed_zone_id = ""
    if not zone_file.is_file():
        findings.append("missing schemas/zone-manifest.v0.1.json")
        zone_drift = True
    else:
        zone_obj = json.loads(zone_file.read_text(encoding="utf-8"))
        computed_zone_id = compute_zone_manifest_id(zone_obj)
        if not hmac.compare_digest(computed_zone_id, str(zone_obj.get("manifest_id", ""))):
            findings.append("ERR_ZONE_MANIFEST_DRIFT: zone-manifest.v0.1.json internal digest mismatch")
            zone_drift = True
        if not hmac.compare_digest(computed_zone_id, str(stored.get("zone_manifest_id", ""))):
            findings.append(
                f"ERR_ZONE_MANIFEST_DRIFT: lineage zone_manifest_id {stored.get('zone_manifest_id')!r} "
                f"!= {computed_zone_id!r}"
            )
            zone_drift = True

    try:
        live_tracked = compute_tracked_plane1_hashes(base)
    except StaleLineageError as exc:
        findings.append(f"stale_lineage: {exc}")
        stale = True
        live_tracked = {}

    stored_tracked = stored.get("tracked_plane1_files", {})
    if not isinstance(stored_tracked, dict):
        findings.append("stale_lineage: tracked_plane1_files is not an object")
        stale = True
    else:
        for rel, live_sha in sorted(live_tracked.items()):
            rec_sha = str(stored_tracked.get(rel, ""))
            if not hmac.compare_digest(live_sha, rec_sha):
                findings.append(f"stale_lineage: {rel} disk sha256 {live_sha} != pinned {rec_sha}")
                stale = True
        for extra in sorted(set(stored_tracked.keys()) - set(live_tracked.keys())):
            findings.append(f"stale_lineage: unexpected tracked entry {extra}")
            stale = True

    spec_sha = live_tracked.get("spec/plane1_formal_spec.md", "")
    if spec_sha and not hmac.compare_digest(spec_sha, str(stored.get("plane1_spec_sha256", ""))):
        findings.append(
            f"stale_lineage: plane1_spec_sha256 {stored.get('plane1_spec_sha256')!r} != live {spec_sha}"
        )
        stale = True

    spec_file = base / "spec" / "plane1_formal_spec.md"
    if spec_file.is_file():
        actual_len = spec_file.stat().st_size
        if stored.get("plane1_spec_bytes") != actual_len:
            findings.append(
                f"stale_lineage: plane1_spec_bytes {stored.get('plane1_spec_bytes')!r} != live {actual_len}"
            )
            stale = True

    # Cross-check stored siliconcordat_commits against hardcoded SILICONCORDAT_PINNED_COMMITS
    stored_sc = stored.get("siliconcordat_commits")
    if not isinstance(stored_sc, dict):
        findings.append("stale_lineage: siliconcordat_commits missing or not an object")
        stale = True
    else:
        for sc_repo, pinned_sha in sorted(SILICONCORDAT_PINNED_COMMITS.items()):
            rec_sc_sha = str(stored_sc.get(sc_repo, ""))
            if not hmac.compare_digest(rec_sc_sha, pinned_sha):
                findings.append(
                    f"stale_lineage: siliconcordat_commits[{sc_repo!r}] {rec_sc_sha!r} != pinned {pinned_sha}"
                )
                stale = True
        for extra_sc in sorted(set(stored_sc.keys()) - set(SILICONCORDAT_PINNED_COMMITS.keys())):
            findings.append(f"stale_lineage: unexpected siliconcordat_commits key {extra_sc!r}")
            stale = True

    upstream = stored.get("upstream_repos", {})
    computed_tree = ""
    if isinstance(upstream, dict) and live_tracked and computed_zone_id:
        computed_tree = compute_corpus_tree_sha256(live_tracked, upstream, computed_zone_id)
        src_lineage = stored.get("source_lineage", {})
        rec_tree = str(src_lineage.get("corpus_tree_sha256", "")) if isinstance(src_lineage, dict) else ""
        if not hmac.compare_digest(computed_tree, rec_tree):
            findings.append(
                f"stale_lineage: source_lineage.corpus_tree_sha256 {rec_tree!r} != recomputed {computed_tree}"
            )
            stale = True
        contested = src_lineage.get("contested_heads", []) if isinstance(src_lineage, dict) else []
        if contested:
            findings.append(f"Hard Veto 2 contested_heads active: {contested}")
            stale = True
        dom_commits = src_lineage.get("domain_commits", {}) if isinstance(src_lineage, dict) else {}
        if not isinstance(dom_commits, dict) or dom_commits.get("formal-verification") != spec_sha[:40]:
            findings.append("stale_lineage: domain_commits['formal-verification'] does not bind plane1_spec_sha256[:40]")
            stale = True
        if isinstance(dom_commits, dict):
            mission_pin = str(upstream.get("Proven-Commons/mission", {}).get("commit", ""))
            eido_pin = str(upstream.get("Moissanite-Labs/weft-eido", {}).get("commit", ""))
            if mission_pin and not hmac.compare_digest(str(dom_commits.get("corpus", "")), mission_pin):
                findings.append("stale_lineage: domain_commits['corpus'] != upstream Proven-Commons/mission commit")
                stale = True
            if eido_pin and not hmac.compare_digest(str(dom_commits.get("weft-eido", "")), eido_pin):
                findings.append("stale_lineage: domain_commits['weft-eido'] != upstream Moissanite-Labs/weft-eido commit")
                stale = True
    else:
        findings.append("stale_lineage: missing upstream_repos or tracked files for tree digest")
        stale = True

    # Cross-check deps/DEPS_MANIFEST.json and actual git HEADs when present on disk (or when require_deps=True)
    actual_deps = (d_dir or (base.parent / "deps") if root is not None and d_dir is None else (d_dir or deps_dir())).resolve()
    deps_manifest_file = actual_deps / "DEPS_MANIFEST.json"
    manifest_dir_map: dict[str, str] = dict(UPSTREAM_REPO_DIRS)
    if deps_manifest_file.is_file() and isinstance(upstream, dict):
        try:
            live_deps = load_upstream_deps_manifest(actual_deps)
            manifest_ok = True
            for r_name, r_info in sorted(upstream.items()):
                if r_name not in live_deps:
                    findings.append(f"stale_lineage: {r_name} missing from DEPS_MANIFEST.json")
                    stale = True
                    manifest_ok = False
                    continue
                d_entry = live_deps[r_name]
                if "dir" in d_entry:
                    manifest_dir_map[r_name] = str(d_entry["dir"])
                live_commit = str(d_entry.get("commit", ""))
                stored_commit = str(r_info.get("commit", "")) if isinstance(r_info, dict) else ""
                if not hmac.compare_digest(live_commit, stored_commit):
                    findings.append(
                        f"stale_lineage: DEPS_MANIFEST.json commit for {r_name} ({live_commit}) != lineage.json ({stored_commit})"
                    )
                    stale = True
                    manifest_ok = False
            for extra_dep in sorted(set(live_deps.keys()) - set(upstream.keys())):
                findings.append(f"stale_lineage: unexpected repo {extra_dep} in DEPS_MANIFEST.json")
                stale = True
                manifest_ok = False
            deps_manifest_verified = manifest_ok
        except (OSError, ValueError) as exc:
            findings.append(f"stale_lineage: invalid DEPS_MANIFEST.json: {exc}")
            stale = True
    elif require_deps:
        findings.append(f"stale_lineage: required DEPS_MANIFEST.json missing at {deps_manifest_file.name}")
        stale = True

    if isinstance(upstream, dict) and upstream:
        checked_count = 0
        all_heads_match = True
        for r_name, r_info in sorted(upstream.items()):
            sub_dir = manifest_dir_map.get(r_name, r_name.split("/")[-1])
            repo_checkout = actual_deps / sub_dir
            expected_commit = str(r_info.get("commit", "")) if isinstance(r_info, dict) else ""
            if (repo_checkout / ".git").exists():
                head_sha = _git_head_sha(repo_checkout)
                checked_count += 1
                if head_sha is None or not hmac.compare_digest(head_sha, expected_commit):
                    findings.append(
                        f"stale_lineage: git checkout {sub_dir} HEAD {head_sha!r} != pinned {expected_commit}"
                    )
                    stale = True
                    all_heads_match = False
            elif require_deps:
                findings.append(f"stale_lineage: required dep checkout missing for {r_name} ({sub_dir})")
                stale = True
                all_heads_match = False
        if checked_count == len(upstream) and all_heads_match:
            deps_checkouts_verified = True

    # Also cross-check sibling siliconcordat git checkouts when present underactual_deps or parent siliconcordat/
    for sc_repo, pinned_sha in sorted(SILICONCORDAT_PINNED_COMMITS.items()):
        short_name = sc_repo.split("/")[-1]
        for cand_sc in (actual_deps / short_name, base.parent.parent / "siliconcordat" / short_name):
            if (cand_sc / ".git").exists():
                sc_head = _git_head_sha(cand_sc)
                if sc_head is not None and not hmac.compare_digest(sc_head, pinned_sha):
                    findings.append(
                        f"stale_lineage: siliconcordat checkout {short_name} HEAD {sc_head} != pinned {pinned_sha}"
                    )
                    stale = True
                break

    passed = (not findings) and (not stale) and (not zone_drift)
    return LineageVerificationReport(
        passed=passed,
        stale_lineage=stale,
        zone_manifest_drift=zone_drift,
        plane1_spec_sha256=spec_sha,
        corpus_tree_sha256=computed_tree,
        zone_manifest_id=computed_zone_id,
        findings=tuple(findings),
        deps_manifest_verified=deps_manifest_verified,
        deps_checkouts_verified=deps_checkouts_verified,
    )
