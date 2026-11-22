# Tier rules for the mcproof claim graph

Both checkers implement exactly these rules and nothing else:
`tools/verify.py` (Python, run in CI) and `docs/assets/proof-core.js`
(JavaScript, run in CI under Node and again in your browser). They share
no code. A disagreement fails the build.

Tiers, weakest to strongest: `OPEN < CONJECTURE < KNOWN < VERIFIED < PROVEN`.

- **R1 Shape.** Claim ids are unique. Every `depends_on` entry names an
  existing claim. The dependency graph has no cycle.
- **R2 Evidence.** A claim asserted `VERIFIED` or `PROVEN` carries at
  least one evidence link. An `obligation` asserted `OPEN` carries none.
- **R3 No tier inflation.** Compute each claim's allowed tier:
  - `axiom` and `definition`: allowed equals asserted (they are the
    stated trust base, listed under "What you must trust").
  - Any other kind: allowed starts at asserted, then:
    - if any dependency computes to `OPEN` or `CONJECTURE`, allowed is
      capped at `CONJECTURE`;
    - `PROVEN` additionally requires every dependency to compute to
      `VERIFIED` or `PROVEN`, or to be an axiom or definition.
  - The claim passes only if asserted is no stronger than allowed.
- **R4 Computed tier.** A passing claim's computed tier is its asserted
  tier. A failing claim computes to `OPEN` and is reported by name.
- **R5 Certificate.** The certificate records the SHA-256 of the exact
  bytes of `claims.json`, each claim's computed tier, and the list of
  open obligations. It contains no timestamp, so rebuilding from the
  same file gives the same certificate byte for byte.
