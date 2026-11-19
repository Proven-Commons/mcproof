"""Planted-bug mutation-kill runner enforcing >= 80% exact rational kill floor under python3 -O -B -W error."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from .paths import dep_repo

KILL_FLOOR_NUM = 4
KILL_FLOOR_DEN = 5  # Exact 4/5 = 80% rational floor (checked via killed * 5 >= total * 4)


def strict_python_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build deterministic single-threaded environment for python3 -O -B -W error execution."""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    if extra:
        env.update(extra)
    return env


def run_python_strict(
    script_or_args: Sequence[str],
    *,
    cwd: Path | None = None,
    stdin_text: str | None = None,
    timeout_sec: int = 60,
    extra_env: Mapping[str, str] | None = None,
    isolated: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute Python with `-O -B -W error` so bare `assert`s are stripped and warnings fail closed."""
    flags = ["-I", "-O", "-B", "-W", "error"] if isolated else ["-O", "-B", "-W", "error"]
    cmd = [sys.executable, *flags, *script_or_args]
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=strict_python_env(extra_env),
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def run_candidate_python_confined(
    script_or_args: Sequence[str],
    *,
    writable_dir: Path,
    timeout_sec: int = 30,
    sandbox_mode: str = "auto",
) -> tuple[subprocess.CompletedProcess[str] | None, bool, str | None]:
    """Run untrusted candidate Python inside Linux `bwrap` (no-net, ro-root, tmpfs home) when available.

    Trust boundary: on hosts without Linux `bwrap` (macOS, Windows, unprivileged containers),
    `sandbox_mode="auto"` falls back to isolated `-I -O -B -W error` with a disposable `HOME`/`USERPROFILE`
    and records `python_sandboxed=False`; `sandbox_mode="bwrap"` fails closed with `PYTHON_SANDBOX_UNAVAILABLE`.
    """
    if sandbox_mode not in ("auto", "bwrap", "none"):
        raise ValueError(f"unsupported sandbox_mode {sandbox_mode!r}")

    isolated_home = writable_dir / "_isolated_home"
    isolated_home.mkdir(parents=True, exist_ok=True)
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "HOME": str(isolated_home),
        "USERPROFILE": str(isolated_home),
        "TMPDIR": str(writable_dir),
        "TEMP": str(writable_dir),
        "TMP": str(writable_dir),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }

    bwrap_bin = shutil.which("bwrap")
    can_bwrap = bwrap_bin is not None and sys.platform.startswith("linux")
    if sandbox_mode in ("auto", "bwrap") and can_bwrap and bwrap_bin is not None:
        w_str = str(writable_dir.resolve())
        bwrap_cmd = [
            bwrap_bin,
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--bind",
            w_str,
            w_str,
            "--unshare-net",
            "--die-with-parent",
            "--chdir",
            w_str,
            sys.executable,
            "-I",
            "-O",
            "-B",
            "-W",
            "error",
            *script_or_args,
        ]
        proc = subprocess.run(
            bwrap_cmd,
            cwd=writable_dir,
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode == 0 or sandbox_mode == "bwrap":
            return proc, True, None
        # Some containerized Linux runners forbid user namespaces inside bwrap; only auto mode falls back
    elif sandbox_mode == "bwrap":
        return None, False, "Linux bubblewrap (`bwrap`) is unavailable for `sandbox_mode='bwrap'`"

    proc = subprocess.run(
        [sys.executable, "-I", "-O", "-B", "-W", "error", *script_or_args],
        cwd=writable_dir,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    return proc, False, None


def synthesize_adversarial_mutations(valid_cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Generate deterministic planted-bug mutations from valid (args/kwargs or certificate) cases."""
    mutations: list[dict[str, Any]] = []

    def _mutate_value(val: Any, kind: str) -> Any:
        if type(val) is int:
            if kind == "plus_one":
                return val + 1
            if kind == "minus_one":
                return val - 1
            if kind == "flip_sign":
                return -val if val != 0 else 999999
            if kind == "large_offset":
                return val + 1000003
            return val + 7
        if isinstance(val, str):
            return val + "_CORRUPTED" if kind != "empty" else ""
        if isinstance(val, list):
            if not val:
                return [999999]
            copied = list(val)
            copied[-1] = _mutate_value(copied[-1], kind)
            return copied
        if isinstance(val, dict):
            if not val:
                return {"__corrupted__": 1}
            copied = dict(val)
            last_k = sorted(copied.keys())[-1]
            copied[last_k] = _mutate_value(copied[last_k], kind)
            return copied
        if type(val) is bool:
            return not val
        return None

    kinds = ("plus_one", "minus_one", "flip_sign", "large_offset", "alt_offset")
    for idx, case in enumerate(valid_cases):
        args = list(case.get("args", []))
        kwargs = dict(case.get("kwargs", {}))
        for k_idx, kind in enumerate(kinds):
            if args:
                mut_args = list(args)
                target_pos = len(mut_args) - 1
                mut_args[target_pos] = _mutate_value(mut_args[target_pos], kind)
                if mut_args != args:
                    mutations.append({
                        "name": f"auto_case{idx}_arg{target_pos}_{kind}",
                        "args": mut_args,
                        "kwargs": kwargs,
                    })
            elif kwargs:
                mut_kw = dict(kwargs)
                target_key = sorted(mut_kw.keys())[-1]
                mut_kw[target_key] = _mutate_value(mut_kw[target_key], kind)
                if mut_kw != kwargs:
                    mutations.append({
                        "name": f"auto_case{idx}_kw_{target_key}_{kind}",
                        "args": [],
                        "kwargs": mut_kw,
                    })
            if len(mutations) >= 5 and k_idx >= 1:
                break
    return mutations


_MUTATION_DRIVER_CODE = """from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
mod_path = Path(payload["checker_path"])
fn_name = payload["entry_fn"]

spec = importlib.util.spec_from_file_location("candidate_checker_mod", mod_path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load candidate checker module")
mod = importlib.util.module_from_spec(spec)
sys.modules["candidate_checker_mod"] = mod
spec.loader.exec_module(mod)

if not hasattr(mod, fn_name):
    raise AttributeError(f"candidate checker missing function {fn_name!r}")
fn = getattr(mod, fn_name)

valid_outcomes = []
for idx, item in enumerate(payload["valid_cases"]):
    args = item.get("args", [])
    kwargs = item.get("kwargs", {})
    try:
        res = fn(*args, **kwargs)
        passed = (res is True)
        valid_outcomes.append({"index": idx, "accepted": passed, "error": None})
    except Exception as exc:
        valid_outcomes.append({"index": idx, "accepted": False, "error": f"{type(exc).__name__}: {exc}"})

mutation_outcomes = []
for idx, item in enumerate(payload["mutations"]):
    name = item.get("name", f"mut_{idx}")
    args = item.get("args", [])
    kwargs = item.get("kwargs", {})
    try:
        res = fn(*args, **kwargs)
        killed = (res is False)
        mutation_outcomes.append({"name": name, "killed": killed, "returned": repr(res), "error": None})
    except (ValueError, TypeError, KeyError, ArithmeticError, LookupError, RuntimeError) as exc:
        mutation_outcomes.append({"name": name, "killed": True, "returned": None, "error": f"{type(exc).__name__}: {exc}"})

result_path = Path(payload["result_path"])
result_path.write_text(
    json.dumps({"valid_outcomes": valid_outcomes, "mutation_outcomes": mutation_outcomes}),
    encoding="utf-8",
)
"""


@dataclass(frozen=True)
class MutationKillReport:
    passed: bool
    good_cases_total: int
    good_cases_passed: int
    mutations_total: int
    mutations_killed: int
    kill_fraction: str
    kill_rate_bps: int
    kill_floor_bps: int
    survived_mutations: tuple[str, ...]
    findings: tuple[dict[str, Any], ...]
    python_sandboxed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "good_cases_total": self.good_cases_total,
            "good_cases_passed": self.good_cases_passed,
            "mutations_total": self.mutations_total,
            "mutations_killed": self.mutations_killed,
            "kill_fraction": self.kill_fraction,
            "kill_rate_bps": self.kill_rate_bps,
            "kill_floor_bps": self.kill_floor_bps,
            "survived_mutations": list(self.survived_mutations),
            "python_sandboxed": self.python_sandboxed,
            "findings": list(self.findings),
        }


