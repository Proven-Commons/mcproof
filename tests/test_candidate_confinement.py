"""Host writes, env leaks, and trusted-input swaps must fail closed.

Each test is aimed at one fix. Reverting that fix fails its test:
a passthrough `run_confined_command` writes the host marker, dropping `env -i`
leaks the sentinel, `--ro-bind / /` makes `.git/config` and the sockets visible,
a line-anchored `attribute` regex misses the split form, skipping the restore
lets the kernel see the rewritten Proofs file, and an uncaught `json.loads`
raises on malformed `comparator.json`.
"""

from __future__ import annotations

import io
from pathlib import Path
import shutil
import uuid

import pytest

from helpers import expect_false, expect_in, expect_true, has_dep, has_lean_toolchain
from mcproof.cli import main as cli_main
from mcproof.lean_harness import (
    _SANDBOX_AS_BYTES,
    _SANDBOX_CPU_SEC,
    _spawn_confined,
    linux_bwrap_functional,
    lint_lean4_source,
    verify_lean4_project_comparator,
    verify_lean4_source,
)
from mcproof.oracles import grade_family_completion, run_prose_and_mixed_zone_oracle
from mcproof.repair_loop import _family_c_build_side_effect_findings, _run_family_c_real_lean_turn
from test_domain_and_repair_loop import _family_c_refl_harness, _family_c_with_theorems


def _skip_without_confinement() -> None:
    if not has_lean_toolchain():
        pytest.skip("Lean is absent, so this confinement path was not exercised")
    if not linux_bwrap_functional():
        pytest.skip("bwrap confinement probe failed, so this path was not exercised")


def _skip_without_soko() -> None:
    if not has_dep("soko"):
        pytest.skip("soko is absent, so the Lean auditor path was not exercised")


def _hidden_eval(marker: Path) -> str:
    """`#eval` hidden by a short raw-string closer. The lint does not see it, so the compile runs."""
    return (
        "theorem host_marker_witness (n : Nat) : n = n := rfl\n"
        'def s := r##"foo"#\n'
        f'#eval IO.FS.writeFile "{marker}" "p"\n'
    )


def _expect_host_marker_absent(run) -> None:
    marker = Path("/tmp") / f"mcproof-host-marker-{uuid.uuid4().hex}"
    marker.unlink(missing_ok=True)
    try:
        run(marker)
        expect_false(marker.is_file(), f"candidate wrote {marker}; the compile was not confined")
    finally:
        marker.unlink(missing_ok=True)


def test_verify_lean4_source_cannot_write_a_host_marker() -> None:
    """Family A's compiler. A passthrough sandbox writes the marker and this fails."""
    _skip_without_confinement()
    _skip_without_soko()

    def run(marker: Path) -> None:
        verify_lean4_source(_hidden_eval(marker))

    _expect_host_marker_absent(run)


def test_family_a_grader_cannot_write_a_host_marker() -> None:
    _skip_without_confinement()
    _skip_without_soko()

    def run(marker: Path) -> None:
        grade_family_completion("A", "```lean\n" + _hidden_eval(marker) + "```\n")

    _expect_host_marker_absent(run)


def test_family_c_grader_cannot_write_a_host_marker() -> None:
    """`grade_family_completion` for Family C runs before the sandboxed harness."""
    _skip_without_confinement()
    _skip_without_soko()

    def run(marker: Path) -> None:
        grade_family_completion("C", "```lean\n" + _hidden_eval(marker) + "```\n")

    _expect_host_marker_absent(run)


def test_family_d_embedded_lean_cannot_write_a_host_marker() -> None:
    _skip_without_confinement()
    _skip_without_soko()

    def run(marker: Path) -> None:
        text = "```lean\n" + _hidden_eval(marker) + "```\n"
        run_prose_and_mixed_zone_oracle(
            text,
            require_formal_sections=False,
            require_data_eido_skip=False,
            verify_embedded_lean=True,
            verify_verdict_shas=False,
        )
        grade_family_completion("D", text)

    _expect_host_marker_absent(run)


def test_cli_lean_cannot_write_a_host_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    _skip_without_confinement()
    _skip_without_soko()

    def run(marker: Path) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(_hidden_eval(marker)))
        cli_main(["lean", "-"])

    _expect_host_marker_absent(run)


