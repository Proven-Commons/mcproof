/-
  Domain-general integer/rational RMSNorm Tangent Projection, Multi-Layer 1/L
  Quadratic Radial-Shrinkage Reduction, Orthogonal Adapter Stack Norm Inflation,
  SwiGLU Elementwise Gate Metric, Radial-Null Adjoint Orthogonality, Scalar-Projection
  Subspace-Retention Illusion, and Rational Shrinkage Sandwich Kernels (mcproof v0.2).
  Stock Lean 4.35.0 Init only: zero floats, zero custom axioms, zero escape hatches.
-/

namespace Mcproof.AdapterBounds

/-- Exact integer inner product on aligned lists (`0` on mismatched tails). -/
def vecDot : List Int → List Int → Int
  | [], _ => 0
  | _, [] => 0
  | x :: xs, y :: ys => x * y + vecDot xs ys

/-- Exact squared Euclidean norm `||v||^2 = <v, v>` in `Int`. -/
def vecNormSq (v : List Int) : Int :=
  vecDot v v

/-- Pointwise vector addition in `Int`. -/
def vecAdd : List Int → List Int → List Int
  | [], _ => []
  | _, [] => []
  | x :: xs, y :: ys => (x + y) :: vecAdd xs ys

/-- Pointwise vector subtraction in `Int`. -/
def vecSub : List Int → List Int → List Int
  | [], _ => []
  | _, [] => []
  | x :: xs, y :: ys => (x - y) :: vecSub xs ys

/-- Scalar multiplication `c * v` in `Int`. -/
def vecScale (c : Int) : List Int → List Int
  | [] => []
  | x :: xs => (c * x) :: vecScale c xs

/-- Elementwise (Hadamard / SwiGLU gate) product `g ⊙ v` in `Int`. -/
def vecHadamard : List Int → List Int → List Int
  | [], _ => []
  | _, [] => []
  | g :: gs, v :: vs => (g * v) :: vecHadamard gs vs

/-- Elementwise square `g ⊙ g` (gate metric diagonal `diag(g^2)`). -/
def vecSqDiag (g : List Int) : List Int :=
  vecHadamard g g

/-- Division-free RMSNorm tangent projection `||h||^2 * delta - <h, delta> * h`. -/
def tangentProjScaled (h delta : List Int) : List Int :=
  vecSub (vecScale (vecNormSq h) delta) (vecScale (vecDot h delta) h)

/-- Sum of natural numbers in a list (total adapter impulse across layers). -/
def sumNat : List Nat → Nat
  | [] => 0
  | x :: xs => x + sumNat xs

/-- Sum of squared natural numbers in a list (cumulative quadratic radial shrinkage). -/
def sumSqNat : List Nat → Nat
  | [] => 0
  | x :: xs => x * x + sumSqNat xs

/-- Exact cross-multiplied rational shrinkage sandwich `D2 / (2*(R2 + D2)) <= (qd - qn)/qd <= D2 / (2*R2)`. -/
def shrinkageSandwichCheck (R2 D2 qn qd : Int) : Bool :=
  decide (D2 * qd ≤ 2 * (R2 + D2) * (qd - qn) ∧ 2 * R2 * (qd - qn) ≤ D2 * qd)

end Mcproof.AdapterBounds
