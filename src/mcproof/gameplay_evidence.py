"""Strict, dependency-free Gameplay Evidence Exchange v0.1 validation.

Validation establishes only envelope structure and digest consistency.  It does
not parse ``source.raw`` or rerun any checker named by the artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_ID = "gameplay-evidence/v0.1"
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
ZERO_SHA256 = "0" * 64

TOP_LEVEL_KEYS = frozenset(
    {"schema", "artifact_sha256", "producer", "claim", "mechanics", "payload", "evidence", "source"}
)
PRODUCER_KEYS = frozenset({"repository", "revision", "adapter"})
CLAIM_KEYS = frozenset({"id", "kind", "statement"})
MECHANIC_KEYS = frozenset({"id", "path", "source_revision", "raw_sha256"})
PAYLOAD_KEYS = frozenset(
    {
        "domain",
        "model",
        "model_sha256",
        "initial_state",
        "initial_state_sha256",
        "actions",
        "actions_sha256",
        "trajectory",
        "trajectory_sha256",
        "outcome",
    }
)
EVIDENCE_KEYS = frozenset({"checks", "negative_controls", "limitations"})
CHECK_KEYS = frozenset(
    {
        "kind",
        "status",
        "checker",
        "source_labels",
        "initial_state_sha256",
        "actions_sha256",
        "trajectory_sha256",
    }
)
CHECKER_KEYS = frozenset({"name", "revision", "artifact_sha256"})
NEGATIVE_CONTROL_KEYS = frozenset({"name", "mutation", "observed", "passed"})
SOURCE_KEYS = frozenset({"media_type", "raw_sha256", "raw"})

SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9_.:-]+")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
CLAIM_KINDS = frozenset({"route", "state_transition", "goal", "counterexample", "observation"})
CHECK_KINDS = frozenset({"model_replay", "model_proof", "live_execution"})
BADGE_ORDER = ("OBSERVED", "REPLAYED", "MODEL_PROVEN", "LIVE_CONFIRMED")


def _validate_canonical_value(value: Any, path: str, active: set[int]) -> None:
    """Reject values whose JSON encoding would be lossy or outside the contract."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise ValueError(f"{path}: integer outside signed 64-bit range")
        return
    if isinstance(value, float):
        raise ValueError(f"{path}: floating-point values are not canonical JSON")
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in active:
            raise ValueError(f"{path}: cyclic value is not JSON")
        active.add(identity)
        try:
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise TypeError(f"{path}: JSON object keys must be strings")
                    _validate_canonical_value(child, f"{path}.{key}", active)
            else:
                for index, child in enumerate(value):
                    _validate_canonical_value(child, f"{path}[{index}]", active)
        finally:
            active.remove(identity)
        return
    raise TypeError(f"{path}: unsupported JSON value type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the contract's canonical UTF-8 JSON representation.

    Object keys must be strings and integers must fit in signed 64 bits. Every
    floating-point value is rejected, including finite integer-valued floats.
    """
    _validate_canonical_value(value, "$", set())
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_json(value: Any) -> str:
    """Hash the canonical JSON bytes of *value* with SHA-256."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {token}")


def load_gameplay_artifact(text: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite numbers.

    This function deliberately does not parse the nested ``source.raw`` string.
    Call :func:`verify_gameplay_artifact` on the returned value before using it.
    """
    if not isinstance(text, str):
        raise TypeError("gameplay artifact input must be text")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
    )


def _error(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _exact_keys(value: Any, expected: frozenset[str], path: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        _error(errors, path, "must be an object")
        return False
    missing = sorted(expected - value.keys())
    unknown = sorted(value.keys() - expected, key=repr)
    if missing:
        _error(errors, path, f"missing keys: {', '.join(missing)}")
    if unknown:
        rendered = ", ".join(key if isinstance(key, str) else repr(key) for key in unknown)
        _error(errors, path, f"unknown keys: {rendered}")
    return not missing and not unknown


def _nonempty_text(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        _error(errors, path, "must be nonempty text")
        return False
    return True


def _identifier(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        _error(errors, path, "must be a nonempty ASCII identifier")
        return False
    return True


def _digest(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _error(errors, path, "must be 64 lowercase hexadecimal characters")
        return False
    if value == ZERO_SHA256:
        _error(errors, path, "all-zero SHA-256 is forbidden")
        return False
    return True


def _commit(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or COMMIT_RE.fullmatch(value) is None:
        _error(errors, path, "must be a 40-character lowercase hexadecimal commit")
        return False
    return True


def _yaml_path(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value:
        _error(errors, path, "must be a nonempty repository-relative YAML path")
        return False
    segments = value.split("/")
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or "\x00" in value
        or any(segment in {"", ".", ".."} for segment in segments)
        or segments[-1].lower().endswith((".yaml", ".yml")) is False
    ):
        _error(errors, path, "must be a nonempty repository-relative YAML path without traversal")
        return False
    return True


def _strict_json_tree(value: Any, path: str, errors: list[str], active: set[int]) -> None:
    """Validate JSON-safe artifact data, rejecting every float and unsafe int."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            _error(errors, path, "integer outside signed 64-bit range")
        return
    if isinstance(value, float):
        _error(errors, path, "floats are forbidden in gameplay artifacts")
        return
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in active:
            _error(errors, path, "cyclic values are forbidden")
            return
        active.add(identity)
        try:
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str):
                        _error(errors, path, "object keys must be strings")
                        continue
                    _strict_json_tree(child, f"{path}.{key}", errors, active)
            else:
                for index, child in enumerate(value):
                    _strict_json_tree(child, f"{path}[{index}]", errors, active)
        finally:
            active.remove(identity)
        return
    _error(errors, path, f"unsupported JSON value type {type(value).__name__}")


