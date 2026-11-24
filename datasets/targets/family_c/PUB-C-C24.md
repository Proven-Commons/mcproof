Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 308,
    "head_sha": "442b5cc1b2b2fdd352ebe20a382c5e0a5a5a1ef1",
    "base_sha": "a71f9dc4746f98ec191db4866811a77affc5ed67",
    "kappa_num": 120777349,
    "kappa_den": 2500000000000,
    "kappa_decimal": "0.0000483109396",
    "tier": "claimed",
    "title": "Token-ring schedule contraction candidate with kappa = 120777349/2500000000000",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/308",
      "head_url": "https://github.com/Foundation-0/f0/tree/442b5cc1b2b2fdd352ebe20a382c5e0a5a5a1ef1",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 120777349/2500000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
