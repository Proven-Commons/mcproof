# Gameplay Evidence Exchange v0.1

`mcproof.gameplay_evidence` implements the closed interchange envelope in [`schema/gameplay-evidence-v0.1.schema.json`](../schema/gameplay-evidence-v0.1.schema.json). It uses only the Python standard library.

```python
from mcproof.gameplay_evidence import load_gameplay_artifact, verify_gameplay_artifact

artifact = load_gameplay_artifact(received_text)  # rejects duplicate JSON keys
report = verify_gameplay_artifact(artifact)
if not report["valid"]:
    raise ValueError(report["errors"])
print(report["source_badges"])
print(report["admitted_badges"])
```

`canonical_json_bytes` emits sorted, compact, ASCII-escaped UTF-8 JSON. `sha256_json` hashes those bytes.

The verifier recomputes the artifact self-digest, exact source UTF-8 digest, four payload commitments, and three payload commitments on every check. It rejects unknown or missing envelope keys, duplicate keys during loading, every floating-point value, integers outside signed 64 bits, non-string object keys, malformed or all-zero SHA-256 fields, and non-boolean negative-control results.

## Badge boundary

`source_badges` summarizes the producer's checks. Higher source badges require the explicit passing checks and a passing negative control stated in the contract. `LIVE_CONFIRMED` also needs passing model replay or model proof over the same payload commitments. `MODEL_PROVEN` and `LIVE_CONFIRMED` remain independent. Any recorded `FAIL` is an unresolved aggregation veto, so a second `PASS` cannot hide it. Missing checks or negative controls do not promote an artifact.

`admitted_badges` contains only `OBSERVED`: this dependency-free module validates structure and commitments but does not independently rerun domain checks. Higher admissions belong to a trusted domain verifier bound to the exact artifact, check, and negative-control digests. `derive_evidence_badges` returns only the admitted list.

`source_labels` is preserved as source data and ignored by source badge derivation. In particular, `VERIFIED`, `MODEL_PROVEN`, or `LIVE_CONFIRMED` supplied as labels cannot promote evidence. Invalid artifacts always return empty source and admitted lists.

## What validation does not establish

A `valid` report establishes structural and digest consistency only. It does **not** parse or execute `source.raw`, rerun replay/proof/live checkers, validate SimGrammar YAML, establish that negative-control prose genuinely documents rejection, or resolve domain semantics.

A trusted domain adapter must do those checks separately. Source check records, checker pins, controls, limitations, and labels remain claims bound by the envelope, not independently reproduced findings.

The JSON Schema closes the envelope and expresses field types, formats, and recursive JSON-safe values where practical. JSON Schema alone cannot reject duplicate input keys, compare digests, hash exact source bytes, derive badges, or consistently distinguish lexical floats such as `1.0` from integers across implementations. The runtime verifier rejects every float and is authoritative for those rules.
