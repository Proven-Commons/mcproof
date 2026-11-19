# mcproof-stack

`mcproof-stack` is the live four-layer integration and multi-adapter composition harness for the [Formal Verification MDE blueprint](https://github.com/siliconcordat/mde/issues/4). It mounts deterministic domain adapters onto `llama-server` behind `mde`, `exo`, and `warp-modeld`, and checks interference, drift, and constant-time rollback. It is built for maintainers and verifiers auditing open-weights formal proof tooling on local hardware.

## Layout

- `src/mcproof_stack/runtime.py`: Discovers local binaries, manages `llama-server` `0.5.0` processes with zero-scale startup and slot isolation, and loads or compiles `weft` adapters.
- `src/mcproof_stack/phase4_mount.py`: Runs Phase 4 (`mde` span tagging and code audit, `exo` zone routing, `warp-modeld` Stages 1 to 4, Plane 1 byte-drift unload, `zone-manifest` rotation unload, and logprob rollback checks).
- `src/mcproof_stack/phase6_composition.py`: Runs Phase 6 (`formal-verification`, `corpus`, and the [weft-eido contrast audit pack](https://github.com/Moissanite-Labs/weft-eido/pull/25) across all seven hazards and gates `T-C1` to `T-C5`).
- `src/mcproof_stack/cli.py`: Command-line runner writing JSON receipts under `results/`.
- `configs/synthetic_host_canaries_16.json`: Sixteen synthetic host-owned smoke canaries (`0600` permissions, zero private holdout overlap).
- `worktrees/`: Isolated local feature branches for `exo`, `warp`, and `weft-eido` leaving sibling working trees untouched.

## Commands

Run unit and pokayoke checks offline:

```bash
$MDE_BIN guard --code-audit src tests configs
PYTHONPATH=src python3 -O -B -W error -m unittest discover -s tests -v
```

Run live Phase 4 and Phase 6 against `llama-server`:

```bash
PYTHONPATH=src python3 -O -B -W error -m mcproof_stack.cli all --output-dir results/live
```

Run sealed holdout and canary verification (for the independent verifier):

```bash
PYTHONPATH=src python3 -O -B -W error -m mcproof_stack.cli all \
  --compiler-manifest path/to/MANIFEST.json \
  --canary-jsonl path/to/warp_canaries_16.json \
  --phase6-canary-jsonl path/to/warp_canaries_multidomain.json \
  --mixed-jsonl path/to/mixed_composition_30.jsonl \
  --mixed-grader-cmd "python3 -O -B -W error path/to/grade_mixed.py --responses {responses_jsonl} --workers 8" \
  --retention-jsonl path/to/general_retention_100.jsonl \
  --retention-grader-cmd "python3 -O -B -W error path/to/grade_retention.py --baseline-responses {baseline_jsonl} --candidate-responses {candidate_jsonl} --max-drop-pp 1.5" \
  --formal-eval-jsonl path/to/private_holdout.jsonl \
  --holdout-grader-cmd "python3 -O -B -W error path/to/grade_holdout.py --responses {responses_jsonl} --workers 8" \
  --output-dir path/to/verification/stack_receipts
```

Pass `--canary-cmd "python3 -O -B -W error path/to/grade_canaries.py --opaque-stage3 --server-url {server_url} --lora-json {lora_json}"` when running zero-plaintext opaque Stage 3 canary checks.
