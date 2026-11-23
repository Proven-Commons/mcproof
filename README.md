repo for the formal verification MDE
a formal verification domain for models to operate within
goal is to have them apply concepts to unlock scientific/mathematic progress, similar to the way it has been done in [f0](https://github.com/Foundation-0)

blueprint:
[# mcproof](https://github.com/siliconcordat/mde/issues/4)

## The site is a proof

The GitHub Pages site in `docs/` is written as a formal derivation. Every
claim on it is one record in `docs/data/claims.json`, with a kind (axiom,
definition, lemma, theorem, obligation, hazard guard), a certainty tier
(`OPEN` to `PROVEN`), its dependencies, and its evidence. Tiers are never
typed into the page by hand. Two checkers that share no code recompute
them from the tier rules in `docs/data/RULES.md`:

- `tools/verify.py` (Python) writes `docs/data/certificate.json`.
- `docs/assets/proof-core.js` (JavaScript) runs under Node in CI and
  again in the visitor's browser, where it rehashes `claims.json` and
  compares its verdict with the certificate.

The main claim, Theorem T0, computes to `CONJECTURE` while obligations
O1 to O5 are open. The checkers cap it there, so the site cannot upgrade
its own headline. The page figure, stats, colours, and background weave
are all deterministic functions of the claim graph and its SHA-256.

CI is the gate: the Pages workflow runs the Python checker three ways,
rejects planted corruptions of the graph (`tools/run_mutations.py`),
checks the JavaScript checker against the certificate and runs checker
parity tests (`node --test "test/*.test.mjs"`), and builds the page twice
to prove the output is byte-identical. Upload and deploy run only on
`main` when the repository variable `PAGES_ENABLED` is set to `true`
(Settings → Secrets and variables → Actions → Variables); until then
verify still runs on every push but Pages is not published. No proof, no
publish.

`tools/build.py --verify` rebuilds prerendered regions from
`claims.json`; the workflow's `git diff` step is what catches edits
outside those regions.

Work on it locally:

```sh
python3 -I -B tools/build.py --verify   # rebuild docs/index.html
python3 -m http.server -d docs 8000     # then open http://localhost:8000
```

Design lineage: the record-keeping discipline and instrument framing of
[Foundation0](https://fdn0.org), and the style-as-a-point design language
of [Eido](https://github.com/Moissanite-Labs/weft-eido) by Moissanite
Labs. The simplex mixer, circular hue blending, and `data-eido-skip`
condense refusal on proof blocks follow Eido's published modules and
guides.
