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
import json
from pathlib import Path
import shutil
import socket
import threading
import uuid

import pytest

from helpers import expect_false, expect_in, expect_true, has_dep, has_lean_toolchain
from mcproof.cli import main as cli_main
from mcproof.lean_harness import (
    _SANDBOX_CPU_SEC,
    _address_space_cap_bytes,
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
    memtotal = 0
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            memtotal = int(line.split()[1]) * 1024
    soft = int(lines[0])
    # A fixed 32 GiB cap is above this host. Unlimited is -1, and -1 <= MemTotal.
    expect_true(memtotal > 0 and soft > 0 and soft <= memtotal, (soft, memtotal))
    expect_true(soft == _address_space_cap_bytes(), (soft, _address_space_cap_bytes()))
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


_ORIGINAL_PROOFS = "import Probe\ntheorem Probe.Proofs.goal : True := trivial\n"


def _write_toml_project(root: Path, proofs: str) -> None:
    (root / "Probe").mkdir(parents=True)
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.35.0\n", encoding="utf-8")
    (root / "lakefile.toml").write_text(
        'name = "probe"\nversion = "0.1.0"\n'
        'defaultTargets = ["Probe", "Probe.Proofs"]\n\n'
        '[[lean_lib]]\nname = "Probe"\n\n[[lean_lib]]\nname = "Probe.Proofs"\n',
        encoding="utf-8",
    )
    (root / "Probe.lean").write_text("theorem probeRoot : True := trivial\n", encoding="utf-8")
    (root / "Probe" / "Proofs.lean").write_text(proofs, encoding="utf-8")
    (root / "comparator.json").write_text(
        '{"challenge_module":"Probe","solution_module":"Probe.Proofs",'
        '"theorem_names":["Probe.Proofs.goal"],'
        '"permitted_axioms":["propext","Quot.sound","Classical.choice"]}\n',
        encoding="utf-8",
    )


def test_planted_lakefile_is_not_elaborated(tmp_path: Path) -> None:
    """Lake prefers lakefile.lean. Leaving it in place elaborates the hidden #eval."""
    _skip_without_confinement()
    _skip_without_soko()
    root = tmp_path / "proj"
    _write_toml_project(root, _ORIGINAL_PROOFS)
    marker = root / "plant-marker.txt"
    (root / "lakefile.lean").write_text(
        "def s := r##\"foo\"#\n"
        "#eval do\n"
        f"  IO.FS.writeFile {json.dumps(str(marker))} \"ELABORATED\"\n"
        f"  IO.FS.writeFile {json.dumps(str(root / 'Probe' / 'Proofs.lean'))} \"ELABORATED\\n\"\n",
        encoding="utf-8",
    )
    verify_lean4_project_comparator(root, allow_unsandboxed=False)
    expect_false(marker.is_file(), "the planted lakefile was elaborated")
    expect_false((root / "lakefile.lean").exists(), "the planted lakefile was kept")
    expect_true(
        (root / "Probe" / "Proofs.lean").read_text(encoding="utf-8") == _ORIGINAL_PROOFS,
        (root / "Probe" / "Proofs.lean").read_text(encoding="utf-8"),
    )


def test_comparator_cannot_see_the_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A host `lake comparator` re-elaborates a cold lakefile and this report shows the host."""
    _skip_without_confinement()
    _skip_without_soko()
    monkeypatch.setenv("MCPROOF_SANDBOX_SENTINEL", "leakme-parent-env")
    root = tmp_path / "proj"
    (root / "Probe").mkdir(parents=True)
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.35.0\n", encoding="utf-8")
    (root / "Probe.lean").write_text("theorem probeRoot : True := trivial\n", encoding="utf-8")
    (root / "Probe" / "Proofs.lean").write_text(_ORIGINAL_PROOFS, encoding="utf-8")
    (root / "comparator.json").write_text(
        '{"challenge_module":"Probe","solution_module":"Probe.Proofs",'
        '"theorem_names":["Probe.Proofs.goal"],'
        '"permitted_axioms":["propext","Quot.sound","Classical.choice"]}\n',
        encoding="utf-8",
    )
    hits: list[bytes] = []
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(0.2)
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _addr = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                hits.append(conn.recv(64))
            finally:
                conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    (root / "probe.py").write_text(
        "import os, socket\n"
        "from pathlib import Path\n"
        "phase = Path('probe-phase.txt')\n"
        "tag = 'comparator' if phase.is_file() else 'build'\n"
        "if not phase.is_file():\n"
        "    phase.write_text('done\\n')\n"
        "git = Path('/agent/repos/mcproof/.git/config')\n"
        "sock = '0'\n"
        "try:\n"
        "    h = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "    h.settimeout(0.3)\n"
        "    h.connect('/run/host-services/ssh-auth.sock')\n"
        "    sock = '1'\n"
        "    h.close()\n"
        "except OSError:\n"
        "    pass\n"
        "tcp = '0'\n"
        "try:\n"
        f"    c = socket.create_connection(('127.0.0.1', {port}), 0.3)\n"
        "    c.sendall(b'NET_OK')\n"
        "    c.close()\n"
        "    tcp = '1'\n"
        "except OSError:\n"
        "    pass\n"
        "env = os.environ.get('MCPROOF_SANDBOX_SENTINEL', '')\n"
        "proc = Path('/proc/1/environ').read_bytes().decode('utf-8', 'replace') if Path('/proc/1/environ').is_file() else ''\n"
        "sent = '1' if ('leakme-parent-env' in env or 'leakme-parent-env' in proc) else '0'\n"
        "lake = Path('.lake')\n"
        "lake.mkdir(exist_ok=True)\n"
        "(lake / 'probe-report.txt').write_text(f'{tag} GIT={1 if git.is_file() else 0} SOCK={sock} TCP={tcp} SENTINEL={sent}\\n')\n"
        "proofs = Path('Probe/Proofs.lean')\n"
        "if tag == 'build':\n"
        "    proofs.write_text(proofs.read_text() + '-- rewritten-by-probe\\n')\n"
        "else:\n"
        "    try:\n"
        "        proofs.write_text('ELABORATED\\n')\n"
        "    except OSError:\n"
        "        pass\n",
        encoding="utf-8",
    )
    (root / "lakefile.lean").write_text(
        "import Lake\nopen Lake DSL\n\n"
        "run_cmd IO.Process.output { cmd := \"python3\", args := #[\"probe.py\"] }\n\n"
        "package «probe»\n\n@[default_target]\nlean_lib «Probe»\nlean_lib «Probe.Proofs»\n",
        encoding="utf-8",
    )
    try:
        verify_lean4_project_comparator(root, allow_unsandboxed=False)
        report_path = root / ".lake" / "probe-report.txt"
        report = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
        expect_true(report.startswith("comparator "), report)
        expect_true("GIT=0" in report and "SOCK=0" in report and "TCP=0" in report, report)
        expect_true("SENTINEL=0" in report and "leakme-parent-env" not in report, report)
        expect_true(hits == [], hits)
        expect_true(
            (root / "Probe" / "Proofs.lean").read_text(encoding="utf-8") == _ORIGINAL_PROOFS,
            (root / "Probe" / "Proofs.lean").read_text(encoding="utf-8"),
        )
    finally:
        stop.set()
        server.close()
        thread.join(timeout=2)


def test_eval_or_run_meta_never_runs_the_comparator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Removing the early return reaches `lake comparator` and this fails."""
    _skip_without_soko()
    if not has_lean_toolchain():
        pytest.skip("Lean is absent, so the comparator stop was not exercised")

    import mcproof.lean_harness as harness

    real_run = harness.subprocess.run
    real_confined = harness.run_confined_command

    def reject_run(argv, *args, **kwargs):
        if any(str(part) == "comparator" for part in argv):
            raise AssertionError(f"comparator ran: {argv}")
        return real_run(argv, *args, **kwargs)

    def reject_confined(argv, *args, **kwargs):
        if any(str(part) == "comparator" for part in argv):
            raise AssertionError(f"comparator ran: {argv}")
        return real_confined(argv, *args, **kwargs)

    monkeypatch.setattr(harness, "run_confined_command", reject_confined)
    monkeypatch.setattr(harness.subprocess, "run", reject_run)
    samples = (
        _ORIGINAL_PROOFS + "#eval IO.println \"hi\"\n",
        "import Lean\n" + _ORIGINAL_PROOFS + "run_meta do pure ()\n",
    )
    for proofs in samples:
        root = tmp_path / uuid.uuid4().hex
        _write_toml_project(root, proofs)
        res = verify_lean4_project_comparator(root, allow_unsandboxed=False)
        rules = {f["rule"] for f in res.findings}
        expect_true(
            "FORBIDDEN_EVAL_COMMAND" in rules or any("run_meta" in str(f.get("message", "")) for f in res.findings),
            res.findings,
        )


def test_confined_compile_error_reports_sandboxed() -> None:
    """The compile ran inside the sandbox. Reporting sandboxed=False makes this fail."""
    _skip_without_confinement()
    _skip_without_soko()
    res = verify_lean4_source(
        'theorem t (n : Nat) : n = n := rfl\ndef s := r##"foo"#\n',
    )
    expect_in("LEAN_COMPILE_ERROR", {f["rule"] for f in res.findings})
    expect_true(res.sandboxed is True, res)
