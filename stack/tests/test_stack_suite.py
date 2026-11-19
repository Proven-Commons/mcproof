"""Automated unit and live smoke tests for mcproof_stack Phase 4 and Phase 6."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from mcproof_stack.cli import build_parser
from mcproof_stack.phase4_mount import run_phase4_live_mount, verify_step_4_1_mde_zones_and_code_audit
from mcproof_stack.phase6_composition import run_phase6_composition
from mcproof_stack.runtime import (
    StackPaths,
    build_checkpoint_and_weft_suite,
    compute_mcproof_plane1_tree_sha256,
    sha256_file,
    step0_logprob_shift,
)


class TestMcproofStack(unittest.TestCase):
    def test_step_4_1_mde_zones_and_pokayoke_code_audit(self) -> None:
        paths = StackPaths.discover()
        with tempfile.TemporaryDirectory(prefix="mcproof_test_4_1_") as td:
            res = verify_step_4_1_mde_zones_and_code_audit(paths, Path(td))
            self.assertTrue(res["passed"])
            self.assertTrue(res["manifest_id"].startswith("sha256:"))
            self.assertEqual(res["classified_zones"]["lean_file"], "formal_proof")
            self.assertEqual(res["classified_zones"]["condensed_json"], "condensed_json")
            self.assertEqual(
                set(res["code_audit_negative_caught_rules"]),
                {"bare_assert", "bare_except", "duplicate_json_key", "silent_except_swallow"},
            )

    def test_lineage_pin_alignment_and_finite_step0_shift(self) -> None:
        paths = StackPaths.discover()
        zm_doc = json.loads(paths.zone_manifest_path.read_text(encoding="utf-8"))
        zm_id = str(zm_doc["manifest_id"])
        lineage_file = paths.stack_root.parent / "spec" / "lineage.json"
        if not lineage_file.is_file():
            lineage_file = paths.stack_root.parent / "repo" / "spec" / "lineage.json"
        repo_lineage = json.loads(lineage_file.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="mcproof_test_lin_") as td:
            env = build_checkpoint_and_weft_suite(
                paths,
                work_dir=Path(td),
                base_gguf=paths.default_base_gguf,
                zone_manifest_id=zm_id,
            )
            self.assertEqual(
                env["lineage"].corpus_tree_sha256,
                repo_lineage["source_lineage"]["corpus_tree_sha256"],
            )
            self.assertIn("gg.siliconcordat/mde", env["vendor_mde_meta"])

            p1_file = env["plane1_dir"] / "spec" / "plane1_formal_spec.md"
            p1_file.write_bytes(p1_file.read_bytes() + b"\n")
            mutated_tracked = dict(env["tracked_plane1_hashes"])
            mutated_tracked["spec/plane1_formal_spec.md"] = sha256_file(p1_file)
            mutated_tree = compute_mcproof_plane1_tree_sha256(
                mutated_tracked,
                env["upstream_repos"],
                zm_id,
            )
            self.assertNotEqual(mutated_tree, env["lineage"].corpus_tree_sha256)

        probs_a = [{"id": 10, "logprob": -0.05, "top_logprobs": [{"id": 10, "logprob": -0.05}, {"id": 22, "logprob": -3.2}]}]
        probs_b = [{"id": 22, "logprob": -0.10, "top_logprobs": [{"id": 22, "logprob": -0.10}]}]
        shift = step0_logprob_shift(probs_a, probs_b)
        self.assertTrue(math.isfinite(shift))
        self.assertGreater(shift, 3.0)

    def test_cli_flags_parse(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(
            [
                "all",
                "--compiler-manifest",
                "artifacts/MANIFEST.json",
                "--formal-gguf",
                "artifacts/p2b/formal-verification.p2b.f16.gguf",
                "--canary-jsonl",
                "warp_canaries_16.json",
                "--phase6-canary-jsonl",
                "warp_canaries_multidomain.json",
                "--canary-cmd",
                "python3 grade_canaries.py --server-url {server_url} --lora-json {lora_json}",
                "--mixed-jsonl",
                "mixed_composition_30.jsonl",
                "--mixed-grader-cmd",
                "python3 grade_mixed.py --responses {responses_jsonl}",
                "--retention-jsonl",
                "general_retention_100.jsonl",
                "--retention-grader-cmd",
                "python3 grade_retention.py --baseline-responses {baseline_jsonl} --candidate-responses {candidate_jsonl}",
                "--formal-eval-jsonl",
                "validation.jsonl",
                "--holdout-grader-cmd",
                "python3 grade_holdout.py --responses {responses_jsonl}",
                "--parallel-slots",
                "8",
            ]
        )
        self.assertEqual(ns.subcommand, "all")
        self.assertEqual(ns.phase6_canary_jsonl, "warp_canaries_multidomain.json")
        self.assertEqual(ns.parallel_slots, 8)
        self.assertIn("{responses_jsonl}", ns.mixed_grader_cmd)
        self.assertIn("{baseline_jsonl}", ns.retention_grader_cmd)

    @unittest.skipUnless(
        os.environ.get("MCPROOF_LIVE_LLAMA_TESTS") == "1",
        "Set MCPROOF_LIVE_LLAMA_TESTS=1 to run full live Qwen3.5-4B llama-server Phase 4 & Phase 6 tests",
    )
    def test_live_phase4_and_phase6_end_to_end(self) -> None:
        paths = StackPaths.discover()
        with tempfile.TemporaryDirectory(prefix="mcproof_test_live_") as td:
            out_dir = Path(td) / "results"
            p4 = run_phase4_live_mount(paths, output_dir=out_dir)
            self.assertTrue(p4["passed"])
            self.assertEqual(p4["step_4_4_drift_and_rollback"]["post_kill_switch_max_logprob_diff"], 0.0)

            p6 = run_phase6_composition(paths, output_dir=out_dir)
            self.assertTrue(p6["passed"])
            self.assertEqual(p6["gates"]["T_C2_mixed_zone_isolation"]["formal_block_corruptions"], 0)
            self.assertEqual(p6["gates"]["T_C4_order_invariance_and_rollback"]["full_stack_rollback_max_logprob_diff"], 0.0)


if __name__ == "__main__":
    unittest.main()
