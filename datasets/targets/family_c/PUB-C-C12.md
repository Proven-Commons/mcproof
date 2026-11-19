Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 304,
    "head_sha": "70fc0294988a88e06f15258a681734cec9a2dd55",
    "base_sha": "038f8fe45b9f313345dbfe82b75f601ed79c1689",
    "kappa_num": 242889,
    "kappa_den": 6250000000,
    "kappa_decimal": "0.00003886224",
    "tier": "claimed",
    "title": "Binomial layer packing candidate with kappa = 242889/6250000000",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/304",
      "head_url": "https://github.com/Foundation-0/f0/tree/70fc0294988a88e06f15258a681734cec9a2dd55",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 242889/6250000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