def _validate_structure(value: Any, errors: list[str]) -> None:
    if not _exact_keys(value, TOP_LEVEL_KEYS, "$", errors):
        if not isinstance(value, dict):
            return
    _strict_json_tree(value, "$", errors, set())

    if value.get("schema") != SCHEMA_ID:
        _error(errors, "$.schema", f"must be the literal {SCHEMA_ID!r}")
    _digest(value.get("artifact_sha256"), "$.artifact_sha256", errors)

    producer = value.get("producer")
    if _exact_keys(producer, PRODUCER_KEYS, "$.producer", errors):
        repository = producer["repository"]
        if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
            _error(errors, "$.producer.repository", "must have owner/repository form")
        _commit(producer["revision"], "$.producer.revision", errors)
        _nonempty_text(producer["adapter"], "$.producer.adapter", errors)

    claim = value.get("claim")
    if _exact_keys(claim, CLAIM_KEYS, "$.claim", errors):
        _identifier(claim["id"], "$.claim.id", errors)
        if not isinstance(claim["kind"], str) or claim["kind"] not in CLAIM_KINDS:
            _error(errors, "$.claim.kind", "unknown claim kind")
        _nonempty_text(claim["statement"], "$.claim.statement", errors)

    mechanics = value.get("mechanics")
    if not isinstance(mechanics, list):
        _error(errors, "$.mechanics", "must be an array")
    else:
        for index, mechanic in enumerate(mechanics):
            path = f"$.mechanics[{index}]"
            if _exact_keys(mechanic, MECHANIC_KEYS, path, errors):
                _identifier(mechanic["id"], f"{path}.id", errors)
                _yaml_path(mechanic["path"], f"{path}.path", errors)
                _commit(mechanic["source_revision"], f"{path}.source_revision", errors)
                _digest(mechanic["raw_sha256"], f"{path}.raw_sha256", errors)

    payload = value.get("payload")
    if _exact_keys(payload, PAYLOAD_KEYS, "$.payload", errors):
        _identifier(payload["domain"], "$.payload.domain", errors)
        for name in ("model", "initial_state", "actions", "trajectory"):
            _digest(payload[f"{name}_sha256"], f"$.payload.{name}_sha256", errors)
        if not isinstance(payload["actions"], list):
            _error(errors, "$.payload.actions", "must be an array")
        if not isinstance(payload["trajectory"], list):
            _error(errors, "$.payload.trajectory", "must be an array")
        if not isinstance(payload["outcome"], dict):
            _error(errors, "$.payload.outcome", "must be an object")

    evidence = value.get("evidence")
    if _exact_keys(evidence, EVIDENCE_KEYS, "$.evidence", errors):
        checks = evidence["checks"]
        if not isinstance(checks, list):
            _error(errors, "$.evidence.checks", "must be an array")
        else:
            for index, check in enumerate(checks):
                path = f"$.evidence.checks[{index}]"
                if not _exact_keys(check, CHECK_KEYS, path, errors):
                    continue
                if not isinstance(check["kind"], str) or check["kind"] not in CHECK_KINDS:
                    _error(errors, f"{path}.kind", "unknown check kind")
                if not isinstance(check["status"], str) or check["status"] not in {"PASS", "FAIL"}:
                    _error(errors, f"{path}.status", "must be PASS or FAIL")
                checker = check["checker"]
                if _exact_keys(checker, CHECKER_KEYS, f"{path}.checker", errors):
                    _nonempty_text(checker["name"], f"{path}.checker.name", errors)
                    _nonempty_text(checker["revision"], f"{path}.checker.revision", errors)
                    _digest(checker["artifact_sha256"], f"{path}.checker.artifact_sha256", errors)
                labels = check["source_labels"]
                if not isinstance(labels, list):
                    _error(errors, f"{path}.source_labels", "must be an array")
                else:
                    for label_index, label in enumerate(labels):
                        _nonempty_text(label, f"{path}.source_labels[{label_index}]", errors)
                for name in ("initial_state", "actions", "trajectory"):
                    _digest(check[f"{name}_sha256"], f"{path}.{name}_sha256", errors)

        controls = evidence["negative_controls"]
        if not isinstance(controls, list):
            _error(errors, "$.evidence.negative_controls", "must be an array")
        else:
            for index, control in enumerate(controls):
                path = f"$.evidence.negative_controls[{index}]"
                if _exact_keys(control, NEGATIVE_CONTROL_KEYS, path, errors):
                    for name in ("name", "mutation", "observed"):
                        _nonempty_text(control[name], f"{path}.{name}", errors)
                    if not isinstance(control["passed"], bool):
                        _error(errors, f"{path}.passed", "must be a real boolean")

        limitations = evidence["limitations"]
        if not isinstance(limitations, list) or not limitations:
            _error(errors, "$.evidence.limitations", "must be a nonempty array")
        else:
            for index, limitation in enumerate(limitations):
                _nonempty_text(limitation, f"$.evidence.limitations[{index}]", errors)

    source = value.get("source")
    if _exact_keys(source, SOURCE_KEYS, "$.source", errors):
        _nonempty_text(source["media_type"], "$.source.media_type", errors)
        _digest(source["raw_sha256"], "$.source.raw_sha256", errors)
        if not isinstance(source["raw"], str):
            _error(errors, "$.source.raw", "must be a string containing exact source text")


