/-
  Core verified definitions for the mcproof Lean 4 reference package.
  Uses stock Lean 4 Init only, with zero floats and zero escape hatches.
-/

import Mcproof.TransitionBounds
import Mcproof.AdapterBounds

namespace Mcproof

/-- Move `x` into the closed natural-number interval `[lo, hi]`. -/
def clampNat (lo hi x : Nat) : Nat :=
  if x < lo then lo
  else if hi < x then hi
  else x

/-- Check exact integer Bezout identity `a * x + b * y = g`. -/
def bezoutCheck (a b x y g : Int) : Bool :=
  decide (a * x + b * y = g)

/-- Division-free rational order check for `n1 / d1 <= n2 / d2` with positive denominators. -/
def ratLeCross (n1 d1 n2 d2 : Int) : Bool :=
  decide (0 < d1 ∧ 0 < d2 ∧ n1 * d2 ≤ n2 * d1)

/-- True when a single path segment is non-empty, not `.` or `..`, and free of `/` and NUL. -/
def isSafeSegment (seg : String) : Bool :=
  decide (seg ≠ "" ∧ seg ≠ "." ∧ seg ≠ ".." ∧ ¬ seg.contains '/' ∧ ¬ seg.contains '\x00')

/-- Validate a pre-tokenized list of relative path segments with no traversal or embedded slash. -/
def cleanSegments (segs : List String) : Option (List String) :=
  match segs with
  | [] => none
  | s :: rest =>
    if (s :: rest).all isSafeSegment then some (s :: rest)
    else none

end Mcproof
