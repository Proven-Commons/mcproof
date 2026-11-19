Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 404,
    "head_sha": "0e88dcfbc2b516a3332fee057452f808f44d7635",
    "base_sha": "8c0cbaf7a8482e148a245c239b3b6813f33496a7",
    "kappa_num": 257077122735047,
    "kappa_den": 5000000000000000000,
    "kappa_decimal": "0.0000514154245470094",
    "tier": "claimed",
    "title": "Two-phase lease quorum trace candidate kappa = 257077122735047/5*10^18",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/404",
      "head_url": "https://github.com/Foundation-0/f0/tree/0e88dcfbc2b516a3332fee057452f808f44d7635",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 257077122735047/5000000000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
