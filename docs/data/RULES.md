# Tier rules for the mcproof claim graph

Both checkers implement exactly these rules and nothing else:
`tools/verify.py` (Python, run in CI) and `docs/assets/proof-core.js`
(JavaScript, run in CI under Node and again in your browser). They share
no code. A disagreement fails the build.

Tiers, weakest to strongest: `OPEN < CONJECTURE < KNOWN < VERIFIED < PROVEN`.

- **R1 Shape.** Claim ids are unique and match `^[A-Za-z][A-Za-z0-9_-]*$`
  (so `__proto__` and friends can never be ids). Every claim has a
  non-empty title, statement, and a known section. Every `depends_on`
  entry is a string naming an existing claim. The list is non-empty and
  the dependency graph has no cycle. Duplicate JSON keys are rejected
  by the Python checker at parse time; the browser detects any byte
  change, duplicate keys included, as a certificate hash mismatch.
- **R2 Evidence.** A claim asserted `VERIFIED` or `PROVEN` carries at
  least one evidence link. Every evidence entry is an object with a
  non-empty label and a URL that is either `https://` or a plain
  relative path (no `javascript:`, `data:`, or protocol-relative URLs).
  An `obligation` asserted `OPEN` carries none.
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
