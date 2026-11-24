Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 403,
    "head_sha": "c22ba21155913a8974400b8f2b746c907ba35b24",
    "base_sha": "c4a87841184ff82e179fe8e37cdd13d49c60aae0",
    "kappa_num": 2050314627,
    "kappa_den": 50000000000000,
    "kappa_decimal": "0.00004100629254",
    "tier": "claimed",
    "title": "Exact Gaussian pivot growth bound candidate kappa = 2050314627/50000000000000",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/403",
      "head_url": "https://github.com/Foundation-0/f0/tree/c22ba21155913a8974400b8f2b746c907ba35b24",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 2050314627/50000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
