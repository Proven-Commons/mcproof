Claim-Tier: VERIFIED

```json
{
  "record": {
    "pr": 402,
    "head_sha": "3b85808185197ee819b563d7ab12058aa060f88c",
    "base_sha": "2d1b7f0542384444132af37aa69c08bb44d73d1b",
    "kappa_num": 90446448750933,
    "kappa_den": 125000000000000000,
    "kappa_decimal": "0.000723571590007464",
    "tier": "human-verified",
    "title": "Maintainer-verified finite hypergraph matching bank bound to selected certificate",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/402",
      "head_url": "https://github.com/Foundation-0/f0/tree/3b85808185197ee819b563d7ab12058aa060f88c",
      "certificate_path": "certificates/selected-result.json"
    },
    "verify": {
      "method": "selected-result-binding",
      "certificate_sha256": "6b581846dbc0e5dbbb4014ff12922f38736b7632423c1cdc2a02df1541f83268",
      "checker_exit": 0
    }
  },
  "chart_bucket": "verified"
}
```

## What is not proved

- Universal asymptotic optimality beyond the finite rational parameter `kappa = 90446448750933/125000000000000000`.
- No kernel-checked Lean theorem backs this v1 staging record.

## What you must trust

- Exact `Decimal` 15-digit fraction-to-decimal agreement and SHA-256 certificate byte recomputation in `scripts/gate.py`.
- Python runtime, Git blob hashing, and underlying host hardware.
