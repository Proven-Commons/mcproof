"""mcproof: Deterministic Tier 2 formal verification oracle harness and Plane 1 spec bundle."""

from __future__ import annotations

from .lean_harness import (
    LeanVerificationResult,
    audit_weak_statements,
    lint_lean4_source,
    verify_lean4_project_comparator,
    verify_lean4_source,
)
from .lineage import (
    CANONICAL_ZONE_MANIFEST_ID,
    LineageVerificationReport,
    StaleLineageError,
    build_lineage_manifest,
    find_forbidden_control_bytes,
    verify_lineage_manifest,
)
from .mutation import (
    KILL_FLOOR_DEN,
    KILL_FLOOR_NUM,
    MutationKillReport,
    run_checker_mutation_suite,
    run_f0_gate_and_corruptions,
    run_python_strict,
)
from .oracles import (
    OracleReceipt,
    grade_family_completion,
    run_all_reference_selftests,
    run_checker_oracle,
    run_claim_hygiene_oracle,
    run_f0_gate_oracle,
    run_lean4_oracle,
    run_mde_code_audit,
    run_mde_integrity,
    run_mission_bar_oracle,
    run_prose_and_mixed_zone_oracle,
    run_soko_integrity_and_evidence_oracle,
    run_verdicts_oracle,
)

__version__ = "0.1.0"

__all__ = [
    "CANONICAL_ZONE_MANIFEST_ID",
    "KILL_FLOOR_DEN",
    "KILL_FLOOR_NUM",
    "LeanVerificationResult",
    "LineageVerificationReport",
    "MutationKillReport",
    "OracleReceipt",
    "StaleLineageError",
    "__version__",
    "audit_weak_statements",
    "build_lineage_manifest",
    "find_forbidden_control_bytes",
    "grade_family_completion",
    "lint_lean4_source",
    "run_all_reference_selftests",
    "run_checker_oracle",
    "run_claim_hygiene_oracle",
    "run_f0_gate_and_corruptions",
    "run_f0_gate_oracle",
    "run_lean4_oracle",
    "run_mde_code_audit",
    "run_mde_integrity",
    "run_mission_bar_oracle",
    "run_prose_and_mixed_zone_oracle",
    "run_python_strict",
    "run_soko_integrity_and_evidence_oracle",
    "run_verdicts_oracle",
    "verify_lean4_project_comparator",
    "verify_lean4_source",
    "verify_lineage_manifest",
]