def _compare_digest(actual: str, expected: str, path: str, errors: list[str]) -> None:
    if actual != expected:
        _error(errors, path, f"digest mismatch: recorded {actual}, computed {expected}")


def _validate_commitments(value: dict[str, Any], errors: list[str]) -> None:
    payload = value["payload"]
    for name in ("model", "initial_state", "actions", "trajectory"):
        _compare_digest(
            payload[f"{name}_sha256"],
            sha256_json(payload[name]),
            f"$.payload.{name}_sha256",
            errors,
        )

    for index, check in enumerate(value["evidence"]["checks"]):
        for name in ("initial_state", "actions", "trajectory"):
            _compare_digest(
                check[f"{name}_sha256"],
                payload[f"{name}_sha256"],
                f"$.evidence.checks[{index}].{name}_sha256",
                errors,
            )

    source = value["source"]
    try:
        raw_bytes = source["raw"].encode("utf-8")
    except UnicodeEncodeError:
        _error(errors, "$.source.raw", "must be encodable as exact UTF-8 bytes")
    else:
        _compare_digest(
            source["raw_sha256"],
            hashlib.sha256(raw_bytes).hexdigest(),
            "$.source.raw_sha256",
            errors,
        )

    unsigned = {key: child for key, child in value.items() if key != "artifact_sha256"}
    _compare_digest(
        value["artifact_sha256"],
        sha256_json(unsigned),
        "$.artifact_sha256",
        errors,
    )


def _derive_source_badges(value: dict[str, Any]) -> list[str]:
    """Summarize source assertions; any source FAIL is an unresolved veto."""
    badges = ["OBSERVED"]
    checks = value["evidence"]["checks"]
    if any(check["status"] == "FAIL" for check in checks):
        return badges
    if not any(control["passed"] for control in value["evidence"]["negative_controls"]):
        return badges

    passing_kinds = {check["kind"] for check in checks if check["status"] == "PASS"}
    if "model_replay" in passing_kinds:
        badges.append("REPLAYED")
    if "model_proof" in passing_kinds:
        badges.append("MODEL_PROVEN")
    if "live_execution" in passing_kinds and passing_kinds.intersection({"model_replay", "model_proof"}):
        # Structural validation already required all three check commitments to
        # equal the same payload commitments for every check.
        badges.append("LIVE_CONFIRMED")
    return [badge for badge in BADGE_ORDER if badge in badges]


def verify_gameplay_artifact(value: Any) -> dict[str, Any]:
    """Return source assertions separately from this consumer's admissions.

    ``valid=True`` never means a source check was independently rerun. Structural
    validation admits only ``OBSERVED``. Higher source badges remain assertions
    until a domain-specific consumer independently verifies the exact artifact.
    Invalid input has empty source and admitted badge lists.
    """
    errors: list[str] = []
    _validate_structure(value, errors)
    if not errors:
        _validate_commitments(value, errors)
    source_badges = _derive_source_badges(value) if not errors else []
    admitted_badges = ["OBSERVED"] if not errors else []
    return {
        "valid": not errors,
        "errors": errors,
        "source_badges": source_badges,
        "admitted_badges": admitted_badges,
    }


def derive_evidence_badges(value: Any) -> list[str]:
    """Return badges admitted by structural validation, or ``[]`` if invalid.

    This dependency-free validator does not rerun domain checks, so the only
    possible admission is ``OBSERVED``. Source-asserted badges are available in
    ``verify_gameplay_artifact(value)["source_badges"]``.
    """
    return verify_gameplay_artifact(value)["admitted_badges"]
