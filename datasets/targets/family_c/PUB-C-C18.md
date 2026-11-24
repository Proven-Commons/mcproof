Claim-Tier: VERIFIED

```json
{
  "record": {
    "pr": 306,
    "head_sha": "0cd16fd34f179d43418edebb74c7998e272fd00d",
    "base_sha": "81117502d9cbefe899be8a51c2aa49539ce16eab",
    "kappa_num": 90446448750933,
    "kappa_den": 125000000000000000,
    "kappa_decimal": "0.000723571590007464",
    "tier": "human-verified",
    "title": "Verified rational interval determinant bank bound to upstream selected certificate",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/306",
      "head_url": "https://github.com/Foundation-0/f0/tree/0cd16fd34f179d43418edebb74c7998e272fd00d",
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
