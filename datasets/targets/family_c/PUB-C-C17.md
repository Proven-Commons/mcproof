Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 305,
    "head_sha": "4cd0a755de1f948a6941a4b92f78145a9dd6977b",
    "base_sha": "70a8b8b21a86aa08f62641416c3e091eb277ae9c",
    "kappa_num": 1959367447,
    "kappa_den": 50000000000000,
    "kappa_decimal": "0.00003918734894",
    "tier": "claimed",
    "title": "Rational Farkas cone certificate candidate for kappa = 1959367447/50000000000000",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/305",
      "head_url": "https://github.com/Foundation-0/f0/tree/4cd0a755de1f948a6941a4b92f78145a9dd6977b",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 1959367447/50000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
