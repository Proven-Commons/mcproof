# mcproof Lean 4 Reference Package

`mcproof` in `lean/` is a stock-`Init` Lean 4.35.0 library and executable that checks bounded clamping, integer Bezout witnesses, division-free rational order, and path-segment containment. Proof engineers and automated verification harnesses use it to validate multi-kernel theorem checking and anti-bypass rules under the [Proven Commons Verified Bar](https://github.com/Proven-Commons/mission/blob/main/playbook/verified-bar.md).

Status: in progress. Independent human specification review has not been recorded yet, so this package is not verified.

## What is proved

| Claim | Theorem |
| --- | --- |
| When `lo <= hi`, `clampNat lo hi x` stays between `lo` and `hi`. | `Mcproof.Spec.clampNat_in_range` |
| An input already in `[lo, hi]` returns unchanged from `clampNat`. | `Mcproof.Spec.clampNat_of_mem` |
| `bezoutCheck` returns `true` only when `a * x + b * y = g`. | `Mcproof.Spec.bezoutCheck_sound` |
| Every valid witness `a * x + b * y = g` passes `bezoutCheck`. | `Mcproof.Spec.bezoutCheck_complete` |
| `ratLeCross` returns `true` only when `0 < d1`, `0 < d2`, and `n1 * d2 <= n2 * d1`. | `Mcproof.Spec.ratLeCross_sound` |
| Every fraction with `0 < d` passes `ratLeCross n d n d`. | `Mcproof.Spec.ratLeCross_refl_pos` |
| Accepted path lists from `cleanSegments` are non-empty and exclude `.`, `..`, `/`, and NUL. | `Mcproof.Spec.cleanSegments_safe` |
| A single valid segment `[s]` returns `some [s]` from `cleanSegments`. | `Mcproof.Spec.cleanSegments_singleton` |

## What is not proved

- Command-line string parsing and standard-output formatting in `Main.lean` are covered by differential tests rather than Lean theorems.
- Operating-system symlink resolution on live filesystems sits outside lexical segment checks.
- Execution latency and memory usage are not proved.

## What you must trust

- The Lean 4.35.0 kernel and the five bundled external kernels (`leanchecker-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`).
- The Lean compiler and C runtime that lower `Mcproof.lean` and `Main.lean` into native machine code.
- The host hardware, operating system, and `bubblewrap` sandbox on Linux hosts.
- Python 3 exact `int` and `fractions.Fraction` arithmetic in the differential test oracle.

## Re-check it

Run the build, multi-kernel proof comparator, and differential test suite from `lean/`:

```sh
lake build
lake comparator --paranoid
python3 tests/run_tests.py
```

On macOS hosts where Linux `bubblewrap` is absent, pass `--inadvisably-no-sandbox` to `lake comparator --paranoid` to execute all six kernels locally while recording `sandboxed = false`.
