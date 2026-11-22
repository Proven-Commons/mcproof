"""Adversarial unit tests for Gameplay Evidence Exchange v0.1."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from mcproof.gameplay_evidence import (
    INT64_MAX,
    INT64_MIN,
    canonical_json_bytes,
    derive_evidence_badges,
    load_gameplay_artifact,
    sha256_json,
    verify_gameplay_artifact,
)


def _check(kind: str, payload: dict, status: str = "PASS", labels: list[str] | None = None) -> dict:
    return {
        "kind": kind,
        "status": status,
        "checker": {
            "name": f"{kind}-checker",
            "revision": "c" * 40,
            "artifact_sha256": sha256_json({"checker": kind, "revision": "c" * 40}),
        },
        "source_labels": list(labels if labels is not None else ["VERIFIED", f"SOURCE_{kind}"]),
        "initial_state_sha256": payload["initial_state_sha256"],
        "actions_sha256": payload["actions_sha256"],
        "trajectory_sha256": payload["trajectory_sha256"],
    }


def _control(passed: bool = True) -> dict:
    return {
        "name": "drop-final-state",
        "mutation": "Remove the final trajectory state",
        "observed": "rejected: trajectory commitment mismatch",
        "passed": passed,
    }


def valid_artifact() -> dict:
    """Build a deterministic observation with one replay and one control."""
    model = {"rules": "east increments position", "assumptions": ["deterministic"]}
    initial_state = {"position": 0}
    actions = ["east"]
    trajectory = [{"position": 0}, {"position": 1}]
    payload = {
        "domain": "toy-grid",
        "model": model,
        "model_sha256": sha256_json(model),
        "initial_state": initial_state,
        "initial_state_sha256": sha256_json(initial_state),
        "actions": actions,
        "actions_sha256": sha256_json(actions),
        "trajectory": trajectory,
        "trajectory_sha256": sha256_json(trajectory),
        "outcome": {"goal_reached": True},
    }
    raw = '{\n  "source_schema": "observation/v7",\n  "label": "VERIFIED",\n  "tick": 1\n}\n'
    artifact = {
        "schema": "gameplay-evidence/v0.1",
        "producer": {
            "repository": "Proven-Commons/mcproof",
            "revision": "a" * 40,
            "adapter": "mcproof.gameplay_evidence",
        },
        "claim": {
            "id": "route-1",
            "kind": "route",
            "statement": "Moving east reaches position one.",
        },
        "mechanics": [
            {
                "id": "grid-mechanics",
                "path": "mechanics/grid.yaml",
                "source_revision": "b" * 40,
                "raw_sha256": hashlib.sha256(b"position: integer\n").hexdigest(),
            }
        ],
        "payload": payload,
        "evidence": {
            "checks": [_check("model_replay", payload)],
            "negative_controls": [_control()],
            "limitations": ["The consumer has not independently rerun the source replay."],
        },
        "source": {
            "media_type": "application/json",
            "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "raw": raw,
        },
    }
    reseal(artifact)
    return artifact


def reseal(artifact: dict) -> None:
    artifact.pop("artifact_sha256", None)
    artifact["artifact_sha256"] = sha256_json(artifact)


def node(artifact: dict, path: tuple[object, ...]):
    current = artifact
    for component in path:
        current = current[component]
    return current


class CanonicalJSONTests(unittest.TestCase):
    def test_canonical_bytes_and_digest_are_deterministic(self) -> None:
        value = {"b": [1, True, None], "a": "é"}
        expected = b'{"a":"\\u00e9","b":[1,true,null]}'
        self.assertEqual(canonical_json_bytes(value), expected)
        self.assertEqual(sha256_json(value), hashlib.sha256(expected).hexdigest())
        self.assertEqual(canonical_json_bytes(value), canonical_json_bytes(copy.deepcopy(value)))

    def test_canonical_rejects_non_string_keys_cycles_and_unsupported_types(self) -> None:
        with self.assertRaises(TypeError):
            canonical_json_bytes({1: "not a string key"})
        with self.assertRaises(TypeError):
            canonical_json_bytes((1, 2))
        cyclic: list = []
        cyclic.append(cyclic)
        with self.assertRaises(ValueError):
            canonical_json_bytes(cyclic)

    def test_canonical_rejects_every_float(self) -> None:
        for value in (1.0, 1.5, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_json_bytes(value)

    def test_canonical_enforces_signed_64_bit_boundaries(self) -> None:
        self.assertEqual(canonical_json_bytes(INT64_MIN), str(INT64_MIN).encode())
        self.assertEqual(canonical_json_bytes(INT64_MAX), str(INT64_MAX).encode())
        for value in (INT64_MIN - 1, INT64_MAX + 1, float(INT64_MAX + 1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_json_bytes(value)


class StrictLoadingTests(unittest.TestCase):
    def test_valid_round_trip_and_json_safe_report(self) -> None:
        artifact = valid_artifact()
        loaded = load_gameplay_artifact(canonical_json_bytes(artifact).decode("utf-8"))
        report = verify_gameplay_artifact(loaded)
        self.assertEqual(
            report,
            {
                "valid": True,
                "errors": [],
                "source_badges": ["OBSERVED", "REPLAYED"],
                "admitted_badges": ["OBSERVED"],
            },
        )
        json.dumps(report, allow_nan=False)

    def test_duplicate_keys_are_rejected_at_every_depth(self) -> None:
        samples = (
            '{"schema":"gameplay-evidence/v0.1","schema":"gameplay-evidence/v0.1"}',
            '{"producer":{"repository":"o/r","repository":"x/y"}}',
            '{"payload":{"outcome":{"x":1,"x":2}}}',
        )
        for text in samples:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "duplicate"):
                load_gameplay_artifact(text)

    def test_non_finite_json_constants_and_non_text_input_are_rejected(self) -> None:
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                load_gameplay_artifact('{"x":' + token + "}")
        with self.assertRaises(TypeError):
            load_gameplay_artifact(b"{}")

    def test_loader_does_not_parse_raw_source(self) -> None:
        artifact = valid_artifact()
        # Duplicate keys and even malformed source documents remain opaque raw
        # evidence during canonical envelope validation.
        for raw in ('{"x":1,"x":1}', "not JSON at all"):
            with self.subTest(raw=raw):
                candidate = copy.deepcopy(artifact)
                candidate["source"]["raw"] = raw
                candidate["source"]["raw_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
                reseal(candidate)
                self.assertTrue(verify_gameplay_artifact(candidate)["valid"])


class ArtifactReportAssertions:
    def assertInvalid(self, artifact, contains: str | None = None) -> dict:
        report = verify_gameplay_artifact(artifact)
        self.assertFalse(report["valid"], report)
        self.assertEqual(report["source_badges"], [])
        self.assertEqual(report["admitted_badges"], [])
        self.assertTrue(report["errors"])
        if contains is not None:
            self.assertIn(contains, "\n".join(report["errors"]))
        json.dumps(report, allow_nan=False)
        return report


class StructuralValidationTests(ArtifactReportAssertions, unittest.TestCase):
    def test_non_object_and_wrong_schema_are_invalid(self) -> None:
        for value in (None, [], "artifact", 1, True):
            with self.subTest(value=value):
                self.assertInvalid(value)
        artifact = valid_artifact()
        artifact["schema"] = "gameplay-evidence/v0.2"
        self.assertInvalid(artifact, "schema")

    def test_every_closed_object_rejects_unknown_keys(self) -> None:
        paths = (
            (),
            ("producer",),
            ("claim",),
            ("mechanics", 0),
            ("payload",),
            ("evidence",),
            ("evidence", "checks", 0),
            ("evidence", "checks", 0, "checker"),
            ("evidence", "negative_controls", 0),
            ("source",),
        )
        for path in paths:
            with self.subTest(path=path):
                artifact = valid_artifact()
                node(artifact, path)["unexpected"] = "closed-envelope-bypass"
                self.assertInvalid(artifact, "unknown keys")

    def test_missing_required_keys_are_invalid(self) -> None:
        artifact = valid_artifact()
        for key in artifact:
            with self.subTest(key=key):
                candidate = copy.deepcopy(artifact)
                del candidate[key]
                self.assertInvalid(candidate, "missing keys")

    def test_wrong_container_types_and_unhashable_enums_fail_closed(self) -> None:
        mutations = (
            ("mechanics", {}, "mechanics"),
            (("payload", "actions"), {}, "actions"),
            (("payload", "trajectory"), {}, "trajectory"),
            (("payload", "outcome"), [], "outcome"),
            (("evidence", "checks"), {}, "checks"),
            (("evidence", "negative_controls"), {}, "negative_controls"),
            (("evidence", "limitations"), [], "limitations"),
            (("claim", "kind"), [], "kind"),
            (("evidence", "checks", 0, "status"), [], "status"),
        )
        for item in mutations:
            path, replacement, message = item
            path = (path,) if isinstance(path, str) else path
            with self.subTest(path=path):
                artifact = valid_artifact()
                parent = node(artifact, path[:-1])
                parent[path[-1]] = replacement
                self.assertInvalid(artifact, message)

    def test_identifiers_repository_and_revisions_are_strict(self) -> None:
        cases = []
        for bad in ("", "has space", "é", "slash/not-allowed"):
            cases.append((("claim", "id"), bad))
            cases.append((("payload", "domain"), bad))
        for bad in ("owner-only", "owner/repo/extra", "owner repo/name", 1):
            cases.append((("producer", "repository"), bad))
        for path in (("producer", "revision"), ("mechanics", 0, "source_revision")):
            for bad in ("A" * 40, "a" * 39, "g" * 40, 1):
                cases.append((path, bad))
        for path, bad in cases:
            with self.subTest(path=path, bad=bad):
                artifact = valid_artifact()
                node(artifact, path[:-1])[path[-1]] = bad
                self.assertInvalid(artifact)

    def test_mechanic_paths_are_repository_relative_yaml_only(self) -> None:
        for bad in ("", "/abs.yaml", "../escape.yaml", "./local.yaml", "a//b.yaml", "a/../b.yaml", "a\\b.yaml", "rules.txt"):
            with self.subTest(path=bad):
                artifact = valid_artifact()
                artifact["mechanics"][0]["path"] = bad
                self.assertInvalid(artifact, "path")

    def test_nonempty_fields_and_source_labels_are_validated(self) -> None:
        paths = (
            ("claim", "statement"),
            ("producer", "adapter"),
            ("evidence", "limitations", 0),
            ("evidence", "checks", 0, "source_labels", 0),
            ("evidence", "checks", 0, "checker", "name"),
            ("evidence", "checks", 0, "checker", "revision"),
            ("evidence", "negative_controls", 0, "observed"),
            ("source", "media_type"),
        )
        for path in paths:
            for bad in ("", " \t\n", None):
                with self.subTest(path=path, bad=bad):
                    artifact = valid_artifact()
                    node(artifact, path[:-1])[path[-1]] = bad
                    self.assertInvalid(artifact)

    def test_negative_control_passed_requires_real_boolean(self) -> None:
        for bad in (1, 0, "true", None):
            with self.subTest(value=bad):
                artifact = valid_artifact()
                artifact["evidence"]["negative_controls"][0]["passed"] = bad
                self.assertInvalid(artifact, "real boolean")

    def test_all_floats_and_unsafe_integers_are_rejected_in_payload_data(self) -> None:
        for bad in (1.0, 1.5, float("nan"), float("inf"), INT64_MIN - 1, INT64_MAX + 1):
            with self.subTest(value=bad):
                artifact = valid_artifact()
                artifact["payload"]["initial_state"]["position"] = bad
                self.assertInvalid(artifact)

    def test_non_string_keys_and_cycles_do_not_escape_or_crash_validation(self) -> None:
        artifact = valid_artifact()
        artifact["payload"]["model"][1] = "non-string key"
        self.assertInvalid(artifact, "keys")
        artifact = valid_artifact()
        artifact["payload"]["initial_state"]["cycle"] = artifact["payload"]["initial_state"]
        self.assertInvalid(artifact, "cyclic")


class DigestValidationTests(ArtifactReportAssertions, unittest.TestCase):
    def test_every_sha256_field_rejects_malformed_uppercase_and_all_zero_values(self) -> None:
        paths = (
            ("artifact_sha256",),
            ("mechanics", 0, "raw_sha256"),
            ("payload", "model_sha256"),
            ("payload", "initial_state_sha256"),
            ("payload", "actions_sha256"),
            ("payload", "trajectory_sha256"),
            ("source", "raw_sha256"),
            ("evidence", "checks", 0, "checker", "artifact_sha256"),
            ("evidence", "checks", 0, "initial_state_sha256"),
            ("evidence", "checks", 0, "actions_sha256"),
            ("evidence", "checks", 0, "trajectory_sha256"),
        )
        for path in paths:
            for bad in ("0" * 64, "A" * 64, "a" * 63, "g" * 64, True):
                with self.subTest(path=path, bad=bad):
                    artifact = valid_artifact()
                    node(artifact, path[:-1])[path[-1]] = bad
                    self.assertInvalid(artifact)

    def test_self_digest_detects_otherwise_valid_tampering(self) -> None:
        artifact = valid_artifact()
        artifact["claim"]["statement"] = "A different claim with the old self digest."
        self.assertInvalid(artifact, "$.artifact_sha256: digest mismatch")

    def test_source_digest_binds_exact_raw_utf8_bytes(self) -> None:
        artifact = valid_artifact()
        artifact["source"]["raw"] += " "
        reseal(artifact)
        self.assertInvalid(artifact, "$.source.raw_sha256: digest mismatch")

    def test_all_payload_digests_bind_their_canonical_values(self) -> None:
        replacements = {
            "model": {"rules": "different"},
            "initial_state": {"position": 99},
            "actions": ["west"],
            "trajectory": [{"position": 0}],
        }
        for name, replacement in replacements.items():
            with self.subTest(name=name):
                artifact = valid_artifact()
                artifact["payload"][name] = replacement
                reseal(artifact)
                self.assertInvalid(artifact, f"$.payload.{name}_sha256: digest mismatch")

    def test_all_check_digests_must_match_payload_commitments(self) -> None:
        for name in ("initial_state", "actions", "trajectory"):
            with self.subTest(name=name):
                artifact = valid_artifact()
                artifact["evidence"]["checks"][0][f"{name}_sha256"] = sha256_json({"different": name})
                reseal(artifact)
                self.assertInvalid(artifact, f"checks[0].{name}_sha256: digest mismatch")

    def test_source_raw_must_be_exact_utf8_encodable_text(self) -> None:
        artifact = valid_artifact()
        artifact["source"]["raw"] = "\ud800"
        self.assertInvalid(artifact, "UTF-8")


class BadgeDerivationTests(ArtifactReportAssertions, unittest.TestCase):
    def assertSourceBadges(self, artifact: dict, expected: list[str]) -> None:
        report = verify_gameplay_artifact(artifact)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["source_badges"], expected)
        self.assertEqual(report["admitted_badges"], ["OBSERVED"])
        self.assertEqual(derive_evidence_badges(artifact), ["OBSERVED"])

    def with_checks(self, kinds_and_statuses: list[tuple[str, str]], controls: bool = True) -> dict:
        artifact = valid_artifact()
        artifact["evidence"]["checks"] = [
            _check(kind, artifact["payload"], status=status) for kind, status in kinds_and_statuses
        ]
        artifact["evidence"]["negative_controls"] = [_control()] if controls else []
        reseal(artifact)
        return artifact

    def test_observation_is_default_ceiling_without_checks_or_controls(self) -> None:
        self.assertSourceBadges(self.with_checks([], controls=False), ["OBSERVED"])
        self.assertSourceBadges(self.with_checks([("model_replay", "FAIL")], controls=False), ["OBSERVED"])

    def test_replay_and_model_proof_require_a_passing_control(self) -> None:
        for kind, badge in (("model_replay", "REPLAYED"), ("model_proof", "MODEL_PROVEN")):
            with self.subTest(kind=kind, controls=False):
                self.assertSourceBadges(self.with_checks([(kind, "PASS")], controls=False), ["OBSERVED"])
            with self.subTest(kind=kind, passed=False):
                artifact = self.with_checks([(kind, "PASS")])
                artifact["evidence"]["negative_controls"][0]["passed"] = False
                reseal(artifact)
                self.assertSourceBadges(artifact, ["OBSERVED"])

    def test_model_proof_and_live_confirmation_are_separate(self) -> None:
        self.assertSourceBadges(self.with_checks([("model_proof", "PASS")]), ["OBSERVED", "MODEL_PROVEN"])
        self.assertSourceBadges(
            self.with_checks([("model_proof", "PASS"), ("live_execution", "PASS")]),
            ["OBSERVED", "MODEL_PROVEN", "LIVE_CONFIRMED"],
        )
        self.assertSourceBadges(
            self.with_checks([("model_replay", "PASS"), ("live_execution", "PASS")]),
            ["OBSERVED", "REPLAYED", "LIVE_CONFIRMED"],
        )

    def test_live_confirmation_cannot_ignore_missing_model_support(self) -> None:
        self.assertSourceBadges(self.with_checks([("live_execution", "PASS")]), ["OBSERVED"])

    def test_any_fail_is_an_unresolved_aggregation_veto(self) -> None:
        cases = (
            [("model_replay", "PASS"), ("model_replay", "FAIL")],
            [("model_replay", "PASS"), ("live_execution", "FAIL")],
            [("model_proof", "PASS"), ("model_replay", "PASS"), ("live_execution", "FAIL")],
        )
        for checks in cases:
            with self.subTest(checks=checks):
                self.assertSourceBadges(self.with_checks(checks), ["OBSERVED"])

    def test_source_labels_never_promote_and_are_preserved(self) -> None:
        artifact = valid_artifact()
        artifact["evidence"]["checks"][0]["source_labels"] = [
            "VERIFIED",
            "MODEL_PROVEN",
            "LIVE_CONFIRMED",
            "arbitrary upstream label",
        ]
        artifact["evidence"]["negative_controls"] = []
        reseal(artifact)
        before = copy.deepcopy(artifact)
        self.assertSourceBadges(artifact, ["OBSERVED"])
        self.assertEqual(artifact, before)
        self.assertEqual(artifact["evidence"]["checks"][0]["source_labels"], before["evidence"]["checks"][0]["source_labels"])

    def test_invalid_artifacts_have_no_derived_badges(self) -> None:
        artifact = valid_artifact()
        artifact["claim"]["statement"] = "tampered"
        self.assertEqual(derive_evidence_badges(artifact), [])
        self.assertInvalid(artifact)


class SchemaTests(unittest.TestCase):
    def test_schema_is_json_and_closes_every_envelope_object(self) -> None:
        path = Path(__file__).resolve().parents[1] / "schema" / "gameplay-evidence-v0.1.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), set(valid_artifact()) - {"artifact_sha256"} | {"artifact_sha256"})
        self.assertFalse(schema["additionalProperties"])
        for name in ("producer", "claim", "payload", "evidence", "source"):
            self.assertFalse(schema["properties"][name]["additionalProperties"])
        for name in ("mechanic", "check", "negativeControl"):
            self.assertFalse(schema["definitions"][name]["additionalProperties"])
        self.assertFalse(schema["definitions"]["check"]["properties"]["checker"]["additionalProperties"])
        self.assertEqual(schema["properties"]["schema"]["const"], "gameplay-evidence/v0.1")


if __name__ == "__main__":
    unittest.main()