def run_checker_mutation_suite(
    checker_source: str,
    *,
    entry_fn: str = "verify",
    valid_cases: Sequence[Mapping[str, Any]] = (),
    planted_mutations: Sequence[Mapping[str, Any]] | None = None,
    kill_floor_num: int = KILL_FLOOR_NUM,
    kill_floor_den: int = KILL_FLOOR_DEN,
    timeout_sec: int = 30,
    sandbox_mode: str = "auto",
) -> MutationKillReport:
    """Execute candidate checker under `python3 -I -O -B -W error` against valid inputs and planted mutations."""
    findings: list[dict[str, Any]] = []
    floor_bps = (kill_floor_num * 10000) // kill_floor_den

    if not valid_cases:
        findings.append({
            "rule": "MISSING_VALID_CASES",
            "message": "mutation suite requires at least one valid positive test case",
        })
        return MutationKillReport(
            passed=False,
            good_cases_total=0,
            good_cases_passed=0,
            mutations_total=0,
            mutations_killed=0,
            kill_fraction="0/0",
            kill_rate_bps=0,
            kill_floor_bps=floor_bps,
            survived_mutations=(),
            findings=tuple(findings),
            python_sandboxed=False,
        )

    mutations = list(planted_mutations) if planted_mutations is not None else synthesize_adversarial_mutations(valid_cases)
    if not mutations:
        findings.append({
            "rule": "MISSING_PLANTED_MUTATIONS",
            "message": "mutation suite requires at least one planted corruption case",
        })
        return MutationKillReport(
            passed=False,
            good_cases_total=len(valid_cases),
            good_cases_passed=0,
            mutations_total=0,
            mutations_killed=0,
            kill_fraction="0/0",
            kill_rate_bps=0,
            kill_floor_bps=floor_bps,
            survived_mutations=(),
            findings=tuple(findings),
            python_sandboxed=False,
        )

    with tempfile.TemporaryDirectory(prefix="mcproof_mut_") as tmp_str:
        tmp_dir = Path(tmp_str)
        checker_file = tmp_dir / "candidate_checker.py"
        driver_file = tmp_dir / "driver.py"
        payload_file = tmp_dir / "payload.json"
        result_file = tmp_dir / "result.json"

        checker_file.write_text(checker_source, encoding="utf-8")
        driver_file.write_text(_MUTATION_DRIVER_CODE, encoding="utf-8")
        payload_file.write_text(
            json.dumps({
                "checker_path": str(checker_file),
                "entry_fn": entry_fn,
                "valid_cases": list(valid_cases),
                "mutations": mutations,
                "result_path": str(result_file),
            }),
            encoding="utf-8",
        )

        proc, py_sandboxed, sb_err = run_candidate_python_confined(
            [str(driver_file), str(payload_file)],
            writable_dir=tmp_dir,
            timeout_sec=timeout_sec,
            sandbox_mode=sandbox_mode,
        )
        if sb_err is not None or proc is None:
            findings.append({
                "rule": "PYTHON_SANDBOX_UNAVAILABLE",
                "message": sb_err or "candidate sandbox unavailable",
            })
            return MutationKillReport(
                passed=False,
                good_cases_total=len(valid_cases),
                good_cases_passed=0,
                mutations_total=len(mutations),
                mutations_killed=0,
                kill_fraction=f"0/{len(mutations)}",
                kill_rate_bps=0,
                kill_floor_bps=floor_bps,
                survived_mutations=tuple(str(m.get("name", f"mut_{i}")) for i, m in enumerate(mutations)),
                findings=tuple(findings),
                python_sandboxed=False,
            )

        if proc.returncode != 0:
            tail = " | ".join(line.strip() for line in ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines()[-5:] if line.strip())
            findings.append({
                "rule": "STRICT_PYTHON_EXEC_ERROR",
                "message": f"checker failed under `python3 -I -O -B -W error`: {tail}",
            })
            return MutationKillReport(
                passed=False,
                good_cases_total=len(valid_cases),
                good_cases_passed=0,
                mutations_total=len(mutations),
                mutations_killed=0,
                kill_fraction=f"0/{len(mutations)}",
                kill_rate_bps=0,
                kill_floor_bps=floor_bps,
                survived_mutations=tuple(str(m.get("name", f"mut_{i}")) for i, m in enumerate(mutations)),
                findings=tuple(findings),
                python_sandboxed=py_sandboxed,
            )

        if not result_file.is_file():
            findings.append({
                "rule": "DRIVER_OUTPUT_MISSING_OR_CORRUPT",
                "message": "mutation driver did not produce result.json",
            })
            return MutationKillReport(
                passed=False,
                good_cases_total=len(valid_cases),
                good_cases_passed=0,
                mutations_total=len(mutations),
                mutations_killed=0,
                kill_fraction=f"0/{len(mutations)}",
                kill_rate_bps=0,
                kill_floor_bps=floor_bps,
                survived_mutations=tuple(str(m.get("name", f"mut_{i}")) for i, m in enumerate(mutations)),
                findings=tuple(findings),
                python_sandboxed=py_sandboxed,
            )

        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            findings.append({
                "rule": "DRIVER_OUTPUT_MISSING_OR_CORRUPT",
                "message": f"corrupt mutation driver result.json: {exc}",
            })
            return MutationKillReport(
                passed=False,
                good_cases_total=len(valid_cases),
                good_cases_passed=0,
                mutations_total=len(mutations),
                mutations_killed=0,
                kill_fraction=f"0/{len(mutations)}",
                kill_rate_bps=0,
                kill_floor_bps=floor_bps,
                survived_mutations=tuple(str(m.get("name", f"mut_{i}")) for i, m in enumerate(mutations)),
                findings=tuple(findings),
                python_sandboxed=py_sandboxed,
            )

    valid_outcomes = data["valid_outcomes"]
    mut_outcomes = data["mutation_outcomes"]

    good_passed = sum(1 for item in valid_outcomes if item["accepted"])
    if good_passed != len(valid_outcomes):
        for item in valid_outcomes:
            if not item["accepted"]:
                findings.append({
                    "rule": "REJECTED_VALID_FIXTURE",
                    "message": f"checker rejected valid fixture #{item['index']} (error={item['error']})",
                })

    killed = 0
    survived: list[str] = []
    for item in mut_outcomes:
        if item["killed"]:
            killed += 1
        else:
            survived.append(str(item["name"]))

    total_mut = len(mut_outcomes)
    rate_bps = (killed * 10000) // total_mut if total_mut > 0 else 0
    meets_floor = (total_mut > 0) and ((killed * kill_floor_den) >= (total_mut * kill_floor_num))
    if not meets_floor:
        findings.append({
            "rule": "MUTATION_KILL_FLOOR_BREACH",
            "message": (
                f"planted-bug kill rate {killed}/{total_mut} ({rate_bps} bps) "
                f"is below required floor {kill_floor_num}/{kill_floor_den} ({floor_bps} bps); "
                f"survived={survived}"
            ),
        })

    passed = (good_passed == len(valid_outcomes)) and meets_floor and (len(findings) == 0)
    return MutationKillReport(
        passed=passed,
        good_cases_total=len(valid_outcomes),
        good_cases_passed=good_passed,
        mutations_total=total_mut,
        mutations_killed=killed,
        kill_fraction=f"{killed}/{total_mut}",
        kill_rate_bps=rate_bps,
        kill_floor_bps=floor_bps,
        survived_mutations=tuple(survived),
        findings=tuple(findings),
        python_sandboxed=py_sandboxed,
    )


