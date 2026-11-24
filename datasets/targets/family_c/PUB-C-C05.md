Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 301,
    "head_sha": "b15c7bb3bfc2a58e5dc01bc31933e523f086ed3b",
    "base_sha": "fac80110683f469df17a046cb7a8de056e38ceda",
    "kappa_num": 1479,
    "kappa_den": 1000000000000,
    "kappa_decimal": "0.000000001479",
    "tier": "claimed",
    "title": "Conditional residue sieve witness with kappa = 1479/10^12",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/301",
      "head_url": "https://github.com/Foundation-0/f0/tree/b15c7bb3bfc2a58e5dc01bc31933e523f086ed3b",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 1479/1000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
