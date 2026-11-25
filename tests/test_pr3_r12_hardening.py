#!/usr/bin/env python3
"""Fail-closed R12 security & provenance regression suite for mcproof PR #3.

Covers all confirmed P0-1..P0-6 defects, X-1..X-5 blind spots, and T1..T9
fail-closed kill assertions with zero bare `assert` statements and pure stdlib
`unittest` compatibility across `-I -B`, `-I -O -B`, `-I -B -W error`, and pytest.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mcproof import domain_protocol, lean_harness, lineage, repair_loop  # noqa: E402


def _clean_soko_mod() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        audit_lean4_source=lambda src, label="<lean>", strict_init_only=True: {
            "label": label,
            "ok": True,
            "finding_count": 0,
            "findings": [],
        }
    )


class CanonicalJsonAndLineageTest(unittest.TestCase):
    """T1 & T2: Unified canonical JSON encoder and strict allow_nan=False parity."""

    def test_t1_canonical_json_and_zone_manifest_parity(self) -> None:
        payload = {"s": "é", "a": 1, "z": [True, "α"]}
        raw = lineage.canonical_json_bytes(payload)
        self.assertIn(b"\\u00e9", raw)
        expected_id = "sha256:" + hashlib.sha256(raw).hexdigest()
        with_id = dict(payload, manifest_id="sha256:" + "0" * 64)
        self.assertEqual(lineage.compute_zone_manifest_id(with_id), expected_id)

        # Existing repo zone-manifest.v0.1.json digest remains unchanged.
        zone_path = REPO_ROOT / "schemas" / "zone-manifest.v0.1.json"
        zone_obj = json.loads(zone_path.read_text(encoding="utf-8"))
        self.assertEqual(lineage.compute_zone_manifest_id(zone_obj), lineage.CANONICAL_ZONE_MANIFEST_ID)

    def test_t2_allow_nan_false_and_canonical_rederivation_in_lineage_and_repair_loop(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    lineage.canonical_json_bytes({"x": bad})
                with self.assertRaises(ValueError):
                    lineage.compute_zone_manifest_id({"x": bad})

        # repair_loop.compute_failure_signature is canonical and order-independent.
        sig_a = repair_loop.compute_failure_signature([
            {"rule": "RULE_B", "line": 9},
            {"rule": "RULE_A", "line": 2},
        ])
        sig_b = repair_loop.compute_failure_signature([
            {"rule": "RULE_A", "line": 2},
            {"rule": "RULE_B", "line": 9},
        ])
        self.assertEqual(sig_a, sig_b)
        expected_sig = hashlib.sha256(
            lineage.canonical_json_bytes([["RULE_A", 2], ["RULE_B", 9]])
        ).hexdigest()[:24]
        self.assertEqual(sig_a, expected_sig)

        # repair_loop HTTP payload rejects NaN via canonical_json_bytes.
        gen = repair_loop.make_llama_server_generator(
            server_url="http://127.0.0.1:1",
            lora=[{"id": 0, "scale": float("nan")}],
        )

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self):
                return b"{}"

        seen_urls: list[str] = []

        def _fake_urlopen(req, timeout=300.0):
            seen_urls.append(req.full_url)
            return _FakeResp()

        with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            with self.assertRaises(ValueError):
                gen("prompt", 1)
        # Slot-erase POST ({}) succeeded, while the completion POST containing NaN aborted before urlopen.
        self.assertEqual(len(seen_urls), 1)
        self.assertIn("action=erase", seen_urls[0])

        # repair_loop JSONL checkpoint lines match canonical_json_bytes(res) + b"\n" byte-for-byte.
        with tempfile.TemporaryDirectory(prefix="mcproof_t2_") as td:
            ckpt = Path(td) / "ckpt.jsonl"
            sample_res = {
                "id": "X-1",
                "family": "A",
                "pass_at_1": True,
                "label": "é",
                "turns_used": 1,
                "oracle_calls": 1,
                "total_prompt_tokens": 10,
                "total_completion_tokens": 5,
                "total_tokens": 15,
                "total_retrieved_plane1_tokens": 8,
            }
            with mock.patch.object(repair_loop, "run_repair_item", return_value=sample_res):
                repair_loop.run_repair_split(
                    [{"id": "X-1", "family": "A"}],
                    lambda _p, _t: {"text": ""},
                    max_turns=1,
                    checkpoint_jsonl=ckpt,
                )
            self.assertEqual(ckpt.read_bytes(), lineage.canonical_json_bytes(sample_res) + b"\n")

            bad_ckpt = Path(td) / "bad_ckpt.jsonl"
            bad_res = {"id": "X-2", "family": "A", "pass_at_1": False, "score": math.nan}
            with mock.patch.object(repair_loop, "run_repair_item", return_value=bad_res):
                with self.assertRaises(ValueError):
                    repair_loop.run_repair_split(
                        [{"id": "X-2", "family": "A"}],
                        lambda _p, _t: {"text": ""},
                        max_turns=1,
                        checkpoint_jsonl=bad_ckpt,
                    )


class LeanBarRulesAndSokoTest(unittest.TestCase):
    """T3 & T5: R12 Lean static rules, compile blocking, comparator blocking, and soko fail-closed."""

    def test_t3_r12_bar_forbidden_rules_and_positive_controls(self) -> None:
        cases = [
            ("theorem t (n : Nat) : n = n := by\n  dbg_trace \"hi\"\n  rfl\n", "FORBIDDEN_DBG"),
            ("def f (n : Nat) : Nat := dbgTraceVal n\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_DBG"),
            ("def f : Unit := dbgSleep 1 (fun _ => ())\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_DBG"),
            ("def f : Unit := dbgStackTrace (fun _ => ())\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_DBG"),
            ("@[export evil_sym]\ndef f (n : Nat) : Nat := n\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_EXPORT_ATTR"),
            ("attribute [export evil_sym] f\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_EXPORT_ATTR"),
            ("@[init]\ndef evilInit : IO Unit := pure ()\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_INIT_ATTRIBUTE"),
            ("@[builtin_init]\ndef evilInit : IO Unit := pure ()\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_INIT_ATTRIBUTE"),
            ("attribute [builtin_init] evilInit\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_INIT_ATTRIBUTE"),
            ("#guard_msgs in\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_EVAL_COMMAND"),
            ("#guard 1 + 1 == 2\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_EVAL_COMMAND"),
            ("def f (n : Nat) : Nat := panic! \"boom\"\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_PANIC"),
            ("def f (n : Nat) : Nat := panicWithDef \"boom\"\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_PANIC"),
            ("def f (n : Nat) : Nat := unreachable!\ntheorem t (n : Nat) : n = n := rfl\n", "FORBIDDEN_PANIC"),
        ]
        with mock.patch.object(lean_harness, "_load_soko_lean4_auditor", return_value=_clean_soko_mod()):
            for src, expected_rule in cases:
                with self.subTest(rule=expected_rule, snippet=src.splitlines()[0]):
                    rep = lean_harness.lint_lean4_source(src, check_vacuous=False, require_theorem=False)
                    self.assertFalse(rep["passed"])
                    rules = {f["rule"] for f in rep["findings"]}
                    self.assertIn(expected_rule, rules)

            # Positive controls must not trigger false positives.
            clean_controls = [
                "export Nat (succ)\ntheorem t (n : Nat) : n + 0 = n := Nat.add_zero n\n",
                "theorem init_eq (n : Nat) : n = n := rfl\nattribute [simp] init_eq\n",
            ]
            for src in clean_controls:
                with self.subTest(control=src.splitlines()[0]):
                    rep = lean_harness.lint_lean4_source(src, check_vacuous=False, require_theorem=True)
                    self.assertTrue(rep["passed"], f"false positive on clean control: {rep['findings']}")

        for rule in (
            "FORBIDDEN_INIT_ATTRIBUTE",
            "FORBIDDEN_EXPORT_ATTR",
            "FORBIDDEN_DBG",
            "FORBIDDEN_PANIC",
            "FORBIDDEN_EVAL_COMMAND",
        ):
            self.assertIn(rule, lean_harness.COMPILE_BLOCKING_LINT_RULES)

        self.assertTrue(
            lean_harness.finding_blocks_comparator({"rule": "FORBIDDEN_EVAL_COMMAND", "message": "#guard_msgs"})
        )
        self.assertTrue(
            lean_harness.finding_blocks_comparator({"rule": "METAPROGRAM_ESCAPE", "message": "matched '#guard_msgs'"})
        )
        self.assertIn("#guard_msgs", lean_harness._lean_commands_that_may_run("#guard_msgs in\ntheorem t : True := trivial\n"))

        # Char-literal double-quote (`'"'`), raw-string, and guillemet (`«"»`) lexer bypasses:
        # Both strip_lean_comments_and_strings(blank_chars=True) and the soko handoff must keep
        # code between two `'"'` literals visible so soko-only rules (`import Mathlib`, `ring`,
        # `: Float`) and BAR rules (`sorry`, `#eval`, `@[export]`) cannot be swallowed.
        char_dquote_cases = [
            (
                "char_dquote_sorry",
                "def c : Char := '\"'\ntheorem t : (1 : Nat) = 2 := sorry\ndef d : Char := '\"'\n",
                "sorry",
            ),
            (
                "char_dquote_mathlib",
                "def c : Char := '\"'\nimport Mathlib\ntheorem t (n : Nat) : n = n := rfl\ndef d : Char := '\"'\n",
                "import Mathlib",
            ),
            (
                "char_dquote_ring",
                "def c : Char := '\"'\ntheorem t (n : Nat) : n + 0 = n := by ring\ndef d : Char := '\"'\n",
                "ring",
            ),
            (
                "char_dquote_float",
                "def c : Char := '\"'\ndef bad (x : Float) : Nat := 0\ntheorem t (n : Nat) : n = n := rfl\ndef d : Char := '\"'\n",
                "Float",
            ),
            (
                "char_escapes_and_dquote",
                "def a : Char := '\\''\ndef b : Char := '\\\\'\ndef c : Char := '\\\"'\n"
                "def q : Char := '\"'\n@[export evil] def f : Nat := 1\ndef r : Char := '\"'\n",
                "@[export evil]",
            ),
            (
                "raw_string_and_guillemet_dquote",
                "def s := r#\"\\\"#\ndef «\"» : Nat := 1\nimport Mathlib\ndef «\"2» : Nat := 2\n",
                "import Mathlib",
            ),
        ]
        for label, src, needle in char_dquote_cases:
            with self.subTest(char_lexer_case=label):
                soko_sanitized = lean_harness.strip_lean_comments_and_strings(src, blank_chars=True)
                self.assertIn(needle, soko_sanitized)
                self.assertEqual(soko_sanitized.count('"') % 2, 0, f"odd quote count in {soko_sanitized!r}")
                # Verify lint_lean4_source passes the sanitized text (with balanced quotes) to soko.
                captured: list[str] = []

                def _capture_soko(passed_src: str, label: str = "<lean>", strict_init_only: bool = True):
                    captured.append(passed_src)
                    return {"label": label, "ok": True, "finding_count": 0, "findings": []}

                fake_soko = types.SimpleNamespace(audit_lean4_source=_capture_soko)
                with mock.patch.object(lean_harness, "_load_soko_lean4_auditor", return_value=fake_soko):
                    lean_harness.lint_lean4_source(src, label=f"<{label}>", check_vacuous=False)
                self.assertEqual(len(captured), 1)
                self.assertIn(needle, captured[0])
                self.assertEqual(captured[0].count('"') % 2, 0, f"unbalanced quotes passed to soko: {captured[0]!r}")

    def test_t5_soko_auditor_fail_closed_and_exec_module_cleanup(self) -> None:
        src = "theorem t (n : Nat) : n = n := rfl\n"
        bad_reports = [
            {"ok": False, "finding_count": 0, "findings": []},
            {"passed": False, "findings": []},
            {"findings": {}},
            {"ok": True, "finding_count": 1, "findings": []},
            {"passed": True, "findings": [{"code": "UNPROVED_SORRY", "line": 1, "detail": "sorry"}]},
            {"passed": "yes", "findings": []},
            {"ok": False, "findings": ["not-a-dict"]},
            "not-a-mapping",
        ]
        for bad in bad_reports:
            with self.subTest(soko_rep=bad):
                fake_mod = types.SimpleNamespace(audit_lean4_source=lambda *_a, **_k: bad)
                with mock.patch.object(lean_harness, "_load_soko_lean4_auditor", return_value=fake_mod):
                    with self.assertRaises(RuntimeError):
                        lean_harness.lint_lean4_source(src, check_vacuous=False)

        with mock.patch.object(lean_harness, "_load_soko_lean4_auditor", return_value=_clean_soko_mod()):
            ok_rep = lean_harness.lint_lean4_source(src, check_vacuous=False)
            self.assertTrue(ok_rep["passed"])

        # exec_module failure must clean up sys.modules and raise RuntimeError.
        with tempfile.TemporaryDirectory(prefix="mcproof_soko_err_") as td:
            bad_soko = Path(td) / "soko_mcp"
            bad_soko.mkdir()
            (bad_soko / "lean4_auditor.py").write_text("raise ZeroDivisionError('boom')\n", encoding="utf-8")
            with mock.patch.object(lean_harness, "dep_repo", return_value=Path(td)):
                with self.assertRaises(RuntimeError):
                    lean_harness._load_soko_lean4_auditor()
            self.assertNotIn("soko_lean4_auditor", sys.modules)


class EnvScrubAndConfinementTest(unittest.TestCase):
    """T4, T6, T7, T9: Env scrubbing, short-name hijack removal, elab_rules confinement, and symlinks."""

    def test_t4_sandbox_env_and_lean_env_block_caller_pollution(self) -> None:
        pairs = lean_harness._sandbox_env_pairs({
            "LEAN_PATH": "/evil/olean",
            "ELAN_TOOLCHAIN": "evil-toolchain",
            "ELAN_HOME": "/evil/elan",
            "LD_PRELOAD": "/evil/lib.so",
        })
        env_map = dict(pairs)
        self.assertNotIn("LEAN_PATH", env_map)
        self.assertNotIn("ELAN_TOOLCHAIN", env_map)
        self.assertNotIn("LD_PRELOAD", env_map)
        expected_elan = lean_harness._toolchain_elan_home()
        if expected_elan:
            self.assertEqual(env_map.get("ELAN_HOME"), expected_elan)

        harness_pairs = lean_harness._sandbox_env_pairs(
            {"LEAN_PATH": "/evil/olean"},
            harness_lean_path="/trusted/mod:/trusted/lib",
        )
        self.assertEqual(dict(harness_pairs).get("LEAN_PATH"), "/trusted/mod:/trusted/lib")

        with tempfile.TemporaryDirectory(prefix="mcproof_elan_") as td:
            fake_elan = Path(td)
            (fake_elan / "bin").mkdir()
            polluted = {
                "PATH": "/usr/bin:/bin",
                "ELAN_HOME": str(fake_elan),
                "ELAN_TOOLCHAIN": "evil-tc",
                "LEAN_PATH": "/evil/olean",
                "LEAN_OPTS": "--evil",
                "LEAN_SRC_PATH": "/evil/src",
                "LEAN_SYSROOT": "/evil/sysroot",
                "LEAN_CC": "/evil/cc",
                "LAKE_HOME": "/evil/lake",
                "LAKE_PKG_PATH": "/evil/pkg",
                "LD_PRELOAD": "/evil/preload.so",
                "LD_LIBRARY_PATH": "/evil/lib",
            }
            with mock.patch.dict(os.environ, polluted, clear=True):
                cleaned = lean_harness._lean_env()
            for var in lean_harness._LEAN_SCRUB_VARS:
                self.assertNotIn(var, cleaned, f"{var} leaked into _lean_env()")
            self.assertTrue(cleaned["PATH"].startswith(str((fake_elan / "bin").resolve())))

        # linux_bwrap_functional must not leak MCPROOF_SANDBOX_SENTINEL into parent os.environ
        # and must require the probe stdout marker "MCPROOF_PROBE_OK".
        saved_cache = lean_harness._BWRAP_FUNCTIONAL
        try:
            lean_harness._BWRAP_FUNCTIONAL = None
            captured_host_env: list[dict[str, str] | None] = []

            def _fake_spawn(*_a, **kw):
                captured_host_env.append(kw.get("host_env"))
                self.assertNotIn("MCPROOF_SANDBOX_SENTINEL", os.environ)
                return subprocess.CompletedProcess(args=["probe"], returncode=0, stdout="", stderr="")

            with mock.patch.object(lean_harness, "_spawn_confined", side_effect=_fake_spawn), \
                 mock.patch("shutil.which", return_value="/usr/bin/tool"), \
                 mock.patch.object(sys, "platform", "linux"):
                # Empty stdout (missing MCPROOF_PROBE_OK) must fail closed to False.
                self.assertFalse(lean_harness.linux_bwrap_functional())
                self.assertTrue(captured_host_env and captured_host_env[0] is not None)
                self.assertIn("MCPROOF_SANDBOX_SENTINEL", captured_host_env[0])

            lean_harness._BWRAP_FUNCTIONAL = None
            with mock.patch.object(
                lean_harness,
                "_spawn_confined",
                return_value=subprocess.CompletedProcess(args=["probe"], returncode=0, stdout="MCPROOF_PROBE_OK\n", stderr=""),
            ), mock.patch("shutil.which", return_value="/usr/bin/tool"), mock.patch.object(sys, "platform", "linux"):
                self.assertTrue(lean_harness.linux_bwrap_functional())
        finally:
            lean_harness._BWRAP_FUNCTIONAL = saved_cache

    def test_t6_pspec_driver_disallows_short_name_hijack_fallback(self) -> None:
        prompt = "Prove `theorem Foo.target (n : Nat) : n + 0 = n := by sorry`."
        candidate = (
            "namespace Foo\n"
            "end Foo\n"
            "private theorem target : True := trivial\n"
        )
        captured_drivers: list[str] = []

        def _fake_confined(cmd, *, cwd, env=None, timeout_sec=60, readable_dirs=(), harness_lean_path=None):
            if str(cmd[-1]).endswith("McproofPromptSpecDriver.lean"):
                drv_text = Path(cmd[-1]).read_text(encoding="utf-8")
                captured_drivers.append(drv_text)
                return subprocess.CompletedProcess(
                    args=list(cmd),
                    returncode=0,
                    stdout="MCPROOF_PSPEC_ERR\tMISSING_PROMPT_THEOREM_NAME\ttarget\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(args=list(cmd), returncode=0, stdout="", stderr="")

        with mock.patch.object(lean_harness, "_load_soko_lean4_auditor", return_value=_clean_soko_mod()), \
             mock.patch.object(lean_harness, "find_lean_tool", return_value="/usr/bin/lean"), \
             mock.patch.object(lean_harness, "_lean_env", return_value={"PATH": "/usr/bin"}), \
             mock.patch("subprocess.run", return_value=subprocess.CompletedProcess(args=["lean"], returncode=0, stdout="/lib\n", stderr="")), \
             mock.patch.object(lean_harness, "run_confined_command", side_effect=_fake_confined):
            findings = lean_harness.verify_lean4_prompt_obligations(
                prompt,
                candidate,
                run_kernel_type_check=True,
                lean_project_dir=REPO_ROOT / "lean",
            )
        self.assertEqual(len(captured_drivers), 1)
        self.assertNotIn("env.find? shortN", captured_drivers[0])
        self.assertIn("env.find? fullN", captured_drivers[0])
        self.assertIn("MISSING_PROMPT_THEOREM_NAME", {f["rule"] for f in findings})

    def test_t7_elab_rules_confined_across_all_six_comparator_kernels(self) -> None:
        self.assertFalse(
            lean_harness.finding_blocks_comparator({"rule": "METAPROGRAM_ESCAPE", "message": "matched 'elab_rules'"})
        )
        with tempfile.TemporaryDirectory(prefix="mcproof_t7_") as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "lean-toolchain").write_text("leanprover/lean4:v4.35.0\n", encoding="utf-8")
            (proj / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")
            (proj / "comparator.json").write_text(
                json.dumps({
                    "challenge_module": "Demo.Spec",
                    "solution_module": "Demo.Proofs",
                    "theorem_names": ["Demo.Spec.t"],
                    "permitted_axioms": ["propext", "Classical.choice", "Quot.sound"],
                }),
                encoding="utf-8",
            )
            (proj / "Demo").mkdir()
            (proj / "Demo" / "Spec.lean").write_text("theorem Demo.Spec.t (n : Nat) : n = n := sorry\n", encoding="utf-8")
            (proj / "Demo" / "Proofs.lean").write_text(
                "elab_rules : term | `(0) => pure (.const ``Nat.zero [])\n"
                "theorem Demo.Spec.t (n : Nat) : n = n := rfl\n",
                encoding="utf-8",
            )

            kernel_lines = ["Exporting #[Demo.Spec.t] from Demo.Proofs"]
            for _k, run_line, acc_line in lean_harness.COMPARATOR_ORDERED_KERNELS:
                kernel_lines.append(run_line)
                kernel_lines.append(acc_line)
            kernel_lines.append("Your solution is okay!")
            comp_stdout = "\n".join(kernel_lines) + "\n"

            confined_invocations: list[list[str]] = []
            orig_confine = lean_harness._confine_argv

            def _spy_confine(cmd, **kw):
                argv = orig_confine(cmd, **kw)
                confined_invocations.append(argv)
                return argv

            def _fake_subproc_run(argv, **_kw):
                if "comparator" in argv:
                    return subprocess.CompletedProcess(args=argv, returncode=0, stdout=comp_stdout, stderr="")
                return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

            with mock.patch.object(lean_harness, "_load_soko_lean4_auditor", return_value=_clean_soko_mod()), \
                 mock.patch.object(lean_harness, "linux_bwrap_functional", return_value=True), \
                 mock.patch.object(lean_harness, "find_lean_tool", side_effect=lambda n: f"/usr/bin/{n}"), \
                 mock.patch.object(lean_harness, "_lean_env", return_value={"PATH": "/usr/bin"}), \
                 mock.patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}"), \
                 mock.patch.object(lean_harness, "_confine_argv", side_effect=_spy_confine), \
                 mock.patch("subprocess.run", side_effect=_fake_subproc_run):
                res = lean_harness.verify_lean4_project_comparator(proj, allow_unsandboxed=False)

            # All 4 phases (lake build, axiom driver, lake update, lake comparator --paranoid) ran confined.
            self.assertEqual(len(confined_invocations), 4)
            for argv in confined_invocations:
                self.assertIn("--unshare-net", argv)
                self.assertIn("--clearenv", argv)
                self.assertIn("-i", argv)
            self.assertEqual(
                res.paranoid_kernels_run,
                tuple(k for k, _, _ in lean_harness.COMPARATOR_ORDERED_KERNELS),
            )
            self.assertFalse(res.passed)
            self.assertIn("METAPROGRAM_ESCAPE", {f["rule"] for f in res.findings})

    def test_t9_symlink_root_parent_lake_and_toolchain_toctou_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcproof_t9_") as td:
            base = Path(td)
            secret = base / "host_secret.txt"
            secret.write_text("TOP_SECRET_HOST_DATA\n", encoding="utf-8")

            real_proj = base / "real_proj"
            real_proj.mkdir()
            (real_proj / "lean-toolchain").write_text("leanprover/lean4:v4.35.0\n", encoding="utf-8")
            (real_proj / "comparator.json").write_text("{}", encoding="utf-8")

            # 1. Symlinked project root must be rejected without following .resolve().
            sym_root = base / "sym_root"
            sym_root.symlink_to(real_proj, target_is_directory=True)
            res_root = lean_harness.verify_lean4_project_comparator(sym_root)
            self.assertFalse(res_root.passed)
            self.assertIn("UNTRUSTED_PROJECT_SYMLINK", {f["rule"] for f in res_root.findings})
            with self.assertRaises(lean_harness.UntrustedProjectPath):
                lean_harness._checked_project_dir(sym_root)

            # 2. Symlink in parent directory must also be rejected.
            real_parent = base / "real_parent"
            (real_parent / "child_proj").mkdir(parents=True)
            sym_parent = base / "sym_parent"
            sym_parent.symlink_to(real_parent, target_is_directory=True)
            res_parent = lean_harness.verify_lean4_project_comparator(sym_parent / "child_proj")
            self.assertFalse(res_parent.passed)
            self.assertIn("UNTRUSTED_PROJECT_SYMLINK", {f["rule"] for f in res_parent.findings})

            # 3. Symlinked .lake + symlinked lean-toolchain must NOT read host secret.
            lake_proj = base / "lake_proj"
            lake_proj.mkdir()
            (lake_proj / "lean-toolchain").symlink_to(secret)
            (lake_proj / ".lake").symlink_to(real_proj, target_is_directory=True)
            res_lake = lean_harness.verify_lean4_project_comparator(lake_proj)
            self.assertFalse(res_lake.passed)
            self.assertIn("LAKE_CACHE_SYMLINK", {f["rule"] for f in res_lake.findings})
            self.assertNotIn("TOP_SECRET_HOST_DATA", res_lake.toolchain)
            self.assertEqual(lean_harness._read_toolchain_nofollow(lake_proj), "leanprover/lean4:v4.35.0")


class RationalDigitCapTest(unittest.TestCase):
    """T8: Pre-int() rational digit cap and bounded dual_objective output."""

    def test_t8_rational_lp_blocks_oversized_digits_and_caps_dual_objective(self) -> None:
        huge = "9" * 5000
        old_limit = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(0)
        try:
            for bad_tok in (huge, f"{huge}/1", f"1/{huge}", f"-{huge}/7"):
                with self.subTest(tok_len=len(bad_tok)):
                    rep = domain_protocol.verify_rational_lp_certificate({
                        "mode": "bounds",
                        "A": [[1]],
                        "b": [bad_tok],
                        "c": [1],
                        "y": [1],
                        "claimed_lower_bound": 0,
                    })
                    self.assertFalse(rep["passed"])
                    self.assertEqual(rep["epistemic_status"], "REJECTED")
                    self.assertIn("LP_CERT_MALFORMED", {f["rule"] for f in rep["findings"]})
        finally:
            sys.set_int_max_str_digits(old_limit)

        # Construct 10 coprime ~30-digit denominators (each <= 10^60) whose exact sum
        # exceeds MAX_DUAL_OBJECTIVE_BITS (~850 bits) -> must be capped cleanly.
        primes = [
            10**29 + 319,
            10**29 + 363,
            10**29 + 381,
            10**29 + 417,
            10**29 + 441,
            10**29 + 471,
            10**29 + 477,
            10**29 + 523,
            10**29 + 531,
            10**29 + 567,
        ]
        rep_cap = domain_protocol.verify_rational_lp_certificate({
            "mode": "bounds",
            "A": [[1] for _ in primes],
            "b": [f"1/{p}" for p in primes],
            "c": [10],
            "y": [1 for _ in primes],
            "claimed_lower_bound": 0,
        })
        self.assertFalse(rep_cap["passed"])
        self.assertEqual(rep_cap["dual_objective"], "<capped>")
        self.assertIn("LP_DUAL_OBJECTIVE_DIGIT_CAP", {f["rule"] for f in rep_cap["findings"]})


if __name__ == "__main__":
    unittest.main()
