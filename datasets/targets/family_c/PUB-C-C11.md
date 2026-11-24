Claim-Tier: CONJECTURE

```json
{
  "record": {
    "pr": 303,
    "head_sha": "0c51f97da6208e20e30d5a1495c58f36013f6b4a",
    "base_sha": "2fe986b4c377468c4857b932a48a6c7badee2416",
    "kappa_num": 57114918,
    "kappa_den": 10000000000000,
    "kappa_decimal": "0.0000057114918",
    "tier": "claimed",
    "title": "Bipartite neighborhood expansion candidate for kappa = 57114918/10^13",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/303",
      "head_url": "https://github.com/Foundation-0/f0/tree/0c51f97da6208e20e30d5a1495c58f36013f6b4a",
      "certificate_path": null
    }
  },
  "chart_bucket": "claimed"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 57114918/10000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
