"""CLI entrypoint for Phase 4 live 4-layer mount and Phase 6 multi-MDE composition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Sequence

from .phase4_mount import run_phase4_live_mount
from .phase6_composition import run_phase6_composition
from .runtime import STACK_ROOT, StackPaths, sanitize_receipt_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcproof-stack",
        description="Run live Phase 4 4-layer mount and Phase 6 multi-MDE composition for siliconcordat/mde#4.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    for cmd_name in ("phase4", "phase6", "all"):
        p = sub.add_parser(cmd_name, help=f"Execute {cmd_name} live verification")
        p.add_argument("--base-gguf", default=None, help="Override path to base GGUF model")
        p.add_argument(
            "--compiler-manifest",
            default=None,
            help="Optional MANIFEST.json or composition_manifest.json from @compiler",
        )
        p.add_argument(
            "--formal-gguf",
            default=None,
            help="Optional direct path override to compiled formal-verification GGUF LoRA",
        )
        p.add_argument(
            "--canary-jsonl",
            default=None,
            help="Optional verifier-owned canary file (.json warp_canaries_16.json or .jsonl canaries_16.jsonl)",
        )
        p.add_argument(
            "--canary-cmd",
            default=None,
            help="Optional shell-quoted opaque canary command (supports {server_url} and {lora_json} placeholders)",
        )
        p.add_argument("--ctx-size", type=int, default=8192, help="Per-slot llama-server context size (default: 8192)")
        p.add_argument("--n-gpu-layers", type=int, default=99, help="GPU offload layers (default: 99)")
        p.add_argument(
            "--parallel-slots",
            type=int,
            default=8,
            help="Parallel llama-server slots for <3s Stage 3 canary batching (default: 8)",
        )
        p.add_argument(
            "--output-dir",
            default=str(STACK_ROOT / "results"),
            help="Directory to write JSON verification receipts and response JSONLs",
        )
        if cmd_name in ("phase6", "all"):
            p.add_argument(
                "--phase6-canary-jsonl",
                default=None,
                help="Optional multidomain canary file for Phase 6 paired/triple mounts (e.g. warp_canaries_multidomain.json)",
            )
            p.add_argument("--mixed-jsonl", default=None, help="Optional 30-prompt mixed composition JSONL")
            p.add_argument(
                "--mixed-grader-cmd",
                default=None,
                help="Optional opaque mixed composition grader command (supports {responses_jsonl})",
            )
            p.add_argument("--retention-jsonl", default=None, help="Optional general retention JSONL")
            p.add_argument(
                "--retention-grader-cmd",
                default=None,
                help="Optional opaque retention grader command (supports {responses_jsonl} or {baseline_jsonl}/{candidate_jsonl})",
            )
            p.add_argument("--formal-eval-jsonl", default=None, help="Optional formal evaluation JSONL")
            p.add_argument(
                "--holdout-grader-cmd",
                default=None,
                help="Optional opaque holdout grader command (supports {responses_jsonl})",
            )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = StackPaths.discover(base_gguf_override=args.base_gguf)
    out_dir = Path(args.output_dir).expanduser().resolve()
    canary_cmd_seq = shlex.split(args.canary_cmd) if args.canary_cmd else None
    mixed_grader_seq = shlex.split(args.mixed_grader_cmd) if getattr(args, "mixed_grader_cmd", None) else None
    ret_grader_seq = shlex.split(args.retention_grader_cmd) if getattr(args, "retention_grader_cmd", None) else None
    hold_grader_seq = shlex.split(args.holdout_grader_cmd) if getattr(args, "holdout_grader_cmd", None) else None

    summary: dict[str, object] = {}
    ok = True

    if args.subcommand in ("phase4", "all"):
        p4 = run_phase4_live_mount(
            paths,
            output_dir=out_dir,
            base_gguf_override=args.base_gguf,
            compiler_manifest_path=args.compiler_manifest,
            formal_gguf_override=args.formal_gguf,
            canary_jsonl_path=args.canary_jsonl,
            canary_cmd=canary_cmd_seq,
            ctx_size=args.ctx_size,
            n_gpu_layers=args.n_gpu_layers,
            parallel_slots=args.parallel_slots,
        )
        summary["phase4"] = p4
        ok = ok and bool(p4["passed"])

    if args.subcommand in ("phase6", "all"):
        p6 = run_phase6_composition(
            paths,
            output_dir=out_dir,
            base_gguf_override=args.base_gguf,
            compiler_manifest_path=args.compiler_manifest,
            formal_gguf_override=args.formal_gguf,
            canary_jsonl_path=args.canary_jsonl,
            phase6_canary_jsonl_path=getattr(args, "phase6_canary_jsonl", None),
            canary_cmd=canary_cmd_seq,
            mixed_jsonl_path=getattr(args, "mixed_jsonl", None),
            mixed_grader_cmd=mixed_grader_seq,
            retention_jsonl_path=getattr(args, "retention_jsonl", None),
            retention_grader_cmd=ret_grader_seq,
            formal_eval_jsonl_path=getattr(args, "formal_eval_jsonl", None),
            holdout_grader_cmd=hold_grader_seq,
            ctx_size=args.ctx_size,
            n_gpu_layers=args.n_gpu_layers,
            parallel_slots=args.parallel_slots,
        )
        summary["phase6"] = p6
        ok = ok and bool(p6["passed"])

    if args.subcommand == "all":
        combined = sanitize_receipt_paths(
            {
                "passed": ok,
                "phase4": summary["phase4"],
                "phase6": summary["phase6"],
            }
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "stack_combined_receipt.json").write_text(
            json.dumps(combined, indent=2, sort_keys=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(combined, indent=2, sort_keys=False, allow_nan=False))
    else:
        only_key = "phase4" if args.subcommand == "phase4" else "phase6"
        print(json.dumps(summary[only_key], indent=2, sort_keys=False, allow_nan=False))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