def test_run_lean4_verification_cannot_write_a_host_marker() -> None:
    _skip_without_confinement()
    if not has_dep("soko"):
        pytest.skip("soko is absent, so run_lean4_verification was not exercised")
    from verification.graders.common import run_lean4_verification

    def run(marker: Path) -> None:
        run_lean4_verification(_hidden_eval(marker))

    _expect_host_marker_absent(run)


def test_execution_lint_stops_verify_lean4_source_before_compile(monkeypatch: pytest.MonkeyPatch) -> None:
    """`attribute [init]` is a lint finding. Removing the early return calls Lean and this fails."""
    _skip_without_soko()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Lean ran after an execution lint")

    monkeypatch.setattr("mcproof.lean_harness.run_confined_command", boom)
    monkeypatch.setattr("mcproof.lean_harness.subprocess.run", boom)
    res = verify_lean4_source(
        'def pwnInit : IO Unit := pure ()\nattribute [init] pwnInit\n',
        require_theorem=False,
    )
    expect_in("FORBIDDEN_INIT_ATTRIBUTE", {f["rule"] for f in res.findings})


def test_execution_lint_stops_run_lean4_verification_before_compile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """soko accepts `attribute [init]`. Removing this lint stop compiles it and this fails."""
    if not has_dep("soko"):
        pytest.skip("soko is absent, so run_lean4_verification was not exercised")
    from verification.graders.common import run_lean4_verification

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Lean ran after an execution lint")

    monkeypatch.setattr("mcproof.lean_harness.run_confined_command", boom)
    monkeypatch.setattr("verification.graders.common.run_confined_command", boom)
    rep = run_lean4_verification('def pwnInit : IO Unit := pure ()\nattribute [init] pwnInit\n')
    expect_false(rep["ok"], str(rep))
    expect_true(any(str(err).startswith("lint:FORBIDDEN_INIT_ATTRIBUTE") for err in rep["errors"]), rep)


def _skip_without_bwrap() -> None:
    if not shutil.which("bwrap"):
        pytest.skip("bwrap is absent, so this confinement check was not exercised")


