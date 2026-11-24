Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 401,
    "head_sha": "a5b15453478a0ef6fc8253f5dfb3d44f8649aedd",
    "base_sha": "3c6146efc462d57d0d52819680d07ff885094f2a",
    "kappa_num": 7939287,
    "kappa_den": 500000000000,
    "kappa_decimal": "0.000015878574",
    "tier": "claimed",
    "title": "Modular totient sieve candidate for kappa = 7939287/500000000000",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/401",
      "head_url": "https://github.com/Foundation-0/f0/tree/a5b15453478a0ef6fc8253f5dfb3d44f8649aedd",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 7939287/500000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
