# Specification: mcproof Lean Reference Library

`mcproof` in `lean/` is the Lean 4 reference package for the Formal Verification MDE. It defines four pure kernels over natural numbers, arbitrary-precision integers, exact rational pairs, and relative path segments, paired with challenge and proof modules checked by `lake comparator --paranoid`.

## Scope

1. `Mcproof.clampNat lo hi x` moves a natural number `x` into `[lo, hi]`, returning `lo` when `lo > hi`.
2. `Mcproof.bezoutCheck a b x y g` returns `true` if and only if `a * x + b * y = g` over exact integers.
3. `Mcproof.ratLeCross n1 d1 n2 d2` checks `n1 / d1 <= n2 / d2` for positive denominators via exact integer cross-multiplication `n1 * d2 <= n2 * d1`.
4. `Mcproof.cleanSegments segs` accepts a non-empty list of segments only when every segment is non-empty, neither `.` nor `..`, and free of `/` and NUL bytes.

## What must always hold

| Property | Theorem |
| --- | --- |
| When `lo <= hi`, `clampNat lo hi x` lies inside `[lo, hi]`. | `Mcproof.Spec.clampNat_in_range` |
| Every input already in `[lo, hi]` returns unchanged. | `Mcproof.Spec.clampNat_of_mem` |
| `bezoutCheck` returns `true` only when `a * x + b * y = g`. | `Mcproof.Spec.bezoutCheck_sound` |
| `bezoutCheck` returns `true` on every valid integer witness. | `Mcproof.Spec.bezoutCheck_complete` |
| `ratLeCross` certifies `0 < d1`, `0 < d2`, and `n1 * d2 <= n2 * d1`. | `Mcproof.Spec.ratLeCross_sound` |
| Every fraction with `0 < d` satisfies `ratLeCross n d n d = true`. | `Mcproof.Spec.ratLeCross_refl_pos` |
| Accepted segment lists are non-empty and free of `.`, `..`, `/`, and NUL. | `Mcproof.Spec.cleanSegments_safe` |
| Every single safe segment `[s]` is accepted as `some [s]`. | `Mcproof.Spec.cleanSegments_singleton` |

## Oracle

`tests/run_tests.py` compares the `mcproof_lean` executable against an independent Python oracle using exact `int` and `fractions.Fraction` arithmetic across seeded random and mutated inputs.