def test_confined_process_does_not_leak_parent_environ(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Dropping `env -i` puts this sentinel in `/proc/1/environ` and this fails."""
    _skip_without_bwrap()
    monkeypatch.setenv("MCPROOF_SANDBOX_SENTINEL", "leakme-parent-env")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "supersecret-git")
    proc = _spawn_confined(
        [
            "python3",
            "-c",
            "from pathlib import Path; print('ENV_BEGIN'); print(Path('/proc/1/environ').read_bytes().decode('utf-8','replace'))",
        ],
        cwd=tmp_path,
        caller_env={},
        timeout_sec=30,
    )
    text = proc.stdout or ""
    expect_true(proc.returncode == 0 and "ENV_BEGIN" in text, (proc.returncode, proc.stderr))
    expect_false("leakme-parent-env" in text, text)
    expect_false("GIT_CONFIG_VALUE_0" in text, text)
    expect_false("supersecret-git" in text, text)


def test_confined_process_cannot_read_git_config(tmp_path: Path) -> None:
    """`--ro-bind / /` makes the checkout config readable and this fails."""
    _skip_without_bwrap()
    proc = _spawn_confined(
        [
            "python3",
            "-c",
            "from pathlib import Path; p=Path('/agent/repos/mcproof/.git/config'); print('YES' if p.is_file() else 'NO')",
        ],
        cwd=tmp_path,
        caller_env={},
        timeout_sec=30,
    )
    expect_true(proc.returncode == 0, proc.stderr)
    expect_true((proc.stdout or "").strip() == "NO", (proc.stdout, proc.stderr))


def test_confined_process_cannot_connect_host_sockets(tmp_path: Path) -> None:
    """A visible `/run` lets the sandbox connect to the host sockets and this fails."""
    _skip_without_bwrap()
    script = (
        "import socket\n"
        "socks=('/run/cursor/api.sock','/run/host-services/ssh-auth.sock')\n"
        "ok=[]\n"
        "for sock in socks:\n"
        "    h=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "    h.settimeout(0.3)\n"
        "    try:\n"
        "        h.connect(sock)\n"
        "        ok.append(sock)\n"
        "    except OSError:\n"
        "        pass\n"
        "    finally:\n"
        "        h.close()\n"
        "print('CONNECT_OK' if ok else 'NO')\n"
    )
    proc = _spawn_confined(["python3", "-c", script], cwd=tmp_path, caller_env={}, timeout_sec=30)
    expect_true(proc.returncode == 0, proc.stderr)
    expect_true((proc.stdout or "").strip() == "NO", (proc.stdout, proc.stderr))


def test_confined_process_has_resource_limits(tmp_path: Path) -> None:
    """Removing `prlimit` leaves the address space unlimited and this fails."""
    _skip_without_bwrap()
    script = (
        "import resource\n"
        f"print(resource.getrlimit(resource.RLIMIT_AS)[0])\n"
        f"print(resource.getrlimit(resource.RLIMIT_CPU)[0])\n"
    )
    proc = _spawn_confined(["python3", "-c", script], cwd=tmp_path, caller_env={}, timeout_sec=30)
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    expect_true(len(lines) == 2, proc.stdout + (proc.stderr or ""))
    expect_true(int(lines[0]) == _SANDBOX_AS_BYTES, lines)
    expect_true(int(lines[1]) == _SANDBOX_CPU_SEC, lines)


def test_split_attribute_init_is_a_lint_finding() -> None:
    """A column-zero regex misses both of these. Restoring it makes this fail."""
    samples = (
        "theorem t (n : Nat) : n = n := rfl attribute [init] pwnInit\n",
        "theorem t (n : Nat) : n = n := rfl\nattribute\n[init] pwnInit\n",
    )
    for src in samples:
        if has_dep("soko"):
            rules = {f["rule"] for f in lint_lean4_source(src, require_theorem=False)["findings"]}
            expect_in("FORBIDDEN_INIT_ATTRIBUTE", rules, src)
        side = {f["rule"] for f in _family_c_build_side_effect_findings(src)}
        expect_in("FORBIDDEN_BUILD_SIDE_EFFECT", side, src)


def test_family_c_split_attribute_init_is_rejected() -> None:
    """The full turn used to accept these with no rules. A line-anchored regex does that again."""
    _skip_without_confinement()
    samples = (
        "theorem CrtPair.Spec.crt_mod_left (n : Nat) : n = n := rfl attribute [init] pwnInit\n"
        "def pwnInit : IO Unit := pure ()\n",
        "attribute\n[init] pwnInit\ndef pwnInit : IO Unit := pure ()\n",
    )
    for snippet in samples:
        findings = _run_family_c_real_lean_turn(
            _family_c_refl_harness(),
            _family_c_with_theorems(snippet),
        )
        rules = {f["rule"] for f in findings}
        expect_true(
            "FORBIDDEN_BUILD_SIDE_EFFECT" in rules or "FORBIDDEN_INIT_ATTRIBUTE" in rules,
            findings,
        )


def test_family_c_restores_proofs_and_comparator_after_the_build() -> None:
    """The build rewrites both files. Skipping the restore drops the axiom finding or raises."""
    _skip_without_confinement()
    _skip_without_soko()
    snippet = (
        "axiom planted_bad : False\n"
        "run_meta do\n"
        "  IO.FS.writeFile \"CrtPair/Proofs.lean\" "
        "\"import CrtPair\\n\\ntheorem CrtPair.Spec.crt_mod_left (n : Nat) : n = n := rfl\\n"
        "theorem CrtPair.Spec.crt_mod_right (n : Nat) : n = n := rfl\\n\"\n"
        "  IO.FS.writeFile \"comparator.json\" \"not-json\"\n"
    )
    findings = _run_family_c_real_lean_turn(
        _family_c_refl_harness(),
        _family_c_with_theorems(snippet, prelude="import Lean\n"),
    )
    rules = {f["rule"] for f in findings}
    expect_in("EXTRA_AXIOM_DECL", rules, str(findings))
    expect_false("COMPARATOR_JSON_MALFORMED" in rules, findings)


def test_malformed_comparator_json_is_a_finding(tmp_path: Path) -> None:
    """An uncaught `json.loads` raises `JSONDecodeError` and this errors instead of failing closed."""
    (tmp_path / "comparator.json").write_text("{", encoding="utf-8")
    res = verify_lean4_project_comparator(tmp_path)
    expect_false(res.passed)
    expect_in("COMPARATOR_JSON_MALFORMED", {f["rule"] for f in res.findings})
