Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 307,
    "head_sha": "8a36d841ad91b73cd8f55d99087bc97a2be4f612",
    "base_sha": "463bdb39741db0e9157fd7fd528a8dd2c37471e3",
    "kappa_num": 1020702544357,
    "kappa_den": 20000000000000000,
    "kappa_decimal": "0.00005103512721785",
    "tier": "claimed",
    "title": "Bounded FIFO state-space density candidate with kappa = 1020702544357/2*10^16",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/307",
      "head_url": "https://github.com/Foundation-0/f0/tree/8a36d841ad91b73cd8f55d99087bc97a2be4f612",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 1020702544357/20000000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
