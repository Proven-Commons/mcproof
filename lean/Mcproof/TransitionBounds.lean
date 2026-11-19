/-
  Domain-general discrete state-transition and optimization lower-bound kernels (mcproof v0.2):
  1. Quotient graph homomorphism heuristics (`quotientHeuristic`) over `ValidPath`.
  2. Pre-funded monotone potential repair (`prefundedVal`, `prefundedHeuristic`).
  3. Non-negative operator-counting / Farkas LP dual lower bounds (`dualObjective`, `dualFloorNat`).
  4. Cyclic mode-switch metric (`cyclicSwitchDist`) for multi-mode controllers and schedulers.
  5. Two-species conservation & irreversible-harvest intact-supply potentials (`countTrue`, `intactSupply`).
  6. Time-expanded vertex-split unit-capacity flow & min-cut horizon bounds (`vertexArcFlow`, `tokensInCut`, `horizonCutCapacity`).
  Stock Lean 4.35.0 Init only: zero floats, zero custom axioms, zero escape hatches.
-/

namespace Mcproof.TransitionBounds

/-- Valid finite action sequence in a deterministic partial transition system (`none` = invalid/sink). -/
inductive ValidPath {S A : Type} (step : S → A → Option S) : S → List A → S → Prop where
  | nil (s : S) : ValidPath step s [] s
  | cons {s s' g : S} {a : A} {as : List A} :
      step s a = some s' → ValidPath step s' as g → ValidPath step s (a :: as) g

/-- Pullback of a quotient heuristic `hQ : Q -> Nat` along state projection `pi : S -> Q`. -/
def quotientHeuristic {S Q : Type} (pi : S → Q) (hQ : Q → Nat) (s : S) : Nat :=
  hQ (pi s)

/-- Exact `Nat` pre-funded potential `max(0, hVal - c * rVal)` via truncating natural subtraction. -/
def prefundedVal (hVal c rVal : Nat) : Nat :=
  hVal - c * rVal

/-- State-level pre-funded monotone resource potential `h_hat(s) = h(s) - c * r(s)` in `Nat`. -/
def prefundedHeuristic {S : Type} (h : S → Nat) (c : Nat) (r : S → Nat) (s : S) : Nat :=
  prefundedVal (h s) c (r s)

/-- Weighted operator-counting / landmark inequality `demand <= sum_{a in plan} coeff(a)`. -/
structure DualConstraint (A : Type) where
  weight : Nat
  demand : Nat
  coeff  : A → Nat

/-- Additive sum of an action valuation `f : A -> Nat` along an action sequence `acts`. -/
def planSum {A : Type} (f : A → Nat) : List A → Nat
  | [] => 0
  | a :: as => f a + planSum f as

/-- Scaled dual objective `sum_{i} weight_i * demand_i` across a constraint list. -/
def dualObjective {A : Type} : List (DualConstraint A) → Nat
  | [] => 0
  | c :: cs => c.weight * c.demand + dualObjective cs

/-- Total dual load `sum_{i} weight_i * coeff_i(a)` charged to a single action `a`. -/
def actionDualLoad {A : Type} : List (DualConstraint A) → A → Nat
  | [], _ => 0
  | c :: cs, a => c.weight * c.coeff a + actionDualLoad cs a

/-- Executable integer dual objective over concrete `(weight, demand)` pairs. -/
def dualObjectivePairs : List (Nat × Nat) → Nat
  | [] => 0
  | (w, d) :: rest => w * d + dualObjectivePairs rest

/-- Executable division-free rational floor `floor((sum_i w_i * d_i) / scale)` for positive `scale`. -/
def dualFloorNat (scale : Nat) (pairs : List (Nat × Nat)) : Nat :=
  if scale == 0 then 0 else dualObjectivePairs pairs / scale

/-- Unwrapped cyclic mode-switch step `(b + k - a) % k` for pre-reduced modes `< k`. -/
def cyclicSwitchTax (k a b : Nat) : Nat :=
  (b + k - a) % k

/-- Directed cyclic mode-switch distance `((b % k) + k - (a % k)) % k` on a `k`-mode cycle. -/
def cyclicSwitchDist (k a b : Nat) : Nat :=
  if k == 0 then 0 else cyclicSwitchTax k (a % k) (b % k)

/-- Cardinality of elements in `xs` satisfying boolean predicate `p`. -/
def countTrue {X : Type} (p : X → Bool) : List X → Nat
  | [] => 0
  | x :: xs => (if p x then 1 else 0) + countTrue p xs

/-- Remaining intact supply on tracked site list `I` in state `s`. -/
def intactSupply {S X : Type} (I : List X) (intact : S → X → Bool) (s : S) : Nat :=
  countTrue (intact s) I

/-- Unit vertex-split internal arc flow `v_in(t) -> v_out(t)` (`0` or `1`) induced by occupancy `occ`. -/
def vertexArcFlow {V : Type} (occ : Nat → V → Bool) (t : Nat) (v : V) : Nat :=
  if occ t v then 1 else 0

/-- Number of occupied vertices inside cut `cut_t` across vertex list `vertices`. -/
def tokensInCut {V : Type} (vertices : List V) (occ_t : V → Bool) (cut_t : V → Bool) : Nat :=
  countTrue (fun v => occ_t v && cut_t v) vertices

/-- Cumulative cut capacity `sum_{t = 0}^{T - 1} cutCap(t)` across horizon `[0, T)`. -/
def horizonCutCapacity (cutCap : Nat → Nat) : Nat → Nat
  | 0 => 0
  | t + 1 => horizonCutCapacity cutCap t + cutCap t

/-- Remaining target deficit `max(0, K - mVal)` in `Nat`. -/
def deficitNat (K mVal : Nat) : Nat :=
  K - mVal

/-- Composed quotient-plus-deficit heuristic `hQ(pi(s)) + (K - m(s))` for partitioned action sets. -/
def composedDeficitHeuristic {S Q : Type} (pi : S → Q) (hQ : Q → Nat) (K : Nat) (m : S → Nat) (s : S) : Nat :=
  quotientHeuristic pi hQ s + deficitNat K (m s)

/-- Exact integer ceiling `ceil(num / scale)` for positive `scale` (`0` when `scale == 0`). -/
def ceilDivNat (num scale : Nat) : Nat :=
  if scale == 0 then 0 else (num + scale - 1) / scale

end Mcproof.TransitionBounds
