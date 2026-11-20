Claim-Tier: VERIFIED

```json
{
  "record": {
    "pr": 302,
    "head_sha": "a3ba8c2264e241092ededf50a9e943019f2dd2bb",
    "base_sha": "41d2a060f06865daee902eb80fcb0e5315c3c85a",
    "kappa_num": 90446448750933,
    "kappa_den": 125000000000000000,
    "kappa_decimal": "0.000723571590007464",
    "tier": "human-verified",
    "title": "Maintainer-audited Bezoutlattice bank matching upstream selected certificate",
    "draft": false,
    "pr_updated_at": "2026-11-18T12:00:00Z",
    "fetched_at": "2026-11-19T00:00:00Z",
    "source_refs": {
      "pr_url": "https://github.com/Foundation-0/f0/pull/302",
      "head_url": "https://github.com/Foundation-0/f0/tree/a3ba8c2264e241092ededf50a9e943019f2dd2bb",
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