def parse_f0_corruption_lines(stdout_text: str, returncode: int, stderr_text: str = "") -> tuple[int, int, list[str], list[dict[str, Any]]]:
    """Parse `run_gate_corruptions.py` output without fabricating a denominator when output is empty/unparseable."""
    lines = stdout_text.splitlines()
    killed = sum(1 for ln in lines if ln.startswith("PASS: corruption "))
    failed_corrs = [ln for ln in lines if ln.startswith("FAIL: corruption ")]
    total = killed + len(failed_corrs)
    findings: list[dict[str, Any]] = []
    if total == 0:
        findings.append({
            "rule": "F0_CORRUPTION_OUTPUT_UNPARSEABLE",
            "message": f"run_gate_corruptions.py emitted zero parseable PASS/FAIL lines (exit {returncode}): {(stdout_text + stderr_text).strip()[:200]}",
        })
    if returncode != 0 or failed_corrs:
        findings.append({
            "rule": "F0_CORRUPTION_ESCAPED",
            "message": f"run_gate_corruptions.py exited {returncode}: {(stdout_text + stderr_text).strip()[:240]}",
        })
    return killed, total, failed_corrs, findings


def run_f0_gate_and_corruptions(f0_root: Path | None = None, *, timeout_sec: int = 60) -> MutationKillReport:
    """Run Foundation-0 `scripts/gate.py` + `tests/run_gate_corruptions.py` under `python3 -O -B -W error`."""
    source_root = (f0_root or dep_repo("f0")).resolve()
    findings: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="mcproof_f0_") as tmp_str:
        work_copy = Path(tmp_str) / "f0"
        shutil.copytree(source_root, work_copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))

        good_proc = run_python_strict(
            [str(work_copy / "scripts" / "gate.py"), "--root", str(work_copy)],
            cwd=work_copy,
            timeout_sec=timeout_sec,
        )
        good_ok = good_proc.returncode == 0
        if not good_ok:
            findings.append({
                "rule": "F0_GATE_GOOD_DATA_FAILED",
                "message": f"f0/scripts/gate.py failed on clean copy: {(good_proc.stdout + good_proc.stderr).strip()[:240]}",
            })

        corr_proc = run_python_strict(
            [str(work_copy / "tests" / "run_gate_corruptions.py")],
            cwd=work_copy,
            timeout_sec=timeout_sec,
        )
        killed, total, failed_corrs, corr_findings = parse_f0_corruption_lines(
            corr_proc.stdout or "",
            corr_proc.returncode,
            corr_proc.stderr or "",
        )
        findings.extend(corr_findings)

    rate_bps = (killed * 10000) // total if total > 0 else 0
    floor_bps = (KILL_FLOOR_NUM * 10000) // KILL_FLOOR_DEN
    meets_floor = (total > 0) and ((killed * KILL_FLOOR_DEN) >= (total * KILL_FLOOR_NUM))
    if not meets_floor:
        findings.append({
            "rule": "MUTATION_KILL_FLOOR_BREACH",
            "message": f"f0 corruption kill rate {killed}/{total} below 4/5 floor",
        })

    return MutationKillReport(
        passed=good_ok and meets_floor and len(findings) == 0,
        good_cases_total=1,
        good_cases_passed=1 if good_ok else 0,
        mutations_total=total,
        mutations_killed=killed,
        kill_fraction=f"{killed}/{total}",
        kill_rate_bps=rate_bps,
        kill_floor_bps=floor_bps,
        survived_mutations=tuple(failed_corrs),
        findings=tuple(findings),
    )
