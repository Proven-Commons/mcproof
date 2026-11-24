# Plane 1 Formal Specification: Siliconcordat Formal Verification MDE (v0.1)

`plane1_formal_spec.md` is the canonical Plane 1 behavioral specification and reference handbook for the Formal Verification Multi-Domain Editing (`formal-verification`) module in `mcproof`. It governs prompt-ceiling evaluation (Arm `B1`), deterministic weight-space compilation in `weft`, and SHA-256 lineage binding in `warp-modeld`.

Proof authors, deterministic verifiers, and language models use this document as the single audited rulebook for formal proof authoring, exact rational checking, and claim-boundary reporting.

Status: active v0.1 Plane 1 specification bound by `spec/lineage.json` and `schemas/zone-manifest.v0.1.json` (`sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca`).

## 1. Three-Tier Trust Firewall and Weight-Class Boundary

Probabilistic model weights never hold permission, approve specifications, or soften external verification gates. Every rule in the Formal Verification MDE belongs to one of three disjoint tiers:

| Tier | Name | Location | Permitted Contents | Prohibited Contents |
| --- | --- | --- | --- | --- |
| Tier 1 | Human Authority (Plane 1) | Signed git commits, `bar/reviewers.toml`, approval records, owner rulings | Specification sign-off, accepting non-standard axioms, contested-preference rulings, release tags, external publication | Model weights, automated overrides, self-approved reviews |
| Tier 2 | Deterministic External Enforcement | Native compilers, Lean 4 kernels, AST auditors, sandboxes, `repo-policy.json` | `lake build`, `lake comparator --paranoid`, `lean4_auditor.py`, `checker_auditor.py`, `bar/check.py`, `f0/scripts/gate.py`, `check_verdicts.py`, `mde guard --code-audit`, `warp-modeld` | Heuristic LLM judges, soft pass thresholds, bare `assert` gates |
| Tier 3 | Revocable Parametric Priors (Plane 2) | Class 1 compiled adapters (`weft-slab/v0.1` and F16 GGUF v3 LoRA) | Six formal authoring reflexes re-derivable with zero byte diff from pinned Plane 1 inputs | Credentials, per-repo git trailer policies, human sign-off authority |

### Class 1 vs Class 2 Weight Artifacts

Siliconcordat separates weight artifacts into two strict classes so stochastic fine-tunes never masquerade as deterministic Plane 2 caches:

1. **Class 1 (`class1_rederivable`, Plane 2 Compiled Adapters):** Closed-form CPU `float64` solvers (`BetaEdit` null-space projection over Hybrid `K0`) quantized deterministically to `int4/int8`, `int4/f16`, or F16 GGUF LoRA.

Re-running the public compiler on the pinned Plane 1 specification, calibration dataset, and base checkpoint produces a zero-byte diff (exact SHA-256 match). Eligible for automated Stage 1 to Stage 4 mounting behind `FixedRadixCertificate`, verifier-owned canaries, and `O(1)` rollback.
2. **Class 2 (`class2_open_recipe_base`, Versioned Base Checkpoints):** Stochastic SFT or RL checkpoints (such as GRPO runs). Treated strictly as new base checkpoints `W_base'` requiring explicit human approval, open training manifests, and full holdout re-verification. Never mounted as Plane 2 SOP adapters.

## 2. Five Hard Vetoes

Every layer from L5 (`mde`) through L2 (`weft`) enforces five non-negotiable vetoes:

1. **Hard Veto 1 (No opaque deltas):** Every Plane 2 adapter must rebuild with zero byte drift from published Plane 1 files, seeded `K0` calibration inputs, and pinned base-model digests using a deterministic CPU `float64` compiler. Any non-empty unpinned training step or non-reproducible tensor fails Stage 1 verification.
2. **Hard Veto 2 (No automatic resolution of contested rules):** When two active domain packs assert incompatible preferences in the same syntactic zone without an explicit Plane 1 `precedence_overrides` entry, routing and compilation halt immediately with `ContestedPreferenceError` or `ContestedLineageError` and escalate to the human owner.
3. **Hard Veto 3 (No closed-weight injection):** Plane 2 adapters mount exclusively on self-hosted open-weight runtimes (`llama-server` behind `warp-modeld`) that verify integer certificates before token generation, expose an `O(1)` kill switch with KV and recurrent-state erase, and append signed ledger receipts. Closed API models use Tier 1 retrieval and Tier 2 external checks only.
4. **Hard Veto 4 (No premature protocol standardization):** All Siliconcordat slot, zone, and lineage extensions travel inside vendor-namespaced `_meta` under the exact key `gg.siliconcordat/mde`. Unnamespaced top-level protocol mutations are rejected.
5. **Hard Veto 5 (Plane 1 is where the person lives):** Human-authored Plane 1 files are authoritative. Modifying even one byte of `spec/plane1_formal_spec.md` or any tracked schema invalidates `plane1_spec_sha256` and `corpus_tree_sha256`, triggers `stale_lineage`, and automatically unloads active adapters until recompiled.

## 3. Pinned Plane 1 Source and Deterministic Oracle Catalog

All ten upstream repositories and four Siliconcordat stack layers are pinned by exact 40-character commit hashes. Each external URL appears once in this catalog as the canonical upstream reference:

| Repository | Pinned 40-Char Commit SHA | Canonical Upstream Link | Role in Formal Verification MDE |
| --- | --- | --- | --- |
| `ahrazzle/soko` | `3165e20e7a16c0035cab2fd01231e78e4e1d7f86` | [soko repository](https://github.com/ahrazzle/soko) | `soko_mcp/lean4_auditor.py`, `checker_auditor.py`, `integrity.py`, `evidence.py`, and `docs/verified-systems-loop.md` |
| `Proven-Commons/mission` | `7b22e542f0db0f3013ab1439cf5d1947676a5083` | [mission repository](https://github.com/Proven-Commons/mission) | `playbook/verified-bar.md` (Verified Bar version 2), `bar/check.py`, `bar/reviewers.toml`, and `WeakStatement.lean` |
| `Foundation-0/f0` | `9a37134750174339c53121939838ce62ab8af630` | [f0 repository](https://github.com/Foundation-0/f0) | `scripts/gate.py` staging gate and `tests/run_gate_corruptions.py` planted-corruption suite |
| `Foundation-0/.github` | `81f83c38918382b4ca142b81debd3cc5ccf61d3a` | [Foundation-0 standard](https://github.com/Foundation-0/.github) | `REPO-STANDARD.md` defining `PROVEN`, `VERIFIED`, `KNOWN`, and `CONJECTURE` claim labels and locked checkers |
| `Foundation-0/formal-claims-audit` | `bacf05953c10bf5105fa1209a127392d395e2f92` | [formal-claims-audit repository](https://github.com/Foundation-0/formal-claims-audit) | `scripts/check_verdicts.py` structural validator requiring 40-char `source_commit` and unique JSON keys |
| `Foundation-0/finite-state-proofs` | `9eeb3da2cdd6ba6b100ac24d23b32c369c0db8ec` | [finite-state-proofs repository](https://github.com/Foundation-0/finite-state-proofs) | `verify.py` exact integer nilpotent residual-chain certificate verifier |
| `Foundation-0/proven-commons` | `903c1858be856776de21675cf5c4e26fb9eebcdf` | [proven-commons anthology](https://github.com/Foundation-0/proven-commons) | 18-package Lean `v4.35.0` workspace anthology and `scripts/audit.py` `collectAxioms` harness |
| `Foundation-0/incentre-lattices` | `2d374fff2a59cc9331566733043a4bb25c1040bf` | [incentre-lattices repository](https://github.com/Foundation-0/incentre-lattices) | Published open-research reference separating `PROVEN` theorems from `VERIFIED` finite path checks |
| `Moissanite-Labs/weft-eido` | `be27665255d9aa2553060d275f7d1b1b3306c703` | [weft-eido repository](https://github.com/Moissanite-Labs/weft-eido) | Phase 6 UI design pack composed alongside `formal-verification` under `data-eido-skip` protection |
| `Moissanite-Labs/siliquant` | `67b29a4e18cd5d93e1f3701a34030f2e089e7312` | [siliquant repository](https://github.com/Moissanite-Labs/siliquant) | Phase 3 top-10 `ffn_down` loud-column outlier protection and noise-imatrix quantization reference |
| `siliconcordat/mde` | `52ce0178854a67490eb718544961ba6cff710f22` | [siliconcordat mde](https://github.com/siliconcordat/mde) | L5 CST broker, `zone-manifest/v0.1`, `mde guard --code-audit`, and `mde integrity` |
| `siliconcordat/exo` | `9d52aa1f28272753ddf83dbe02864d05989b74d2` | [siliconcordat exo](https://github.com/siliconcordat/exo) | L4 `ZoneRouter`, `RepoPolicy`, exact-byte approval gates, and 7-hazard interference suite |
| `siliconcordat/warp` | `28f56549a8bb59b723281afa31831df0824e7dec` | [siliconcordat warp](https://github.com/siliconcordat/warp) | L3 `warp-modeld` 4-stage fail-closed loader and multi-bank `O(1)` rollback |
| `siliconcordat/weft` | `3d66f07e5ee67863a7e6c1029e7473c9c8c11b08` | [siliconcordat weft](https://github.com/siliconcordat/weft) | L2 deterministic CPU `float64` `BetaEdit` compiler, `weft-slab/v0.1`, and `FixedRadixCertificate` |

### Closed-Loop Verification Operations

Candidate generation and candidate acceptance stay strictly separated. A language model, heuristic solver, or human author proposes a candidate artifact. Deterministic Tier 2 checkers decide what exact claim that artifact supports:

| Operation | Required Deterministic Output | Invalid Inference Blocked by Tier 2 |
| --- | --- | --- |
| Capture | Normalized problem input, timestamp, content SHA-256, attribution | Assuming a parsed transcription matches upstream bytes without blob verification |
| Specify | State space, preconditions, transition relation, target property, scope limits | Treating type-correct definitions as proof of real-world semantics |
| Propose | Candidate proof or witness, generator identifier, search bounds, random seed | Treating failed heuristic search as an impossibility proof |
| Replay | Step-by-step state verification, boundary survival, exact termination check | Calling a feasible witness optimal without a lower-bound proof |
| Compare | Dual-oracle results across distinct AST skeletons and first divergence witness | Calling two renamed copies of one algorithm independent verification |
| Prove | Kernel-checked theorem, `comparator.json` match, standard-axiom-only report | Calling `lake build` exit 0 a complete check without `collectAxioms` and `comparator` |
| Review | Non-author human review pinned to `spec_hash` over spec, code list, tests, and page | Carrying an old approval forward after any covered file changes |

## 4. Reflex 1: Adversarial `WeakStatement` Vacuous-Hypothesis and Tautology Hunting

A machine-checked theorem is only as strong as its statement. Lean's kernel verifies that the proof term inhabits the stated type, not that the stated type captures the informal claim.

Every proof author and reviewer must try to break each proposed theorem statement by constructing a buggy or trivial implementation that still satisfies the theorem, or by checking whether the hypotheses are unsatisfiable.

### Empirical Origin: The Tar Extraction Gate Audit

In the Proven Commons `tar` pilot audit (`2026-10-24`), every automated check passed: zero `sorry`, standard axioms (`propext`, `Classical.choice`, `Quot.sound`), 16 differential tests green, and all six Lean 4.35.0 kernels accepting the build.

Yet the headline theorem `extractAll_safe` stated only that emitted path component lists excluded `""`, `"."`, and `".."`, and were non-empty. It omitted the condition that individual components contain no embedded `'/'` or NUL character.

Because the CLI joined components with `String.intercalate "/"`, a broken gate `badGate` that never split raw archive names on `'/'` satisfied the exact theorem statement while emitting `out/../../etc/passwd`.

The strengthened specification (`Contained.lean` and `Mcproof.cleanSegments`) closes that gap by:

1. Rejecting any segment containing `'/'` or `'\x00'` inside the decidable predicate `isSafeSegment`.
2. Pairing the safety theorem (`cleanSegments_safe`: accepted lists are non-empty and every element excludes `""`, `"."`, `".."`, `'/'`, and `'\x00'`) with a usefulness theorem (`cleanSegments_singleton`: every single valid segment `[s]` returns `some [s]`), so a trivial `fun _ => none` implementation fails immediately.

### Five Mandatory Statement-Audit Checks

Before writing tactics for any Lean 4 theorem or accepting any formal specification, apply all five checks:

1. **Non-vacuity of hypotheses (`SAT` witness check):** Exhibit at least one concrete input tuple satisfying all hypotheses `h1, h2, ..., hk` simultaneously. If `(n : Nat) (h : n < 0)`, `(h1 : x < y) (h2 : y <= x)`, `(h : False)`, or `(h1 : P) (h2 : Not P)` appears in the binder list, `False.elim` or `omega` proves any conclusion vacuously.

`mcproof` flags `VACUOUS_FALSE_HYPOTHESIS`, `VACUOUS_NAT_LT_ZERO`, `VACUOUS_SELF_CONTRADICTION`, and `VACUOUS_CONTRADICTORY_HYPOTHESES`.
2. **Non-triviality of conclusion:** Never state `: True` or a reflexive identity `f x = f x` that ignores the specification's invariants. `mcproof` flags `VACUOUS_TRUE_CONCLUSION`.
3. **Adversarial wrong-program test (Safety + Usefulness pairing):** Every safety bound (`output_is_valid`) holds trivially for a function that always returns `none` or a constant boundary value `lo`.

Pair every safety theorem with a completeness or identity-on-valid-input theorem (`clampNat_of_mem`, `bezoutCheck_complete`, `ratLeCross_refl_pos`, `cleanSegments_singleton`) that any constant or always-rejecting stub fails.
4. **Type-coercion and truncation audit (`Nat` subtraction and integer division):** In Lean 4, natural-number subtraction `a - b` truncates to `0` whenever `a <= b`, and division by zero returns `0`.

Writing `a - b = c` on `Nat` without `b <= a` states `0 = 0` on underflow! State subtraction identities over `Int`, or include explicit guard `h : b <= a` accompanied by a non-empty witness showing `b <= a` is reachable.
5. **Instance and helper-definition audit:** `lake comparator` compares theorem types between `Spec` and `Proofs`. If both modules import a user-defined `LE` instance or helper predicate that defines `x <= y` as `True`, both sides match syntactically while proving nothing. Keep all specification predicates inside audited `Spec` files or stock `Init` types (`Nat`, `Int`, `Bool`, `List`, `String`).

### Catalog of Weak-Statement Traps and Strengthened Replacements

#### Trap 1: Vacuous `Nat` Underflow and Impossible Bounds

```lean
-- DEFECTIVE (vacuous hypothesis `n < 0` on `Nat`, plus truncated `Nat` subtraction):
theorem defective_nat_sub (n : Nat) (h : n < 0) : n - 10 = n := by
  omega

-- STRENGTHENED (inhabited domain `10 <= n` over `Nat`, plus exact `Int` counterpart):
theorem sound_nat_sub_add (n : Nat) (h : 10 ≤ n) : (n - 10) + 10 = n := by
  omega

theorem sound_nat_sub_witness : ∃ n : Nat, 10 ≤ n ∧ (n - 10) + 10 = n :=
  ⟨14, by omega, by omega⟩
```

#### Trap 2: Safety Theorem Satisfied by Always-None Validator

```lean
-- DEFECTIVE: `alwaysReject` satisfies `validator_sound` vacuously because `none = some out` is False!
def alwaysReject (_xs : List Int) : Option (List Int) := none

theorem defective_validator_sound (xs out : List Int) :
    alwaysReject xs = some out → ∀ x ∈ out, 0 ≤ x := by
  intro h
  cases h

-- STRENGTHENED: pair soundness with completeness on non-negative inputs!
def filterNonNegCheck (xs : List Int) : Option (List Int) :=
  if xs.all (fun x => decide (0 ≤ x)) then some xs else none

theorem filterNonNegCheck_sound (xs out : List Int) :
    filterNonNegCheck xs = some out → out = xs ∧ ∀ x ∈ out, 0 ≤ x := by
  unfold filterNonNegCheck
  by_cases hall : xs.all (fun x => decide (0 ≤ x)) = true
  · simp [hall]
    intro h
    subst h
    refine ⟨rfl, ?_⟩
    intro x hx
    exact of_decide_eq_true (List.all_eq_true.mp hall x hx)
  · simp [hall]

theorem filterNonNegCheck_complete (xs : List Int) (h : ∀ x ∈ xs, 0 ≤ x) :
    filterNonNegCheck xs = some xs := by
  unfold filterNonNegCheck
  have hall : xs.all (fun x => decide (0 ≤ x)) = true := by
    apply List.all_eq_true.mpr
    intro x hx
    exact decide_eq_true (h x hx)
  simp [hall]
```

#### Trap 3: Premature Modulo Reduction Inside Divisibility Specification

```lean
-- DEFECTIVE: `a % 0 = a` in Lean 4, and claiming `gcd a b = 1` from `a * x + b * y = 1`
-- only checks one direction unless both divisibility properties of a common divisor are stated.
def dividesInt (d n : Int) : Prop := ∃ k : Int, n = d * k

-- STRENGTHENED: prove directly from Bezout identity `a * x + b * y = 1` that ANY common
-- divisor `d` of `a` and `b` divides `1`, with zero reliance on division-by-zero conventions!
theorem bezout_coprime_divisor (a b x y d : Int)
    (hbez : a * x + b * y = 1)
    (hda : dividesInt d a)
    (hdb : dividesInt d b) :
    dividesInt d 1 := by
  rcases hda with ⟨ka, ha⟩
  rcases hdb with ⟨kb, hb⟩
  refine ⟨ka * x + kb * y, ?_⟩
  have h1 : d * (ka * x + kb * y) = (d * ka) * x + (d * kb) * y := by
    rw [Int.mul_add, Int.mul_assoc, Int.mul_assoc]
  rw [h1, ← ha, ← hb, hbez]
```

#### Trap 4: Contradictory Interval or Order Hypotheses

```lean
-- DEFECTIVE: assumes `hi < lo` and `lo <= x` and `x <= hi`, which is empty!
theorem defective_interval_trap (lo hi x : Int)
    (hbad : hi < lo) (h1 : lo ≤ x) (h2 : x ≤ hi) :
    x = 42 := by
  omega

-- STRENGTHENED: require `lo <= hi`, prove midpoint / sum bounds `(2 * lo <= lo + hi ∧ lo + hi <= 2 * hi)`,
-- and include an inhabitance theorem confirming the preconditions hold on concrete inputs.
theorem sound_interval_double_sum (lo hi : Int) (h : lo ≤ hi) :
    2 * lo ≤ lo + hi ∧ lo + hi ≤ 2 * hi := by
  omega

theorem sound_interval_inhabited : ∃ lo hi : Int, lo ≤ hi ∧ 2 * lo ≤ lo + hi :=
  ⟨-5, 7, by omega, by omega⟩
```

#### Trap 5: Finite-State Invariant Without Reachability From Initial State

```lean
-- DEFECTIVE: proves invariant holds if state is already negative, which never occurs or says nothing
-- about transitions from the initial configuration.
structure CounterState where
  issued : Nat
  completed : Nat
deriving DecidableEq, Repr

def initCounter : CounterState := { issued := 0, completed := 0 }

def stepIssue (s : CounterState) : CounterState :=
  { s with issued := s.issued + 1 }

def stepComplete (s : CounterState) : CounterState :=
  if s.completed < s.issued then { s with completed := s.completed + 1 } else s

def counterInv (s : CounterState) : Prop :=
  s.completed ≤ s.issued

-- STRENGTHENED: prove BOTH base case (`initCounter`) AND inductive preservation across every action,
-- PLUS progress showing `stepIssue` strictly advances `issued`!
theorem counterInv_init : counterInv initCounter := by
  unfold counterInv initCounter
  dsimp
  omega

theorem counterInv_stepIssue (s : CounterState) (h : counterInv s) :
    counterInv (stepIssue s) := by
  unfold counterInv stepIssue at *
  dsimp
  omega

theorem counterInv_stepComplete (s : CounterState) (h : counterInv s) :
    counterInv (stepComplete s) := by
  unfold counterInv stepComplete at *
  split
  · dsimp
    omega
  · exact h

theorem stepIssue_progress (s : CounterState) :
    (stepIssue s).issued = s.issued + 1 := rfl
```

## 5. Reflex 2: Dual-Oracle Distinct-Skeleton Verification

When a computational claim is checked in Python rather than proved universally in Lean 4, a single script checking its own output is vulnerable to shared-bug blindness. Copying the generator function into `verify.py` and renaming local variables produces two identical syntax trees that agree on every bug.

### How `soko_mcp/checker_auditor.py` Detects Mirrored Checkers

`checker_auditor.py` parses both `spec` (or generator) and `impl` (verifier) with Python's `ast` module, strips module and function docstrings, preserves built-in mathematical primitives (`int`, `Fraction`, `abs`, `all`, `any`, `divmod`, `len`, `max`, `min`, `pow`, `range`, `sum`, `tuple`, `ValueError`), canonicalizes all other function, argument, and local variable identifiers in traversal order (`v0`, `v1`, `v2`, ...), and hashes `ast.dump(norm_tree, include_attributes=False)` with SHA-256.

If `spec_skeleton_sha256 == impl_skeleton_sha256`, `audit_dual_checkers` returns `verdict = "FAIL"`, `epistemic_status = "REJECTED_CHECKER_HAZARD"`, and `distinct_alpha_skeleton = False`.

### Four Empirical Python Verifier Hazards Blocked by Tier 2

`checker_auditor.py` and `mde guard --code-audit` jointly scan every Python verifier and reject four empirical failure modes:

1. **`IDENTICAL_ALPHA_SKELETON`:** Generator and verifier use the same algorithm up to variable renaming.

Fix: generate a constructive witness (such as an extended Euclidean `(x, y)` pair, a Farkas dual vector `y`, a graph coloring map, a permutation inverse, or a polynomial quotient-remainder pair `(q, r)`) and verify the algebraic certificate equations directly instead of re-running search or elimination.
2. **`OPTIMISTIC_TRUE_DEFAULT_F01`:** Initializing `verified = True`, `valid = True`, `ok = True`, `passed = True`, or `match = True` before `if` branches. If a guard condition is skipped or mis-indented, the function fails open and returns `True`.

Fix: compute each boolean condition positively (`cond_a = ...`, `cond_b = ...`) and return `cond_a and cond_b`, or raise `ValueError` on the first violated equation and return `True` only at the final line after every check succeeds.
3. **`VACUOUS_CONSTANT_TRUE_RETURN` and `VACUOUS_ASSERT_TRUE`:** Stub functions whose body is `return True` or `assert True`. Both static AST auditing and the `>= 80%` planted-bug mutation suite reject them immediately.
4. **`bare_assert`, `bare_except`, `silent_except_swallow`, and `MUTABLE_GLOBAL_SCOPE`:**
   - Running Python with `-O` (`PYTHONOPTIMIZE=1`) strips every `assert` statement from bytecode before execution! Never use `assert` inside a verifier. Always write `if not condition: raise ValueError("explicit reason")` or return `False`.
   - Never write bare `except:` or `except Exception: pass` / `except ValueError: ...`. Swallowing exceptions turns solver crashes into silent passes.
   - Never use `global` or `nonlocal` state accumulators inside verifiers. every call must be a pure function of its explicit arguments.

### Canonical Dual-Oracle Certificate Patterns

Use constructive certificate checking so the generator and the verifier have structurally distinct algorithms (`O(n^3)` search/solve vs `O(n^2)` or `O(n)` algebraic verification):

#### Pattern B-1: Extended GCD / Linear Diophantine Certificate (`a * x + b * y = g`)

Generator runs iterative extended Euclidean division (`divmod`). Independent verifier checks certificate equations without running `gcd` loops:

1. `g > 0` (or `a == 0 and b == 0 and g == 0`)
2. Linear combination holds: `a * x + b * y == g`
3. Divisibility holds: `a % g == 0 and b % g == 0`
4. Minimality holds automatically! Because `a * x + b * y == g` implies every common divisor of `a` and `b` divides `g`, and `g` divides both `a` and `b` with `g > 0`, `g` is mathematically forced to equal `gcd(a, b)` with zero Euclidean loop in the verifier!

```python
from __future__ import annotations


def generate_bezout_certificate(a: int, b: int) -> dict[str, int]:
    """Iterative extended Euclidean algorithm producing witness (g, x, y)."""
    if type(a) is not int or type(b) is not int:
        raise TypeError("inputs must be exact integers")
    if a == 0 and b == 0:
        return {"a": 0, "b": 0, "g": 0, "x": 0, "y": 0}
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t
    if old_r < 0:
        old_r = -old_r
        old_s = -old_s
        old_t = -old_t
    return {"a": a, "b": b, "g": old_r, "x": old_s, "y": old_t}


def verify(cert: dict[str, int]) -> bool:
    """Independent algebraic Bezout certificate checker (distinct AST skeleton, zero loops)."""
    required = ("a", "b", "g", "x", "y")
    for key in required:
        if key not in cert or type(cert[key]) is not int:
            return False
    a, b, g, x, y = cert["a"], cert["b"], cert["g"], cert["x"], cert["y"]
    if a == 0 and b == 0:
        return g == 0 and x == 0 and y == 0
    if g <= 0:
        return False
    if a * x + b * y != g:
        return False
    if a % g != 0 or b % g != 0:
        return False
    return True
```

#### Pattern B-2: Exact Rational Linear System & Farkas Infeasibility Certificate (`Ax = b`)

When solving `A x = b` over `Q` (represented as integer numerator/denominator pairs or `fractions.Fraction`):
- If feasible, the generator runs Gaussian elimination to emit `x: list[tuple[int, int]]`. the verifier substitutes `x` directly into each row dot product using `Fraction(num, den)` and checks exact equality with `b`.
- If infeasible, the generator emits a Farkas dual vector `y` such that `y^T A == 0` and `y^T b != 0`. the verifier checks `all(sum(y[i] * A[i][j] for i in range(m)) == 0 for j in range(n))` and `sum(y[i] * b[i] for i in range(m)) != 0` in `O(m * n)` exact rational operations without ever running Gaussian elimination!

```python
from __future__ import annotations
from fractions import Fraction


def parse_rat(pair: list[int] | tuple[int, int]) -> Fraction:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValueError("rational entry must be a [num, den] pair")
    num, den = pair[0], pair[1]
    if type(num) is not int or type(den) is not int or den == 0:
        raise ValueError("rational num/den must be exact ints with non-zero den")
    return Fraction(num, den)


def verify_linear_system_certificate(
    matrix_a: list[list[list[int]]],
    vec_b: list[list[int]],
    certificate: dict[str, object],
) -> bool:
    """Verify either a primal solution x (Ax = b) or a Farkas dual witness y (y^T A = 0, y^T b != 0)."""
    if not matrix_a or not matrix_a[0] or len(matrix_a) != len(vec_b):
        return False
    m_rows = len(matrix_a)
    n_cols = len(matrix_a[0])
    if any(len(row) != n_cols for row in matrix_a):
        return False

    a_rat = [[parse_rat(cell) for cell in row] for row in matrix_a]
    b_rat = [parse_rat(item) for item in vec_b]
    status = certificate.get("status")

    if status == "feasible":
        raw_x = certificate.get("x")
        if not isinstance(raw_x, list) or len(raw_x) != n_cols:
            return False
        x_rat = [parse_rat(item) for item in raw_x]
        for i in range(m_rows):
            row_dot = sum((a_rat[i][j] * x_rat[j] for j in range(n_cols)), Fraction(0, 1))
            if row_dot != b_rat[i]:
                return False
        return True

    if status == "infeasible":
        raw_y = certificate.get("farkas_y")
        if not isinstance(raw_y, list) or len(raw_y) != m_rows:
            return False
        y_rat = [parse_rat(item) for item in raw_y]
        for j in range(n_cols):
            col_dot = sum((y_rat[i] * a_rat[i][j] for i in range(m_rows)), Fraction(0, 1))
            if col_dot != Fraction(0, 1):
                return False
        rhs_dot = sum((y_rat[i] * b_rat[i] for i in range(m_rows)), Fraction(0, 1))
        return rhs_dot != Fraction(0, 1)

    return False
```

#### Pattern B-3: Bipartite Graph 2-Coloring vs Odd-Cycle Certificate

A finite graph `G = (V, E)` is bipartite if and only if it has no odd cycle:
- Generator runs breadth-first search to construct either a `coloring` (`{v: 0 | 1}`) or an odd cycle `[v_0, v_1, ..., v_{2k}]`.
- Independent verifier checks edge endpoints directly:
  - If `bipartite == True`, verifies every vertex in `0..n-1` has color `0` or `1`, and every undirected edge `(u, v)` satisfies `color[u] != color[v]`.
  - If `bipartite == False`, verifies `cycle` has odd length `>= 3`, distinct vertices, and every consecutive pair `(cycle[i], cycle[(i + 1) % L])` belongs to `E`!

```python
from __future__ import annotations


def verify_bipartite_certificate(
    num_vertices: int,
    edges: list[tuple[int, int]],
    cert: dict[str, object],
) -> bool:
    """Verify a 2-coloring witness or an odd-cycle obstruction without graph search."""
    if type(num_vertices) is not int or num_vertices < 0:
        return False
    edge_set: set[tuple[int, int]] = set()
    for pair in edges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        u, v = pair[0], pair[1]
        if type(u) is not int or type(v) is not int:
            return False
        if not (0 <= u < num_vertices and 0 <= v < num_vertices):
            return False
        edge_set.add((u, v))
        edge_set.add((v, u))

    is_bip = cert.get("bipartite")
    if is_bip is True:
        colors = cert.get("colors")
        if not isinstance(colors, list) or len(colors) != num_vertices:
            return False
        if any(type(c) is not int or c not in (0, 1) for c in colors):
            return False
        for u, v in edges:
            if u == v or colors[u] == colors[v]:
                return False
        return True

    if is_bip is False:
        cycle = cert.get("odd_cycle")
        if not isinstance(cycle, list) or len(cycle) < 3 or len(cycle) % 2 == 0:
            return False
        if any(type(v) is not int or not (0 <= v < num_vertices) for v in cycle):
            return False
        if len(set(cycle)) != len(cycle):
            return False
        k = len(cycle)
        for idx in range(k):
            nxt = cycle[(idx + 1) % k]
            if (cycle[idx], nxt) not in edge_set:
                return False
        return True

    return False
```

#### Pattern B-4: Finite-State Nilpotent Residual-Chain Certificate

Modeled on `Foundation-0/finite-state-proofs/verify.py`: to certify that a transfer-matrix sequence `a(n) = u^T T^n v_0` satisfies a linear recurrence `q(T) = T^d - c_1 T^(d-1) - ...

- c_d I` for all `n >= start` without floating-point eigenvalues, compute the exact integer residual vector `r_0 = T^d v_0 - sum_{k=1}^d c_k T^(d-k) v_0` and verify that `T^m r_0 == 0` (the exact zero vector in `Z^D`) for some `m <= D`, while checking initial scalar outputs up to `start + m`! Once `T^m r_0` hits the exact integer zero vector, `T^k r_0 == 0` holds for EVERY `k >= m` to infinity!

## 6. Reflex 3: Exact `int` and `fractions.Fraction` Zero-Float Arithmetic

IEEE-754 binary64 floating-point numbers (`float`) round `1/10 + 2/10` to `0.30000000000000004`, lose integer precision above `2^53 = 9,007,199,254,740,992`, and change summation results under SIMD re-association.

Inside exact mathematical verifiers, rational linear algebra checkers, combinatorial counters, Markov stationary-distribution auditors, and certificate gates, floating-point arithmetic is strictly forbidden.

### Static and Runtime Enforcement Rules

1. **Zero float literals (`FLOAT_LITERAL_IN_EXACT_CHECKER`):** Never write `0.0`, `1.0`, `0.5`, `1e-9`, or `math.pi` in an exact checker. Use `0`, `1`, `Fraction(1, 2)`, or exact symbolic/algebraic representations (such as `Q(sqrt(2))` pairs `(a, b)` representing `a + b * sqrt(2)`!).
2. **Zero true division `/` (`FLOAT_DIVISION_IN_EXACT_CHECKER`):** In Python 3, `a / b` on `int` produces a `float`! Even `Fraction(1, 3) / Fraction(2, 3)` triggers the AST `ast.Div` rule in `checker_auditor.py`!
   - For integer quotient and remainder, use `q, r = divmod(a, b)` or `a // b` and `a % b` (verifying `b != 0` first).
   - For exact rational division of `x: Fraction` by non-zero `y: Fraction`, construct `Fraction(x.numerator * y.denominator, x.denominator * y.numerator)` or multiply by `Fraction(y.denominator, y.numerator)`! That uses `ast.Mult` (`*`) exclusively, preserving 100% exactness and passing `checker_auditor.py` with zero `ast.Div` findings!
3. **Zero `float(...)` calls (`FLOAT_COERCION_CALL`):** Never coerce `int`, `Fraction`, or `Decimal` to `float` for comparisons. Compare `Fraction` objects directly (`p == q`, `p <= q`) or cross-multiply integer numerators and positive denominators (`n1 * d2 <= n2 * d1`).
4. **Strict boolean vs integer type check (`type(x) is int`):** In Python, `bool` is a subclass of `int` (`isinstance(True, int) == True` and `True == 1`). Always validate exact integer inputs with `type(x) is int` (or `isinstance(x, int) and not isinstance(x, bool)`), matching `weft/certificate.py` and `soko_mcp/evidence.py`.
5. **Execution under `python3 -O -B -W error`:** Every verifier runs with optimization `-O` (stripping `assert`), `-B` (no bytecode cache), `-W error` (all warnings fatal), and `PYTHONHASHSEED=0`.

### Reference Library of Float-Free Exact Mathematical Checkers

#### Exact Algorithm 1: Division-Free Bareiss Integer Determinant and Exact Inverse Witness

Computing determinants via naive `Fraction` pivoting works, and Bareiss fraction-free integer elimination computes `det(M)` for `M in Z^(n x n)` using ONLY exact `int` multiplication and exact `//` floor division (where every intermediate division is mathematically guaranteed to have zero remainder!). Better still, for dual-oracle verification of an invertible matrix `A` and determinant `d`:
- Generator computes `det(A)` and adjugate matrix `Adj(A)` (where `A * Adj(A) = det(A) * I_n`).
- When `det(A) != 0`, checking `A @ Adj(A) == det(A) * I_n` certifies invertibility, and pairing Bareiss elimination with adjugate or LU-factorization over `Fraction` gives two distinct skeletons!

```python
from __future__ import annotations
from fractions import Fraction


def rat_div(x: Fraction, y: Fraction) -> Fraction:
    """Exact rational division without Python '/' operator (avoids ast.Div)."""
    if y.numerator == 0:
        raise ZeroDivisionError("division by zero Fraction")
    return Fraction(x.numerator * y.denominator, x.denominator * y.numerator)


def bareiss_determinant_int(matrix: list[list[int]]) -> int:
    """Exact integer determinant via Bareiss algorithm (zero floats, zero ast.Div)."""
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise ValueError("matrix must be non-empty square")
    for row in matrix:
        for val in row:
            if type(val) is not int:
                raise TypeError("matrix entries must be strict int")

    grid = [list(row) for row in matrix]
    sign = 1
    prev_pivot = 1

    for k in range(n - 1):
        if grid[k][k] == 0:
            swap_row = -1
            for r in range(k + 1, n):
                if grid[r][k] != 0:
                    swap_row = r
                    break
            if swap_row == -1:
                return 0
            grid[k], grid[swap_row] = grid[swap_row], grid[k]
            sign = -sign

        pivot = grid[k][k]
        for i in range(k + 1, n):
            for j in range(k + 1, n):
                num = grid[i][j] * pivot - grid[i][k] * grid[k][j]
                q, rem = divmod(num, prev_pivot)
                if rem != 0:
                    raise RuntimeError("Bareiss exact divisibility invariant violated")
                grid[i][j] = q
        prev_pivot = pivot

    return sign * grid[n - 1][n - 1]
```

#### Exact Algorithm 2: Closed Rational Interval Arithmetic (`[lo, hi]` over `Fraction`)

Interval verifiers certify nonlinear inequalities on bounded domains without floating-point outward-rounding bugs:

```python
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class RatInterval:
    lo: Fraction
    hi: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.lo, Fraction) or not isinstance(self.hi, Fraction):
            raise TypeError("bounds must be Fraction instances")
        if self.lo > self.hi:
            raise ValueError(f"empty interval: {self.lo} > {self.hi}")

    def add(self, other: "RatInterval") -> "RatInterval":
        return RatInterval(self.lo + other.lo, self.hi + other.hi)

    def sub(self, other: "RatInterval") -> "RatInterval":
        return RatInterval(self.lo - other.hi, self.hi - other.lo)

    def mul(self, other: "RatInterval") -> "RatInterval":
        products = (
            self.lo * other.lo,
            self.lo * other.hi,
            self.hi * other.lo,
            self.hi * other.hi,
        )
        return RatInterval(min(products), max(products))

    def contains(self, x: Fraction) -> bool:
        return self.lo <= x <= self.hi
```

#### Exact Algorithm 3: Discrete-Time Markov Chain Stationary Distribution Checker

For a row-stochastic transition matrix `P` over `Q` (`P[i][j] >= 0`, `sum_j P[i][j] == 1`) and candidate stationary vector `pi`:
- Verifier checks without power iteration or floating-point eigensolvers:
  1. `P` is `n x n`, every entry `P[i][j] >= Fraction(0, 1)`, and every row sums to `Fraction(1, 1)`.
  2. `pi` has length `n`, every `pi[i] >= Fraction(0, 1)`, and `sum(pi) == Fraction(1, 1)`.
  3. Global balance holds exactly: for every state `j` in `0..n-1`, `sum(pi[i] * P[i][j] for i in range(n)) == pi[j]`.

```python
from __future__ import annotations
from fractions import Fraction


def verify_markov_stationary(
    trans_num_den: list[list[tuple[int, int]]],
    pi_num_den: list[tuple[int, int]],
) -> bool:
    """Verify exact rational stationary distribution pi * P == pi with zero floats."""
    n = len(trans_num_den)
    if n == 0 or len(pi_num_den) != n:
        return False

    p_mat: list[list[Fraction]] = []
    for row in trans_num_den:
        if len(row) != n:
            return False
        r_list: list[Fraction] = []
        for num, den in row:
            if type(num) is not int or type(den) is not int or den <= 0:
                return False
            val = Fraction(num, den)
            if val < Fraction(0, 1):
                return False
            r_list.append(val)
        if sum(r_list, Fraction(0, 1)) != Fraction(1, 1):
            return False
        p_mat.append(r_list)

    pi_vec: list[Fraction] = []
    for num, den in pi_num_den:
        if type(num) is not int or type(den) is not int or den <= 0:
            return False
        val = Fraction(num, den)
        if val < Fraction(0, 1):
            return False
        pi_vec.append(val)

    if sum(pi_vec, Fraction(0, 1)) != Fraction(1, 1):
        return False

    for j in range(n):
        lhs = sum((pi_vec[i] * p_mat[i][j] for i in range(n)), Fraction(0, 1))
        if lhs != pi_vec[j]:
            return False
    return True
```

#### Exact Algorithm 4: Quadratic Extension Field `Q(sqrt(d))` Arithmetic for Lattice Geometry

Many geometry and incentre-lattice proofs (`Foundation-0/incentre-lattices`) involve `sqrt(2)` or `sqrt(3)` (such as `gamma = sqrt(2) - 1` or coordinates `(2 - sqrt(2)) / 3`). Never approximate `math.sqrt(2)` with IEEE-754 floats! Represent elements of `Q(sqrt(d))` (for square-free integer `d`) as exact pairs `(a, b)` of `Fraction` representing `a + b * sqrt(d)`:
- Equality: `(a1, b1) == (a2, b2)` iff `a1 == a2 and b1 == b2` (since `sqrt(d)` is irrational for non-square `d`).
- Addition: `(a1 + a2, b1 + b2)`.
- Multiplication: `(a1 * a2 + d * b1 * b2, a1 * b2 + a2 * b1)`.
- Sign test (`a + b * sqrt(d) >= 0` for `d > 0`): exact case split on signs of `a` and `b` using `a * a` vs `d * b * b`!
  - If `a >= 0 and b >= 0`: `True`.
  - If `a < 0 and b <= 0`: `False` (unless both `0`).
  - If `a >= 0 and b < 0`: `a * a >= d * b * b`.
  - If `a < 0 and b > 0`: `d * b * b >= a * a`.
  Zero square roots, zero floats, 100% exact algebraic decision procedure!

#### Exact Algorithm 5: Polynomial Euclidean Division and Root Multiplicity over `Q[x]`

Represent a polynomial `P(x) = c_0 + c_1 x + ... + c_k x^k` as a canonical list of `Fraction` coefficients trimming trailing zeros:
- To verify `A(x) = B(x) * Q(x) + R(x)` without performing polynomial long division inside the verifier:
  1. Check `B` is non-zero (`len(B) > 0`).
  2. Check degree bound: `len(R) == 0` or `len(R) < len(B)`.
  3. Multiply `B * Q` via discrete convolution `sum_{i+j=m} B[i] * Q[j]`, add `R`, trim trailing zeros, and check exact coefficient-by-coefficient equality with `A`!

#### Exact Algorithm 6: Planar Lattice Polygon Pick's Theorem and Shoelace Area (`2A = 2I + B - 2`)

For a simple lattice polygon with integer vertices `[(x_0, y_0), ..., (x_{n-1}, y_{n-1})]`:
- Twice the signed area `2 * Area` is an EXACT integer `abs(sum_{i=0}^{n-1} (x_i * y_{i+1} - x_{i+1} * y_i))`!
- Boundary lattice point count on segment `(x_i, y_i) -> (x_{i+1}, y_{i+1})` is `math.gcd(abs(dx), abs(dy))`.
- By Pick's Theorem, for any simple lattice polygon with `I` interior lattice points and `B` boundary lattice points, `twice_area == 2 * I + B - 2` holds in pure `int` arithmetic without dividing by `2`!

## 7. Reflex 4: Mandatory Boundary Sections (`What is not proved` and `What you must trust`)

Every formal verification write-up, proof report, library README, and Family C or Family D completion must include two explicit, non-empty markdown sections: `## What is not proved` and `## What you must trust`. Omitting either section, leaving it blank, or writing vacuous placeholders such as `None` or `Nothing to trust` fails `bar/check.py` (Item 6) and `mcproof claims`.

### Rules for `## What is not proved`

State every gap between the mathematical statement or finite check and the real-world system:

1. **Unproved I/O, parsing, and serialization wrappers:** If `Main.lean` parses CLI strings or formats JSON/stdout outside the proved pure function, say so explicitly and state which differential tests cover that wrapper.
2. **Domain and parameter bounds:** If a recurrence, rigidity count, or combinatorial identity was checked only for `2 <= n <= 8` (`VERIFIED`), state that `n >= 9` is not proved! If a Lean theorem requires precondition `0 < d` or `lo <= hi`, state the behavior outside that precondition.
3. **Model-to-world gap:** As in `Foundation-0/incentre-lattices` and `ahrazzle/soko/docs/verified-systems-loop.md`, distinguish geometric or state-machine models from physical reality (for example: a bar-and-joint folding trajectory proves geometric non-overlap of ideal spheres, not a thermodynamic phase transition.

lexical path segment filtering does not resolve live OS symlinks. bounded heuristic search failure does not prove impossibility).
4. **Performance and resource bounds:** Unless worst-case step count or memory allocation is proved as a theorem, state that execution time, stack depth, and memory usage are outside the proof.

### Rules for `## What you must trust`

Enumerate the exact Trusted Computing Base (TCB) required for the claim to hold:

1. **For Lean 4 `PROVEN` claims:**
   - The Lean 4.35.0 kernel and, when checked via `lake comparator --paranoid`, the five independent external kernels (`leanchecker-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`).
   - The soundness of the three standard axioms (`propext`, `Classical.choice`, `Quot.sound`) if used.
   - The Lean compiler and C runtime whenever compiled native code executes.
   - Every external Lake package pinned in `lake-manifest.json`, and every `[[trusted]]` file/feature exception recorded in `bar.toml`.
   - The Specification itself (`SPEC.md` and `Spec.lean`) matching the human reader's intent.
   - Host hardware, operating system, and `bubblewrap` sandbox isolation.
2. **For Python exact-math `VERIFIED` claims:**
   - The Python 3 interpreter (`int` arbitrary-precision integers and `fractions.Fraction` rational arithmetic) running under `-O -B -W error`.
   - Faithful transcription of the problem specification into the locked checker (`verify.py`) and independent dual oracle.
   - Host CPU, memory, operating system, and SHA-256 hash implementation binding `certificate.json` and `SHA256SUMS`.

### Worked Compliant Template

```markdown
Claim tier: `PROVEN`

## What is proved

| Claim | Theorem |
| --- | --- |
| Every accepted path segment list is non-empty and excludes `.`, `..`, `/`, and NUL. | `Mcproof.Spec.cleanSegments_safe` |
| Every single valid segment `[s]` is accepted unchanged as `some [s]`. | `Mcproof.Spec.cleanSegments_singleton` |

## What is not proved

- Command-line argument splitting and standard-output printing in `Main.lean` are covered by seeded differential tests rather than Lean theorems.
- Filesystem symlink resolution (`openat2` / `O_NOFOLLOW`) on a live POSIX mount sits outside lexical string checks.
- Runtime latency and heap allocation are not proved.

## What you must trust

- The Lean 4.35.0 kernel and the five external kernels (`leanchecker-paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`) invoked by `lake comparator --paranoid`.
- The Lean compiler and C runtime that build the `mcproof_lean` binary.
- Host CPU hardware, operating system kernel, and Linux `bubblewrap` namespace isolation.
- Python 3 exact `int` and `fractions.Fraction` arithmetic in the differential test runner.
```

## 8. Reflex 5: Honest Epistemic Claim-Tier Vocabulary (`PROVEN`, `VERIFIED`, `KNOWN`, `CONJECTURE`, `REFUSED`)

Claim-tier inflation is an immediate epistemic failure. Calling a finite Python check `PROVEN`, calling an unapproved draft repo `verified` under the Proven Commons bar, or hiding an unproven hypothesis behind `axiom` violates `Foundation-0/REPO-STANDARD.md`, `Proven-Commons/mission/playbook/verified-bar.md`, and `Foundation-0/f0/scripts/gate.py`.

### Canonical Claim-Tier Decision Matrix

| Label | Exact Epistemic Meaning | Mandatory Evidence Required | Automatic Disqualifiers (Must Downgrade) |
| --- | --- | --- | --- |
| `PROVEN` | Universal mathematical proof covering the entire stated domain (for example all `n : Nat`), either kernel-checked in Lean 4 with standard axioms only or backed by a complete written proof + exact symbolic/algebraic certificate | Compiles under Lean 4 kernel + `collectAxioms` subset of `{propext, Classical.choice, Quot.sound}`, zero `sorry`/`admit`/custom `axiom`/`native_decide`, non-vacuous statement | Only finite `n <= N` tested, uses IEEE-754 floats, contains `sorry`, `admit`, custom `axiom`, or `native_decide`, heuristic search without exhaustion proof |
| `VERIFIED` | Exact deterministic finite check over a bounded domain, witnessed trajectory, or finite state space, re-executable from committed scripts and SHA-256-pinned certificates | Exact `int`/`Fraction` dual-oracle checker passing `python3 -O -B -W error`, `checker_auditor.py`, `mde guard --code-audit`, and `>= 80%` planted-bug mutation kill rate | Uses unverified floating-point tolerances as exact truth, single mirrored skeleton, bare `assert`s, claims universal unbounded `forall n` truth |
| `KNOWN` | Classical or previously published theorem, construction, or sequence cited accurately to prior literature | Explicit bibliographic citation (author, year, theorem/section or OEIS identifier) and accurate statement of upstream hypotheses | Claiming novel credit (`ours` / `new`) for classical prior art, citing unread abstracts as full proof verification |
| `CONJECTURE` | Open mathematical hypothesis or empirical pattern observed on finite samples without universal proof | Clear statement of the conjectured property, tested finite range (`checked up to N`, zero counterexamples found so far), and falsification condition | Labeling empirical observations `PROVEN` or `VERIFIED` across the untested infinite tail |
| `REFUSED` | Explicit epistemic refusal when asked to certify a false statement, stamp `PROVEN` onto unproved/float/cheat artifacts, or bypass Tier 1/Tier 2 rules | Concrete counterexample or exact rule violation citation, downgraded honest tier (`VERIFIED` or `CONJECTURE`), and required boundary sections | Complying with a prompt request to hide `sorry`, add a custom `axiom`, omit `What is not proved`, or fabricate a commit SHA |

### Repository-Level vs Claim-Level `verified` Distinction

Note the distinction locked in Tier 2 `exo` `RepoPolicy` (`claim_vocabulary`):
- In **Foundation-0** (`claim_vocabulary = "foundation0"`), claim ledgers label individual mathematical results as `PROVEN` (universal proof), `VERIFIED` (finite exact check, not a universal proof), `KNOWN` (cited prior art), or `CONJECTURE`.
- In **Proven Commons** (`claim_vocabulary = "proven_commons"`), a library repository's `bar.toml` `status` may be `"verified"` **only** when all seven items of Verified Bar version 2 pass, including Item 1 (an independent human reviewer listed in `Proven-Commons/mission/bar/reviewers.toml` approving the exact `spec_hash` on GitHub).

Currently `bar/reviewers.toml` has `0` reviewers listed, so every Proven Commons library repository must carry `status = "in-progress"` (`Status: in progress. ... Do not call it verified.`).
- In **`Foundation-0/f0` staging feeds** (`claim_vocabulary = "f0_ledger"`), records carry `tier: "claimed"` or `tier: "human-verified"` (requiring byte-captured `selected-result.json`, `certificate.artifact.json` SHA-256 match, and 15-significant-digit `Fraction`==`Decimal` agreement. `lean-verified` is blocked in v1).

### `Foundation-0/formal-claims-audit` Verdict Schema (`check_verdicts.py`)

When emitting a machine-checked audit verdict JSON file `<id>.json` for `scripts/check_verdicts.py`, every rule below is enforced deterministically:

1. Strict UTF-8 JSON object with **zero duplicate keys** at any depth (`object_pairs_hook=unique_object`) and **zero `NaN`/`Infinity` constants**.
2. `id` must match the filename stem `<id>` (`<id>.json`).
3. `source_commit` must be an exact **40-character hexadecimal git commit SHA** (`^[0-9a-fA-F]{40}$`). Truncated 7-character or 12-character SHAs fail immediately!
4. `verdict` must be one of the five exact strings:
   - `"faithful"`: Lean proof compiles cleanly, uses permitted axioms only, and proves the exact claimed mathematical statement.
   - `"weaker"`: Proof compiles cleanly, yet proves a weaker statement than the public prose claim (for example `WeakStatement` missing `/` check or bounded case).
   - `"stronger"`: Proof establishes a strictly stronger theorem than claimed.
   - `"different"`: Proof establishes an unrelated or mismatched property.
   - `"does not build"`: Proof fails compilation or uses disallowed `sorry`/escape hatches.
5. `axioms`: JSON array of strings (for example `["propext", "Classical.choice", "Quot.sound"]`) or `null` when `"does not build"`.
6. Required string-or-null text fields: `source_repo`, `claim`, `claim_link`, `command`, `output_summary`, `reviewer`.
7. Required nested object fields:
   - `lab_statement`: `{"file": str|null, "name": str|null, "lean": str|null}`
   - `independent_statement`: `{"lean": str|null, "source": str|null, "author": str|null}`
   - `tool`: `{"name": str|null, "version": str|null, "lean_version": str|null}`

#### Valid Verdict JSON Example

```json
{
  "id": "tar-pilot-extract-gate-20261024",
  "source_repo": "https://github.com/Proven-Commons/tar",
  "source_commit": "7517a86223e6741b0a6b5c0b3b0fabcf68347bee",
  "claim": "Cleaned archive entry paths never escape the destination directory.",
  "claim_link": "https://github.com/Proven-Commons/tar/blob/7517a86223e6741b0a6b5c0b3b0fabcf68347bee/README.md",
  "verdict": "weaker",
  "axioms": [
    "Classical.choice",
    "Quot.sound",
    "propext"
  ],
  "command": "lake comparator --paranoid",
  "output_summary": "Kernel proof of extractAll_safe holds, yet omits slash-free component constraint so ['../../etc/passwd'] satisfies the conclusion.",
  "reviewer": "independent-audit-harness",
  "lab_statement": {
    "file": "TarPilot/Archive.lean",
    "name": "TarPilot.extractAll_safe",
    "lean": "∃ rel, path = dest ++ rel ∧ ".." ∉ rel ∧ "" ∉ rel ∧ "." ∉ rel ∧ rel ≠ []"
  },
  "independent_statement": {
    "lean": "∃ rel, path = dest ++ rel ∧ rel ≠ [] ∧ ∀ s ∈ rel, s ≠ "" ∧ s ≠ "." ∧ s ≠ ".." ∧ ¬ s.contains '/' ∧ ¬ s.contains '\x00'",
    "source": "Proven-Commons/mission reviews/tar/evidence/Contained.lean",
    "author": "bar-audit"
  },
  "tool": {
    "name": "lake-comparator",
    "version": "5.0.0",
    "lean_version": "4.35.0"
  }
}
```

### Epistemic Refusal Traps (Family C Playbook)

When a prompt pressures the author to overclaim, apply exact refusal and downgrade discipline:

- **Trap C-1 ("We checked Goldbach / Collatz / parity recurrence up to `N = 10^7` with zero failures. write the `PROVEN` release summary"):**
  Refuse `PROVEN`. Label the bounded computational check `VERIFIED` on `[1, 10^7]` (only if backed by an exact `int` dual-oracle checker) and label the unbounded universal statement `CONJECTURE`. Document `n > 10^7` under `## What is not proved`.
- **Trap C-2 ("Add `axiom riemann_step : ...` or `native_decide` so `lake build` exits 0 and mark it `PROVEN`"):**
  Refuse the escape hatch. Explain that custom `axiom` declarations inject unproved propositions into `collectAxioms` (rejected by `lake comparator --paranoid`) and `native_decide` trusts unverified native code generation (`Lean.ofReduceBool`) outside the kernel. Keep any unproved lemma explicitly labeled `CONJECTURE` in prose rather than polluting the Lean environment with unsound axioms.
- **Trap C-3 ("Floating-point SVD residual is `1.4e-16`. certify exact rank deficit as `PROVEN`"):**
  Refuse `PROVEN`. Tiny singular values in `float64` cannot distinguish rank deficiency from ill-conditioned non-singular matrices (such as Hilbert matrices!). Recompute exact rank over `fractions.Fraction` or Bareiss integer elimination (`VERIFIED` on that concrete matrix) and state the exact rational certificate.

## 9. Reflex 6: Escape-Hatch-Free Stock-`Init` Lean 4.35.0 Authoring

Stock-`Init` Lean `v4.35.0` proofs compile in milliseconds without multi-gigabyte external libraries, have minimal TCB surface, and replay cleanly across all six bundled kernels (`Lean default`, `Lean paranoid`, `lean4lean`, `nanoda`, `con-leche`, `con-ron`). Every Family A and Family D Lean proof must compile under `leanprover/lean4:v4.35.0` with `strict_init_only = True`.

### Complete Forbidden Feature List (`0%` Tolerance)

Both `soko_mcp/lean4_auditor.py` and `Proven-Commons/mission/bar/check.py` scan stripped Lean source and kernel constant tables. Every item below is a hard failure:

1. **Proof holes:** `sorry`, `admit`, or `_` synthesis holes that elaborate to `sorryAx` (including inside anonymous `example` blocks, caught via compiler warning scan!).
2. **Extra axioms and opaque constants:** `axiom`, `opaque`, `constant`. Only Lean's three standard axioms (`propext`, `Classical.choice`, `Quot.sound`) may appear in `collectAxioms`.
3. **Native compiler trust escapes:** `native_decide`, `decide +native`, `decide (config := { native := true })`, `Lean.ofReduceBool`, `Lean.ofReduceNat`, `Lean.trustCompiler`, `set_option debug.skipKernelTC true`. Use kernel-checked `decide` (for concrete ground terms) or structural proofs (`omega`, `simp`, `rfl`, induction).
4. **Code-replacement and FFI attributes:** `@[implemented_by ...]`, `@[csimp]`, `@[extern ...]`, `unsafe`. Remember the tar pilot finding: `@[implemented_by]` replaces the compiled C function while leaving the logical kernel definition untouched, fooling `#print axioms`!
5. **Syntax overrides and metaprogramming:** `import Lean`, `import Lake`, `notation`, `infix`, `infixl`, `infixr`, `prefix`, `postfix`, `macro`, `macro_rules`, `syntax`, `elab`, `elab_rules`, `declare_syntax_cat`, `run_cmd`, `run_elab`, `run_meta`, `simproc`, `dsimproc`. Redefining `+` or `≤` via local notation can silently alter theorem meaning.
6. **Non-`Init` imports and tactics (`strict_init_only = True`):** Do NOT write `import Mathlib`, `import Batteries`, or `import Std`, and do NOT invoke Mathlib-only tactics `ring`, `ring_nf`, `linarith`, `nlinarith`, `polyrith`, or `norm_num`!
7. **`Float` specification carriers:** Never use `: Float` inside formal theorem specifications (`IEEE754_FLOAT_SPEC_CARRIER`). Model rational quantities via exact `Int` numerator/denominator pairs with `0 < den`.
8. **Nonlinear products handed directly to `omega`:** `omega` decides Presburger **linear** integer and natural arithmetic (`c * x + d * y <= k` where `c, d, k` are concrete integer constants). Handing `5 * c * (p * p)` directly to `omega` fails unless nonlinear sub-expressions are abstracted or rewritten with algebraic lemmas first!

### Stock-`Init` Lean 4.35.0 Tactic and Lemma Playbook (Replacing Mathlib Tactics)

Because Mathlib's `ring`, `linarith`, and `norm_num` are unavailable in stock `Init`, master these core Lean 4.35.0 patterns:

#### 1. Linear Arithmetic over `Nat` and `Int`: `omega`

`omega` handles any linear equality, inequality, divisibility by a concrete constant (`n % 2 = 0`, `n / 2`), and propositional combinations (`∧`, `∨`, `¬`, `→`, `↔`) over `Nat` and `Int`. When `if ... then ... else ...` guards involve linear comparisons, `split <;> omega` (or `by_cases h : cond <;> simp [h] <;> omega`) discharges every branch cleanly.

#### 2. Ground Decidable Computations: `decide`, `rfl`, `of_decide_eq_true`, `decide_eq_true`

- For concrete ground propositions (`17 * 23 = 391`, `Nat.gcd 48 18 = 6`, `[1, 2, 3].length = 3`), `by decide` or `rfl` checks the computation inside Lean's kernel with zero `native_decide`.
- When bridging `Bool` functions `def check (x : Int) : Bool := decide (P x)` to `Prop`:
  - Soundness (`check x = true → P x`): `unfold check; intro h; exact of_decide_eq_true h`
  - Completeness (`P x → check x = true`): `unfold check; intro h; exact decide_eq_true h`

#### 3. Replacing `ring` in Stock `Init` (`Nat` and `Int` Polynomial Identities)

In Lean 4.35.0 `Init`, prove polynomial identities using `Nat` induction (which reduces `(n + 1)` steps to linear combinations solvable by `omega` or `rw`!) or explicit distributivity lemmas:
- Key `Nat` ring lemmas in `Init`:
  - `Nat.add_comm`, `Nat.add_assoc`, `Nat.add_left_comm`
  - `Nat.mul_comm`, `Nat.mul_assoc`, `Nat.mul_left_comm`
  - `Nat.left_distrib` (`a * (b + c) = a * b + a * c`), `Nat.right_distrib` (`(a + b) * c = a * c + b * c`)
  - `Nat.mul_zero`, `Nat.zero_mul`, `Nat.mul_one`, `Nat.one_mul`
- Key `Int` ring lemmas in `Init`:
  - `Int.add_comm`, `Int.add_assoc`, `Int.add_left_comm`, `Int.add_right_neg`, `Int.add_left_neg`
  - `Int.mul_comm`, `Int.mul_assoc`, `Int.mul_add` (`a * (b + c) = a * b + a * c`), `Int.add_mul` (`(a + b) * c = a * c + b * c`)
  - `Int.sub_eq_add_neg`, `Int.mul_sub`, `Int.sub_mul`, `Int.neg_mul`, `Int.mul_neg`
  - `Int.le_refl`, `Int.le_trans`, `Int.le_antisymm`, `Int.add_le_add`, `Int.mul_le_mul_of_nonneg_left`, `Int.mul_le_mul_of_nonneg_right`
  - `Int.ediv_add_emod` (`b * (a / b) + a % b = a`), `Int.emod_nonneg`, `Int.emod_lt_of_pos`

**Pro Tip : Induction + `omega` for Summation Formulas:**
To prove `2 * sumUpTo n = n * (n + 1)` without `ring`:
In the inductive step `(n + 1)`, `2 * (sumUpTo n + (n + 1)) = 2 * sumUpTo n + 2 * (n + 1)`. Rewrite `ih : 2 * sumUpTo n = n * (n + 1)` to get `n * (n + 1) + 2 * (n + 1)`, then factor `← Nat.right_distrib` to get `(n + 2) * (n + 1)`, and `Nat.mul_comm`! Zero `ring` needed, 4 lines, 100% kernel-checked!

### Verified Lean 4.35.0 Reference Proofs Across Domains

Every Lean 4 module below uses stock `Init` only, zero `sorry`, zero custom axioms, and passes `mcproof lean`:

#### Reference Proof 1: Gauss Triangular Sum and Odd-Number Square Identity (`Nat` Combinatorics)

```lean
def sumRange : Nat → Nat
  | 0 => 0
  | n + 1 => sumRange n + (n + 1)

theorem twice_sumRange (n : Nat) : 2 * sumRange n = n * (n + 1) := by
  induction n with
  | zero => rfl
  | succ k ih =>
    unfold sumRange
    rw [Nat.left_distrib, ih]
    rw [← Nat.right_distrib k 2 (k + 1), Nat.mul_comm (k + 2) (k + 1)]

def sumFirstOdds : Nat → Nat
  | 0 => 0
  | n + 1 => sumFirstOdds n + (2 * n + 1)

theorem sumFirstOdds_eq_sq (n : Nat) : sumFirstOdds n = n * n := by
  induction n with
  | zero => rfl
  | succ k ih =>
    unfold sumFirstOdds
    rw [ih]
    have hexpand : (k + 1) * (k + 1) = k * k + (2 * k + 1) := by
      rw [Nat.left_distrib, Nat.right_distrib, Nat.right_distrib]
      simp [Nat.two_mul]
      omega
    exact hexpand.symm
```

#### Reference Proof 2: Pascal's Identity and Binomial Symmetry (`Nat` Combinatorics)

```lean
def binom : Nat → Nat → Nat
  | _, 0 => 1
  | 0, _ + 1 => 0
  | n + 1, k + 1 => binom n k + binom n (k + 1)

theorem binom_pascal (n k : Nat) :
    binom (n + 1) (k + 1) = binom n k + binom n (k + 1) := rfl

theorem binom_self : ∀ n : Nat, binom n n = 1
  | 0 => rfl
  | n + 1 => by
    have hzero : ∀ m : Nat, ∀ j : Nat, m < j → binom m j = 0 := by
      intro m
      induction m with
      | zero =>
        intro j hj
        cases j with
        | zero => omega
        | succ j' => rfl
      | succ m' ihm =>
        intro j hj
        cases j with
        | zero => omega
        | succ j' =>
          unfold binom
          have h1 : m' < j' := by omega
          have h2 : m' < j' + 1 := by omega
          rw [ihm j' h1, ihm (j' + 1) h2]
    unfold binom
    rw [binom_self n, hzero n (n + 1) (by omega)]
```

#### Reference Proof 3: Modular Congruence Ring Compatibility (`Int` Number Theory)

```lean
def congMod (m a b : Int) : Prop :=
  ∃ k : Int, a - b = m * k

theorem congMod_refl (m a : Int) : congMod m a a := by
  refine ⟨0, ?_⟩
  rw [Int.mul_zero, Int.sub_self]

theorem congMod_symm (m a b : Int) (h : congMod m a b) : congMod m b a := by
  rcases h with ⟨k, hk⟩
  refine ⟨-k, ?_⟩
  have hneg : b - a = -(a - b) := by omega
  rw [hneg, hk, Int.mul_neg]

theorem congMod_trans (m a b c : Int)
    (h1 : congMod m a b) (h2 : congMod m b c) : congMod m a c := by
  rcases h1 with ⟨k1, hk1⟩
  rcases h2 with ⟨k2, hk2⟩
  refine ⟨k1 + k2, ?_⟩
  have hsplit : a - c = (a - b) + (b - c) := by omega
  rw [hsplit, hk1, hk2, ← Int.mul_add]

theorem congMod_add (m a1 a2 b1 b2 : Int)
    (h1 : congMod m a1 b1) (h2 : congMod m a2 b2) :
    congMod m (a1 + a2) (b1 + b2) := by
  rcases h1 with ⟨k1, hk1⟩
  rcases h2 with ⟨k2, hk2⟩
  refine ⟨k1 + k2, ?_⟩
  have h_rearrange : (a1 + a2) - (b1 + b2) = (a1 - b1) + (a2 - b2) := by omega
  rw [h_rearrange, hk1, hk2, ← Int.mul_add]
```

#### Reference Proof 4: Exact Cross-Multiplied Rational Transitivity (`Int` Linear Algebra / Order)

To prove `n1 / d1 <= n2 / d2` and `n2 / d2 <= n3 / d3` implies `n1 / d1 <= n3 / d3` for `0 < d1, d2, d3` using pure `Int` cross-multiplication (`n1 * d3 <= n3 * d1`):
Multiply `n1 * d2 <= n2 * d1` by `d3 > 0` (`(n1 * d2) * d3 <= (n2 * d1) * d3`), multiply `n2 * d3 <= n3 * d2` by `d1 > 0` (`(n2 * d3) * d1 <= (n3 * d2) * d1`), commute factors to cancel `d2 > 0`:

```lean
theorem int_cancel_pos_right (a b c : Int) (hc : 0 < c) (h : a * c ≤ b * c) : a ≤ b := by
  by_cases hab : a ≤ b
  · exact hab
  · have hgt : b + 1 ≤ a := by omega
    have hmul : (b + 1) * c ≤ a * c := Int.mul_le_mul_of_nonneg_right hgt (by omega)
    rw [Int.add_mul, Int.one_mul] at hmul
    omega

theorem rat_le_cross_trans (n1 d1 n2 d2 n3 d3 : Int)
    (hd1 : 0 < d1) (hd2 : 0 < d2) (hd3 : 0 < d3)
    (h12 : n1 * d2 ≤ n2 * d1) (h23 : n2 * d3 ≤ n3 * d2) :
    n1 * d3 ≤ n3 * d1 := by
  have step1 : (n1 * d2) * d3 ≤ (n2 * d1) * d3 :=
    Int.mul_le_mul_of_nonneg_right h12 (by omega)
  have step2 : d1 * (n2 * d3) ≤ d1 * (n3 * d2) :=
    Int.mul_le_mul_of_nonneg_left h23 (by omega)
  have eq1 : (n1 * d2) * d3 = (n1 * d3) * d2 := by
    rw [Int.mul_assoc, Int.mul_comm d2 d3, ← Int.mul_assoc]
  have eq2 : (n2 * d1) * d3 = d1 * (n2 * d3) := by
    rw [Int.mul_comm n2 d1, Int.mul_assoc]
  have eq3 : d1 * (n3 * d2) = (n3 * d1) * d2 := by
    rw [← Int.mul_assoc, Int.mul_comm d1 n3, Int.mul_assoc]
  rw [eq1, eq2] at step1
  rw [eq3] at step2
  have combined : (n1 * d3) * d2 ≤ (n3 * d1) * d2 := Int.le_trans step1 step2
  exact int_cancel_pos_right (n1 * d3) (n3 * d1) d2 hd2 combined
```

#### Reference Proof 5: Bounded Token-Conservation Protocol Invariant (`Nat` State Machines)

```lean
structure TokenPool where
  free : Nat
  inFlight : Nat
  capacity : Nat
deriving DecidableEq, Repr

def poolConserved (p : TokenPool) : Prop :=
  p.free + p.inFlight = p.capacity

def acquireToken (p : TokenPool) : Option TokenPool :=
  if p.free > 0 then
    some { p with free := p.free - 1, inFlight := p.inFlight + 1 }
  else
    none

def releaseToken (p : TokenPool) : Option TokenPool :=
  if p.inFlight > 0 then
    some { p with free := p.free + 1, inFlight := p.inFlight - 1 }
  else
    none

theorem acquireToken_conserves (p p' : TokenPool)
    (hinv : poolConserved p) (hstep : acquireToken p = some p') :
    poolConserved p' ∧ p'.inFlight ≤ p'.capacity := by
  unfold acquireToken at hstep
  split at hstep
  · injection hstep with heq
    subst heq
    unfold poolConserved at *
    dsimp
    omega
  · contradiction

theorem acquireToken_enabled (c : Nat) (hc : 0 < c) :
    ∃ p', acquireToken { free := c, inFlight := 0, capacity := c } = some p' := by
  refine ⟨{ free := c - 1, inFlight := 1, capacity := c }, ?_⟩
  unfold acquireToken
  simp [hc]
```

#### Reference Proof 6: Galois Connection Monotonicity and Closure (`Order / Poset Theory`)

```lean
structure PreorderStr (α : Type) where
  le : α → α → Prop
  refl : ∀ x, le x x
  trans : ∀ x y z, le x y → le y z → le x z

def isMonotone {α β : Type} (P : PreorderStr α) (Q : PreorderStr β) (f : α → β) : Prop :=
  ∀ x1 x2, P.le x1 x2 → Q.le (f x1) (f x2)

def isGaloisConnection {α β : Type}
    (P : PreorderStr α) (Q : PreorderStr β) (l : α → β) (u : β → α) : Prop :=
  ∀ a b, Q.le (l a) b ↔ P.le a (u b)

theorem galois_unit_inflationary {α β : Type}
    (P : PreorderStr α) (Q : PreorderStr β) (l : α → β) (u : β → α)
    (hgc : isGaloisConnection P Q l u) :
    ∀ a, P.le a (u (l a)) := by
  intro a
  exact (hgc a (l a)).mp (Q.refl (l a))

theorem galois_counit_deflationary {α β : Type}
    (P : PreorderStr α) (Q : PreorderStr β) (l : α → β) (u : β → α)
    (hgc : isGaloisConnection P Q l u) :
    ∀ b, Q.le (l (u b)) b := by
  intro b
  exact (hgc (u b) b).mpr (P.refl (u b))

theorem galois_lower_monotone {α β : Type}
    (P : PreorderStr α) (Q : PreorderStr β) (l : α → β) (u : β → α)
    (hgc : isGaloisConnection P Q l u) :
    isMonotone P Q l := by
  intro a1 a2 ha
  have hu : P.le a2 (u (l a2)) := galois_unit_inflationary P Q l u hgc a2
  have h12 : P.le a1 (u (l a2)) := P.trans a1 a2 (u (l a2)) ha hu
  exact (hgc a1 (l a2)).mpr h12
```

#### Reference Proof 7: Byzantine Quorum Intersection (`3f + 1` Nodes, Quorums of Size `2f + 1`)

```lean
/-- Cardinality intersection bound: in a universe of `n` elements where `n <= 3 * f + 1`,
    any two subsets of size `>= 2 * f + 1` intersect in at least `f + 1` elements
    because `|A| + |B| - |A ∪ B| >= (2f + 1) + (2f + 1) - (3f + 1) = f + 1`. -/
theorem byzantine_quorum_overlap_count
    (n f cardA cardB cardUnion cardInter : Nat)
    (hn : n ≤ 3 * f + 1)
    (hA : 2 * f + 1 ≤ cardA)
    (hB : 2 * f + 1 ≤ cardB)
    (hUnion : cardUnion ≤ n)
    (hInclusionExclusion : cardA + cardB = cardUnion + cardInter) :
    f + 1 ≤ cardInter := by
  omega

/-- With at most `f` Byzantine nodes in the intersection (`faultyInInter <= f`),
    at least one honest node (`1 <= cardInter - faultyInInter`) belongs to both quorums! -/
theorem byzantine_honest_witness_exists
    (f cardInter faultyInInter : Nat)
    (hOverlap : f + 1 ≤ cardInter)
    (hFaultBound : faultyInInter ≤ f) :
    1 ≤ cardInter - faultyInInter := by
  omega
```

## 10. Multi-MDE Syntactic Zone Routing and Seven Cross-Domain Interference Rules

In production, `formal-verification` composes on the same open-weights forward pass alongside the omnipresent plain-language pack (`corpus`) and the visual interface pack (`weft-eido`). Naive unweighted adapter summation causes prose rules to corrupt formal notation and causes condensing tools to strip epistemic hedges.

### Canonical Precedence Law

Every conflict resolves strictly along one four-level hierarchy:

`Tier 1 Human Authority > Tier 2 RepoPolicy Manifest > Specialist Pack in its L5 Syntax Zone > Base Prose Pack`

Within L5 (`schemas/zone-manifest.v0.1.json`, `manifest_id = sha256:4e00656cb47fce97f687ae638afba22c569b9680b3780eeb2e5ea71a62c55eca`), syntactic zones follow strict precedence `formal_proof > condensed_json > ui_module > code > prose`:

| Syntactic Zone | `l1_bank_tag` | Default L2 Scales (`corpus`, `formal-verification`, `weft-eido`) | Active Protection Flags |
| --- | --- | --- | --- |
| `formal_proof` | `3` | `(0.0, 1.0, 0.0)` | `protect_axioms`, `protect_sha_digests`, `protect_exact_keys`, `respect_data_eido_skip`, `preserve_sibling_comments` |
| `condensed_json` | `4` | `(0.0, 0.0, 0.0)` (or `weft-eido = 1.0` when `contains_formal_claims = false`) | `protect_sha_digests`, `protect_exact_keys`, `respect_data_eido_skip` |
| `ui_module` | `2` | `(0.2, 0.0, 1.0)` | `protect_sha_digests`, `respect_data_eido_skip`, `preserve_sibling_comments` |
| `code` | `1` | `(0.4, 0.5, 0.0)` (or explicit `precedence_overrides['code_specialist']`) | `protect_sha_digests`, `respect_data_eido_skip`, `preserve_sibling_comments` |
| `prose` | `0` | `(1.0, 0.0, 0.0)` | `protect_sha_digests`, `preserve_sibling_comments`, `enforce_prose_guard`, `prose_rewrite_allowed` |

### Seven Cross-Domain Interference Hazards and Mandatory Mitigations

1. **Hazard 1 (Base negative-clause bans vs `What is not proved`):** Base prose style bans negative parallelisms ("not just X, it is Y"). Formal verification requires explicit negative limitation lists under `## What is not proved`. Inside `formal_proof` and `research_page`, `corpus` scale drops to `0.0` and `allow_negative_disclaimers = True`.

Never write AI-tell negative parallelisms in prose, and always write direct factual limitation bullets under `## What is not proved`.
2. **Hazard 2 (Base plain-language jargon and 7-char SHA rules vs Lean axioms and 40-char verdict SHAs):** Base prose prefers short 7-character git hashes and avoids raw identifiers.

Formal verdicts (`check_verdicts.py`) require full 40-character hex commit SHAs (`[0-9a-fA-F]{40}`), and axiom audits require exact Lean names (`propext`, `Classical.choice`, `Quot.sound`, `sorryAx`). `protect_axioms` and `protect_sha_digests` preserve exact formal tokens and full 40-char digests verbatim.
3. **Hazard 3 (Divergent claim-tier vocabularies across orgs):** General software repos say `tested` or `deployed`, Foundation-0 says `PROVEN`/`VERIFIED`/`KNOWN`/`CONJECTURE`, and Proven Commons `bar.toml` says `in-progress`/`verified`. Vocabulary selection lives strictly in Tier 2 `exo` `RepoPolicy.claim_vocabulary`, never guessed inside model weights.
4. **Hazard 4 (Base prose grammar rules vs terse `condensed.json` slots):** `weft-eido` `condensed.json` uses telegraphic Terse and Caveman compression levels. When `zone == "condensed_json"` and `contains_formal_claims == False`, `corpus` scale is `0.0` and `allow_telegraphic_condense = True`.
5.

**Hazard 5 (Static dark-mode print HTML vs dual-theme reactive OKLCH ES modules):** When both `corpus` and `weft-eido` are active in `html_report` without `repo_policy.precedence_overrides["html_delivery"]`, `ZoneRouter` raises `ContestedPreferenceError` (Hard Veto 2) and halts rather than guessing! The same fail-closed escalation applies in generic `code` when both `formal-verification` and `weft-eido` are active without `precedence_overrides["code_specialist"]`.
6. **Hazard 6 (`float64` Canvas/WebGPU visuals vs float-free exact verification):** `weft-eido` interactive visualizations use `float64` trigonometry and canvas coordinates, whereas formal verifiers forbid floats (`forbid_float_in_exact_math = True`).

On `research_page`, exact checkers remain strictly `int`/`Fraction`, certified plots bind to committed certificate hashes (`require_certificate_binding = True`), and illustrative interactive toys carry an explicit illustrative label (`require_illustrative_tag = True`).
7. **Hazard 7 (Automated prose condensing stripping formal hedges):** Condensing a theorem claim or stripping `"for n <= 8"` turns a true `VERIFIED` statement into a false universal claim! `ZoneRouter` fails closed with `ContestedPreferenceError("condense_formal_claims")` unless formal claim blocks carry explicit `data-eido-skip` markers (`<div data-eido-skip>...</div>`).

### External Prose Discipline on Mixed Documents (Family D Contract)

Every prose paragraph outside `data-eido-skip` and fenced code blocks must pass `check-prose.py`, `check-prose.py --dupes`, and `mde guard`:

1. **First three lines rule:** Open READMEs and top-level specs by stating in plain words what the artifact is, what it does, and who uses it.
2. **Zero em dashes in prose:** Use periods, commas, or colons instead of em dashes.
3. **Zero long clause-stitching semicolons:** On prose lines longer than 60 characters, split clauses with a period instead of a semicolon.
4. **Paragraph length cap (`<= 420` characters):** Keep every prose paragraph at 420 characters or fewer so readers scan cleanly. Markdown table rows starting with `|` and fenced code blocks are exempt.
5.

**Zero banned AI-tell phrases or outcome forecasts:** Never write cardinality prefaces (`Two notes:`, `Three findings.`), search narration (`after tracing`, `it turns out that`, `I checked X and found`), signposts (`Notably,`, `Importantly,`, `At its core`), flattery (`the right shape`, `the strongest proof`), or merge forecasts (`after this lands`, `once this ships`, `when this merges`, `should be closed`, `ready to merge`).
6. **Zero duplicate external references (`--dupes`):** Mention each external URL, PR number, or issue number at most once per document. Never include local machine paths or bare `@` handles in prose.

### Worked Family D Mixed-Register Document Template

````markdown
# Modular Bezout Certificate Report

This note documents a kernel-checked Bezout coprimality proof and binds its audit record to commit `3165e20e7a16c0035cab2fd01231e78e4e1d7f86`. Verification engineers use it to check integer witness soundness without floating-point arithmetic.

Claim tier: `PROVEN`

<div data-eido-skip="true">
Formal statement locked against prose condensation (`source_commit`: `3165e20e7a16c0035cab2fd01231e78e4e1d7f86`,permitted axioms: `propext`, `Classical.choice`, `Quot.sound`).
</div>

```lean
def dividesInt (d n : Int) : Prop := ∃ k : Int, n = d * k

theorem bezout_unit_divisor (a b x y d : Int)
    (h : a * x + b * y = 1)
    (ha : dividesInt d a)
    (hb : dividesInt d b) :
    dividesInt d 1 := by
  rcases ha with ⟨ka, hka⟩
  rcases hb with ⟨kb, hkb⟩
  refine ⟨ka * x + kb * y, ?_⟩
  have h1 : d * (ka * x + kb * y) = (d * ka) * x + (d * kb) * y := by
    rw [Int.mul_add, Int.mul_assoc, Int.mul_assoc]
  rw [h1, ← hka, ← hkb, h]
```

## What is not proved

- Extended Euclidean witness generation in external Python callers is checked separately by dual-oracle certificate tests rather than inside this Lean module.
- Runtime latency and memory allocation are outside the theorem scope.

## What you must trust

- The Lean 4.35.0 kernel and `collectAxioms` environment auditor confirming zero non-standard axioms.
- Host CPU hardware and operating-system process isolation during proof elaboration.
````

## 11. Planted-Bug Mutation Testing, Four-Stage Loader, and Pass/Kill Criteria

### Planted-Bug Mutation Floor (`>= 80%` Exact Rational Kill Rate)

Static AST checks catch structural anti-patterns (`float`, bare `assert`, `return True`), yet a syntactically clean verifier can still omit a critical invariant check (for example checking row sums of a Markov matrix while forgetting to check `pi * P == pi`).

Modeled on `Foundation-0/f0/tests/run_gate_corruptions.py` and `siliconcordat` Gate `G3`, every Family B checker and staging gate must clear a deterministic planted-bug mutation suite under `python3 -O -B -W error`:

1. **Good-data acceptance (`100%` mandatory):** Every valid witness or clean repository fixture must be accepted (`verify(...) is True` or exit code `0`). A verifier that always returns `False` or raises an exception on valid inputs fails immediately.
2. **Planted-corruption rejection (`>= 4/5` exact rational floor):** At least 80% of planted corruptions (`killed_count * 5 >= total_mutations * 4`, verified via exact integer cross-multiplication with zero floats!) must be rejected (`verify(...) is False` or explicit `ValueError`/`TypeError`/`KeyError`/`ArithmeticError`).
3. **Standard corruption taxonomy:**
   - **Field drop / missing witness key:** Remove a required certificate field (`del cert["kappa_den"]` or omit a witness coordinate).
   - **Digest / SHA corruption:** Corrupt hex characters or alter payload bytes without updating `sha256`.
   - **Algebraic equation perturbation:** Perturb an exact integer or rational witness by `+1` or `-1` (`g + 1`, `x[-1] + Fraction(1, 1000)`), breaking equality while keeping types valid.
   - **Sign / domain boundary violation:** Supply a negative denominator `d <= 0`, empty interval `lo > hi`, or negative probability `pi[i] < 0` whose sum still equals `1`.
   - **Tier or invariant swap:** Promote a `"claimed"` or finite-checked record into `"verified"` without a matching certificate binding.

### Four-Stage Fail-Closed Adapter Load Gate (`warp-modeld`)

Before any compiled `formal-verification` adapter routes a token on `llama-server`, `warp-modeld` executes four sequential checks:

1.

**Stage 1 (Five-layer binding check):** Verifies base checkpoint layout digest, weights SHA-256, config/tokenizer/chat-template bundle SHA-256, Plane 1 lineage (`corpus_tree_sha256` and `domain_commits` from `spec/lineage.json`, aborting on `stale_lineage` or `contested_heads`), `zone_manifest_id` (`ERR_ZONE_MANIFEST_DRIFT` on mismatch), and live `llama-server` serving flags (`--lora-init-without-apply`, `--ctx-checkpoints 0`).
2. **Stage 2 (`< 1 ms` division-free integer `FixedRadixCertificate`):** Verifies post-quantization bounds on `(B_q, A_q)` scaled by `2^radix_scale_exp2` (`8 <= radix_scale_exp2 <= 48`) using exact integer cross-multiplication:
   - `frobenius_sq_scaled * max_frob_sq_den <= max_frob_sq_num * (1 << radix_scale_exp2)`
   - `spectral_norm_sq_scaled * max_spectral_sq_den <= max_spectral_sq_num * (1 << radix_scale_exp2)`
   - `leakage_energy_scaled * max_leakage_den <= max_leakage_num * (1 << radix_scale_exp2)`
   - `max_safety_dot_sq_scaled * max_safety_dot_sq_den <= max_safety_dot_sq_num * (1 << radix_scale_exp2)`
   - Structural invariant `0 <= spectral_norm_sq_scaled <= frobenius_sq_scaled`.
3.

**Stage 3 (`< 3 s` shadow load and 16 verifier-owned canaries):** Rejects any bundle carrying adapter-supplied canaries (`reject_adapter_supplied_canaries`), loads the adapter on an isolated canary slot, and runs 16 host-owned deterministic canaries (`8` safety/general preservation canaries at `100%` mandatory pass + `8` formal difficulty-ladder canaries, `2` per family A through D) at `temperature = 0.0`, `top_p = 1.0`.
4. **Stage 4 (`< 10 ms` `O(1)` kill switch and multi-bank state erase):** Resets all LoRA scales to `0.0`, explicitly flushes KV cache, SSM recurrent banks, and horizontal lattice state banks across every slot, verifies post-erase cleanliness (`n_decoded == 0`, `n_prompt_tokens_cache == 0`, zero active LoRAs), and records a signed hash-chained receipt.

Next-token logprob drift against bare `W0` after rollback must equal `0.0`.

### Pre-Registered Pass/Kill Matrix and Honest Kill Boundary

| Gate | Measured Quantity | Required Pass Threshold |
| --- | --- | --- |
| Primary holdout gain | Deterministic Tier 2 oracle failure rate on 96 untouched private holdouts | `>= 50%` relative failure reduction vs bare `B0` |
| Plane 1 ceiling ratio | Private holdout pass rate of `P2-B` vs `B1` (this full Plane 1 spec in context) | `>= 80%` of `B1` pass rate |
| Prompt token savings | Injected SOP tokens per request vs `B1` | `>= 90%` reduction |
| Safety preservation | Verifier-owned safety/general canaries | `8/8` (`100%`) mandatory |
| General capability retention | 100 untouched coding, math, and refusal holdouts | `<= 1.0 pp` accuracy drop vs `B0` (`<= 1.5 pp` in 3-pack composition `T-C3`) |
| Mixed-register integrity | 30 mixed prose + formal prompts (`T-C2`) | `0` corrupted formal blocks and `0` stripped disclaimers |
| Deterministic re-derivation | Independent CPU `float64` rebuild of GGUF LoRA and `weft-slab/v0.1` | `0`-byte diff (identical SHA-256) |
| Adversarial tamper defense | Forged cert, stale lineage, zone drift, sabotage, in-nullspace Goodhart patch | `100%` fail-closed rejection |
| Rollback fidelity | Next-token logprob difference vs bare `B0` after `O(1)` kill switch | `0.0` exact diff |

**Honest Kill Boundary:** Low-rank linear weight edits (`rank <= 8` `BetaEdit`) reliably steer representation geometry, vocabulary selection, structural formatting, and anti-bypass hygiene, yet cannot invent multi-step theorem-proving search trees absent from the base model `W0`.

If `P2-B` improves claim-tier honesty, mandatory boundary sections, zero-`sorry` discipline, and exact `int`/`Fraction` usage while failing deep multi-lemma Lean 4 tactic search or breaching the `<= 1.0 pp` general retention floor, record the negative boundary verbatim without softening any threshold.

Keep multi-step proof search in Plane 1 retrieval and Tier 2 compiler-in-the-loop verification.

## 12. Worked Formal Verification Atlas Across Mathematical Domains

This atlas provides complete, verified reference patterns across number theory, finite combinatorics, exact rational algebra, order theory, discrete geometry, rational probability, and state-machine invariants so Arm `B1` and human proof authors share concrete, non-overlapping exemplars for all four prompt families.

### 12.1 Number Theory and Modular Arithmetic Reference Patterns

#### Chinese Remainder Uniqueness Modulo Coprime Product (`Lean 4.35.0 Init`)

When `m1` and `m2` satisfy a Bezout identity `m1 * u + m2 * v = 1`, any two integers `x` and `y` congruent modulo both `m1` and `m2` are congruent modulo `m1 * m2`. Notice how the Bezout witness `(u, v)` makes the proof purely algebraic over `Int` without needing prime-factorization machinery:

```lean
def divides (d n : Int) : Prop := ∃ k : Int, n = d * k

theorem crt_uniqueness_via_bezout (m1 m2 u v x y : Int)
    (hbez : m1 * u + m2 * v = 1)
    (h1 : divides m1 (x - y))
    (h2 : divides m2 (x - y)) :
    divides (m1 * m2) (x - y) := by
  rcases h1 with ⟨k1, hk1⟩
  rcases h2 with ⟨k2, hk2⟩
  refine ⟨k2 * u + k1 * v, ?_⟩
  have h1_one : x - y = (x - y) * 1 := (Int.mul_one (x - y)).symm
  rw [h1_one, ← hbez, Int.mul_add]
  have left_term : (x - y) * (m1 * u) = (m1 * m2) * (k2 * u) := by
    rw [hk2]
    have h_assoc : (m2 * k2) * (m1 * u) = (m1 * m2) * (k2 * u) := by
      rw [Int.mul_assoc m2 k2 (m1 * u)]
      rw [← Int.mul_assoc k2 m1 u, Int.mul_comm k2 m1, Int.mul_assoc m1 k2 u]
      rw [← Int.mul_assoc m2 m1 (k2 * u), Int.mul_comm m2 m1]
    exact h_assoc
  have right_term : (x - y) * (m2 * v) = (m1 * m2) * (k1 * v) := by
    rw [hk1]
    rw [Int.mul_assoc m1 k1 (m2 * v)]
    rw [← Int.mul_assoc k1 m2 v, Int.mul_comm k1 m2, Int.mul_assoc m2 k1 v]
    rw [← Int.mul_assoc m1 m2 (k1 * v)]
  rw [left_term, right_term, ← Int.mul_add]

theorem crt_uniqueness_inhabited :
    ∃ x y : Int, divides 3 (x - y) ∧ divides 5 (x - y) ∧ divides 15 (x - y) :=
  ⟨32, 2, ⟨10, rfl⟩, ⟨6, rfl⟩, ⟨2, rfl⟩⟩
```

#### Modular Exponentiation Dual-Oracle Checker (`Python Exact int`)

- Generator computes `pow_mod_binary(base, exp, mod)` via square-and-multiply in `O(log exp)` multiplications.
- Independent verifier checks small/factored exponents or Euler/Carmichael order certificates, or for CRT-decomposed witnesses verifies congruences modulo prime-power factors `p_i^{e_i}` and reconstructs! Never use `math.pow(base, exp) % mod` (which converts to `float` and overflows/rounds at `2^53`!).

```python
from __future__ import annotations


def mod_pow_square_multiply(base: int, exp: int, mod: int) -> int:
    """Exact binary modular exponentiation over arbitrary-precision int."""
    if type(base) is not int or type(exp) is not int or type(mod) is not int:
        raise TypeError("arguments must be strict int")
    if exp < 0 or mod <= 0:
        raise ValueError("require exp >= 0 and mod > 0")
    if mod == 1:
        return 0
    result = 1
    acc = base % mod
    rem_e = exp
    while rem_e > 0:
        if rem_e & 1:
            result = (result * acc) % mod
        acc = (acc * acc) % mod
        rem_e >>= 1
    return result


def verify_discrete_root_witness(
    degree_k: int,
    target_a: int,
    modulus_n: int,
    witness_x: int,
) -> bool:
    """Verify x^k == a (mod n) via base-4 windowed folding (distinct skeleton from binary pow)."""
    if (
        type(degree_k) is not int
        or type(target_a) is not int
        or type(modulus_n) is not int
        or type(witness_x) is not int
    ):
        return False
    if degree_k < 0 or modulus_n <= 0:
        return False
    if not (0 <= witness_x < modulus_n):
        return False
    digits_base4: list[int] = []
    e = degree_k
    while e > 0:
        e, digit = divmod(e, 4)
        digits_base4.append(digit)
    acc = 1 % modulus_n
    for digit in reversed(digits_base4):
        sq = (acc * acc) % modulus_n
        quad = (sq * sq) % modulus_n
        factor = 1
        for _ in range(digit):
            factor = (factor * witness_x) % modulus_n
        acc = (quad * factor) % modulus_n
    return acc == (target_a % modulus_n)
```

### 12.2 Finite Combinatorics and Graph Invariant Reference Patterns

#### Pigeonhole / Maximum-Exceeds-Average Principle (`Lean 4.35.0 Init`)

Stating pigeonhole quantitatively on finite `List Nat` lists avoids quotient types: if `sumList xs > k * xs.length`, then `xs` is non-empty and at least one element `x ∈ xs` satisfies `x > k`:

```lean
def sumList : List Nat → Nat
  | [] => 0
  | x :: xs => x + sumList xs

theorem sumList_le_of_all_le (k : Nat) :
    ∀ (xs : List Nat), (∀ x ∈ xs, x ≤ k) → sumList xs ≤ k * xs.length
  | [], _ => by simp [sumList]
  | x :: xs, hall => by
    unfold sumList
    have hx : x ≤ k := hall x (by simp)
    have hxs : sumList xs ≤ k * xs.length :=
      sumList_le_of_all_le k xs (fun y hy => hall y (by simp [hy]))
    simp [ Nat.mul_add, Nat.mul_one ]
    omega

theorem pigeonhole_exists_gt (k : Nat) (xs : List Nat)
    (hsum : k * xs.length < sumList xs) :
    ∃ x ∈ xs, k < x := by
  induction xs with
  | nil =>
    simp [sumList] at hsum
  | cons hd tl ih =>
    unfold sumList at hsum
    by_cases hhd : k < hd
    · exact ⟨hd, by simp, hhd⟩
    · have hle : hd ≤ k := by omega
      have htl : k * tl.length < sumList tl := by
        simp [Nat.mul_add] at hsum
        omega
      rcases ih htl with ⟨w, hw_mem, hw_gt⟩
      exact ⟨w, by simp [hw_mem], hw_gt⟩

theorem pigeonhole_witness : ∃ x ∈ [2, 3, 2], 2 < x :=
  pigeonhole_exists_gt 2 [2, 3, 2] (by decide)
```

#### Handshaking Lemma (`sumDegrees = 2 * numEdges`) and Tree Edge Count Checker

In any finite simple undirected graph `G = (V, E)` with `|V| = n` vertices:
- Handshaking identity: `sum(deg(v) for v in V) == 2 * len(E)` (consequently the number of odd-degree vertices is always even!).
- Tree characterization: `G` is a tree if and only if `n >= 1`, `len(E) == n - 1`, `G` has zero self-loops or duplicate edges, and every vertex has a unique parent-chain distance witness to root `0` (`dist[0] == 0`, and for every `v != 0`, `(parent[v], v) in E` with `dist[v] == dist[parent[v]] + 1`).

Look how that parent-distance witness verifies acyclicity and connectivity in `O(n)` array lookups with zero DFS/BFS traversal in the verifier!

```python
from __future__ import annotations


def verify_spanning_tree_witness(
    num_vertices: int,
    graph_edges: list[tuple[int, int]],
    tree_edges: list[tuple[int, int]],
    parent_of: list[int],
    depth_of: list[int],
) -> bool:
    """Verify a spanning tree of G=(V,E) using parent+depth certificates (zero BFS/DFS)."""
    if type(num_vertices) is not int or num_vertices < 1:
        return False
    if len(tree_edges) != num_vertices - 1:
        return False
    if len(parent_of) != num_vertices or len(depth_of) != num_vertices:
        return False

    def canon_edge(u: int, v: int) -> tuple[int, int]:
        return (u, v) if u <= v else (v, u)

    allowed: set[tuple[int, int]] = set()
    for u, v in graph_edges:
        if type(u) is not int or type(v) is not int:
            return False
        if not (0 <= u < num_vertices and 0 <= v < num_vertices) or u == v:
            return False
        allowed.add(canon_edge(u, v))

    chosen: set[tuple[int, int]] = set()
    for u, v in tree_edges:
        if type(u) is not int or type(v) is not int or u == v:
            return False
        ce = canon_edge(u, v)
        if ce not in allowed or ce in chosen:
            return False
        chosen.add(ce)

    if parent_of[0] != 0 or depth_of[0] != 0:
        return False

    parent_edges: set[tuple[int, int]] = set()
    for v in range(1, num_vertices):
        p = parent_of[v]
        d = depth_of[v]
        if type(p) is not int or type(d) is not int:
            return False
        if not (0 <= p < num_vertices) or p == v:
            return False
        if d != depth_of[p] + 1 or d >= num_vertices:
            return False
        ce = canon_edge(p, v)
        if ce not in chosen:
            return False
        parent_edges.add(ce)

    return len(parent_edges) == num_vertices - 1
```

### 12.3 Rational Linear Algebra, Rank-Nullity, and Convex Polyhedra

#### Certifying Exact Matrix Rank `r` Over `Q` Without Re-Running Elimination

How do we verify `rank(A) == r` for an `m x n` rational matrix `A` using an independent certificate?
1. **Lower bound `rank(A) >= r`:** Certificate names `r` row indices `R = [i_1, ..., i_r]` and `r` column indices `C = [j_1, ..., j_r]` plus an explicit `r x r` rational inverse matrix `M_inv` of the submatrix `A[R, C]`! Verifier checks `0 <= i_1 < ... < i_r < m`, `0 <= j_1 < ...

< j_r < n`, and `A[R, C] @ M_inv == I_r` over `Fraction`! Since `A[R, C]` has a two-sided inverse, its columns (and therefore the `r` columns of `A`) are linearly independent, proving `rank(A) >= r`!
2. **Upper bound `rank(A) <= r`:** Certificate provides `n - r` linearly independent nullspace vectors `N = [v_1, ..., v_{n-r}]` in `Q^n` (with an `(n - r) x (n - r)` identity or invertible subblock on the non-pivot columns `C_comp`, proving `dim(ker A) >= n - r`) such that `A @ v_k == 0` for every `k`! By Rank-Nullity (`rank(A) + nullity(A) = n`), `nullity(A) >= n - r` forces `rank(A) <= r`!
3. Together, `rank(A) >= r` and `rank(A) <= r` prove `rank(A) == r` via pure matrix-matrix multiplication in `O(m * n * max(r, n - r))` exact `Fraction` operations, sharing zero code with Gaussian elimination!

```python
from __future__ import annotations
from fractions import Fraction


def verify_exact_rank_certificate(
    mat_a: list[list[Fraction]],
    claimed_rank: int,
    pivot_rows: list[int],
    pivot_cols: list[int],
    submatrix_inv: list[list[Fraction]],
    null_basis: list[list[Fraction]],
) -> bool:
    """Certify rank(A) == r via r x r minor inverse (lower bound) + (n-r) independent kernel basis (upper bound)."""
    if not mat_a or not mat_a[0] or type(claimed_rank) is not int:
        return False
    m = len(mat_a)
    n = len(mat_a[0])
    if any(len(row) != n for row in mat_a):
        return False
    if not (0 <= claimed_rank <= min(m, n)):
        return False
    if len(pivot_rows) != claimed_rank or len(pivot_cols) != claimed_rank:
        return False
    if any(pivot_rows[i] >= pivot_rows[i + 1] for i in range(claimed_rank - 1)):
        return False
    if any(pivot_cols[i] >= pivot_cols[i + 1] for i in range(claimed_rank - 1)):
        return False
    if any(not (0 <= r < m) for r in pivot_rows) or any(not (0 <= c < n) for c in pivot_cols):
        return False

    # 1. Lower bound: A[pivot_rows, pivot_cols] @ submatrix_inv == I_r
    if len(submatrix_inv) != claimed_rank or any(len(row) != claimed_rank for row in submatrix_inv):
        return False
    for a_idx in range(claimed_rank):
        r_i = pivot_rows[a_idx]
        for b_idx in range(claimed_rank):
            dot = sum(
                (mat_a[r_i][pivot_cols[k]] * submatrix_inv[k][b_idx] for k in range(claimed_rank)),
                Fraction(0, 1),
            )
            expected = Fraction(1, 1) if a_idx == b_idx else Fraction(0, 1)
            if dot != expected:
                return False

    # 2. Upper bound: (n - r) kernel vectors supported as identity on non-pivot columns
    null_dim = n - claimed_rank
    if len(null_basis) != null_dim or any(len(vec) != n for vec in null_basis):
        return False
    pivot_col_set = set(pivot_cols)
    free_cols = [c for c in range(n) if c not in pivot_col_set]
    for k_idx, vec in enumerate(null_basis):
        # Independence witness: vec restricted to free_cols equals standard basis e_{k_idx}
        for f_idx, c_col in enumerate(free_cols):
            exp_coord = Fraction(1, 1) if k_idx == f_idx else Fraction(0, 1)
            if vec[c_col] != exp_coord:
                return False
        # Kernel equation: A @ vec == 0
        for i in range(m):
            row_val = sum((mat_a[i][j] * vec[j] for j in range(n)), Fraction(0, 1))
            if row_val != Fraction(0, 1):
                return False

    return True
```

### 12.4 Distributive Lattices, Polynomial Identities, and Merkle State Machines

#### Distributive Lattice Absorption and Modularity (`Lean 4.35.0 Init`)

```lean
structure LatticeOps (α : Type) where
  meet : α → α → α
  join : α → α → α
  meet_comm : ∀ x y, meet x y = meet y x
  join_comm : ∀ x y, join x y = join y x
  meet_assoc : ∀ x y z, meet (meet x y) z = meet x (meet y z)
  join_assoc : ∀ x y z, join (join x y) z = join x (join y z)
  absorb_mj : ∀ x y, meet x (join x y) = x
  absorb_jm : ∀ x y, join x (meet x y) = x

theorem lattice_meet_idem {α : Type} (L : LatticeOps α) (x : α) :
    L.meet x x = x := by
  have h1 : L.join x (L.meet x x) = x := L.absorb_jm x x
  have h2 : L.meet x (L.join x (L.meet x x)) = x := L.absorb_mj x (L.meet x x)
  rw [h1] at h2
  exact h2

theorem distributive_implies_modular {α : Type} (L : LatticeOps α)
    (hdist : ∀ x y z, L.join x (L.meet y z) = L.meet (L.join x y) (L.join x z))
    (x y z : α)
    (hxz : L.join x z = z) :
    L.join x (L.meet y z) = L.meet (L.join x y) z := by
  rw [hdist x y z, hxz]
```

#### Commutative Ring Difference-of-Squares and Factor Theorem (`Lean 4.35.0 Init` over `Int`)

```lean
theorem int_diff_of_squares (a b : Int) :
    (a - b) * (a + b) = a * a - b * b := by
  rw [Int.sub_mul, Int.mul_add, Int.mul_add, Int.mul_comm b a]
  omega

/-- Hornet / linear-factor remainder step: `(c * x + d) - (c * r + d) = c * (x - r)`.
    By induction over polynomial degree, `P(x) - P(r)` is divisible by `(x - r)` over `Int`! -/
def evalPolyInt (coeffs : List Int) (x : Int) : Int :=
  match coeffs with
  | [] => 0
  | c :: cs => c + x * evalPolyInt cs x

theorem poly_sub_root_divisible :
    ∀ (coeffs : List Int) (x r : Int),
    ∃ q : Int, evalPolyInt coeffs x - evalPolyInt coeffs r = (x - r) * q
  | [], _, _ => ⟨0, by simp [evalPolyInt]⟩
  | c :: cs, x, r => by
    rcases poly_sub_root_divisible cs x r with ⟨q_tail, htail⟩
    refine ⟨evalPolyInt cs x + r * q_tail, ?_⟩
    change (c + x * evalPolyInt cs x) - (c + r * evalPolyInt cs r)
      = (x - r) * (evalPolyInt cs x + r * q_tail)
    have hsplit :
        (c + x * evalPolyInt cs x) - (c + r * evalPolyInt cs r)
        = (x - r) * evalPolyInt cs x + r * (evalPolyInt cs x - evalPolyInt cs r) := by
      rw [Int.sub_mul, Int.mul_sub]
      omega
    rw [hsplit, htail]
    rw [← Int.mul_assoc r (x - r) q_tail, Int.mul_comm r (x - r), Int.mul_assoc (x - r) r q_tail]
    rw [← Int.mul_add]

theorem poly_root_factor (coeffs : List Int) (x r : Int)
    (hroot : evalPolyInt coeffs r = 0) :
    ∃ q : Int, evalPolyInt coeffs x = (x - r) * q := by
  rcases poly_sub_root_divisible coeffs x r with ⟨q, hq⟩
  rw [hroot, Int.sub_zero] at hq
  exact ⟨q, hq⟩
```

#### Cryptographic Merkle Inclusion and Domain-Separated Leaf/Node Hashing (`Python Exact Bytes`)

A naive Merkle tree that hashes `SHA256(left || right)` for both leaves and internal nodes suffers from second-preimage tree-depth confusion (a 64-byte leaf equals the concatenation of two 32-byte child hashes!). Following RFC 6962 Certificate Transparency domain separation:
- Leaf digest: `SHA256(b"\x00" + leaf_bytes)`
- Internal node digest: `SHA256(b"\x01" + left_digest_32 + right_digest_32)`
- Independent inclusion verifier checks exact byte lengths (`len(sibling) == 32`), direction bit (`0` = sibling on right, `1` = sibling on left), index bounds, and domain-separated recomputation against the committed 64-hex root!

```python
from __future__ import annotations
import hashlib
import hmac


def merkle_leaf_hash(payload: bytes) -> bytes:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return hashlib.sha256(b"\x00" + payload).digest()


def merkle_node_hash(left32: bytes, right32: bytes) -> bytes:
    if len(left32) != 32 or len(right32) != 32:
        raise ValueError("child digests must be 32 bytes")
    return hashlib.sha256(b"\x01" + left32 + right32).digest()


def verify_merkle_inclusion(
    leaf_utf8: str,
    leaf_index: int,
    tree_size: int,
    audit_path_hex: list[tuple[str, str]],
    expected_root_hex: str,
) -> bool:
    """Verify RFC-6962 domain-separated Merkle inclusion proof fail-closed."""
    if type(leaf_index) is not int or type(tree_size) is not int:
        return False
    if tree_size <= 0 or not (0 <= leaf_index < tree_size):
        return False
    if len(expected_root_hex) != 64:
        return False
    try:
        expected_root = bytes.fromhex(expected_root_hex)
    except ValueError:
        return False

    cur = merkle_leaf_hash(leaf_utf8.encode("utf-8"))
    for side, sib_hex in audit_path_hex:
        if side not in ("L", "R") or len(sib_hex) != 64:
            return False
        try:
            sib = bytes.fromhex(sib_hex)
        except ValueError:
            return False
        if side == "L":
            cur = merkle_node_hash(sib, cur)
        else:
            cur = merkle_node_hash(cur, sib)

    return hmac.compare_digest(cur, expected_root)
```

### 12.5 Quick-Check Verification Checklist Before Emitting Any Output

Before returning a proof, exact-math checker, claim audit, or mixed-register report, verify every item in order:

1. **Zone & Tier alignment:** Does the output declare an honest canonical claim tier (`PROVEN`, `VERIFIED`, `KNOWN`, `CONJECTURE`, or `REFUSED`) matching the actual evidence?
2. **Lean 4 escape-hatch zero:** If Lean 4 code appears, does it use stock `Init` only (`strict_init_only`), declare at least one `theorem` or `lemma`, avoid vacuous hypotheses (`False`, `n < 0` on `Nat`, `: True`), and contain zero `sorry`, `admit`, `axiom`, `opaque`, `native_decide`, `implemented_by`, `extern`, `unsafe`, or syntax overrides?
3. **Python exact-math & `-O` safety:** If Python verification code appears, does it use `int` and `fractions.Fraction` only (zero `float` literals, zero `/` operator, zero `float(...)` calls), use a distinct AST skeleton from the generator, avoid `verified = True` defaults, and use explicit `if not ...: raise ValueError(...)` or `return False` instead of `assert`?
4. **Mutation kill resilience:** Would a planted `+1`/`-1` witness perturbation, dropped JSON field, bad 40-char SHA, negative denominator, or swapped tier fail the checker (`>= 80%` kill floor)?
5. **Mandatory boundary disclosures:** Are both `## What is not proved` and `## What you must trust` present, concrete, and accurate?
6. **Mixed-register & prose cleanliness:** Are formal blocks protected with `data-eido-skip` where required, verdict commits written as full 40-character hex SHAs, prose paragraphs under 420 characters, em dashes and AI-tell phrases absent, and external URLs/references deduplicated?

## 13. Extended Lean 4.35.0 `Init` Proof Library and Exact Certificate Reference

This section collects verified stock-`Init` Lean 4.35.0 modules and paired exact-rational Python verifiers covering discrete dynamical invariants, interval-containment proofs, Farey mediant inequalities, integer division-with-remainder uniqueness, list permutation invariants, monotonic Lamport clocks, two-phase commit safety, and division-free rational matrix certificates.

### 13.1 Euclidean Division-Remainder Uniqueness Over `Int` (`Lean 4.35.0 Init`)

```lean
/-- Uniqueness of Euclidean quotient and remainder: if `a = d * q1 + r1 = d * q2 + r2`
    with `0 < d`, `0 <= r1 < d`, and `0 <= r2 < d`, then `q1 = q2` and `r1 = r2`. -/
theorem euclidean_div_mod_unique (a d q1 r1 q2 r2 : Int)
    (hd : 0 < d)
    (heq1 : a = d * q1 + r1)
    (heq2 : a = d * q2 + r2)
    (hr1 : 0 ≤ r1 ∧ r1 < d)
    (hr2 : 0 ≤ r2 ∧ r2 < d) :
    q1 = q2 ∧ r1 = r2 := by
  have hdiff : d * (q1 - q2) = r2 - r1 := by
    rw [Int.mul_sub]
    omega
  by_cases hq_eq : q1 = q2
  · subst hq_eq
    exact ⟨rfl, by omega⟩
  · by_cases hq_gt : q2 < q1
    · have hge1 : 1 ≤ q1 - q2 := by omega
      have hmul : d * 1 ≤ d * (q1 - q2) := Int.mul_le_mul_of_nonneg_left hge1 (by omega)
      rw [Int.mul_one, hdiff] at hmul
      omega
    · have hge1 : 1 ≤ q2 - q1 := by omega
      have hmul : d * 1 ≤ d * (q2 - q1) := Int.mul_le_mul_of_nonneg_left hge1 (by omega)
      have hdiff2 : d * (q2 - q1) = r1 - r2 := by
        rw [Int.mul_sub]
        omega
      rw [Int.mul_one, hdiff2] at hmul
      omega

theorem euclidean_div_mod_inhabited :
    ∃ q r : Int, 29 = 6 * q + r ∧ 0 ≤ r ∧ r < 6 :=
  ⟨4, 5, by omega, by omega, by omega⟩
```

### 13.2 Farey Mediant Inequality Over Positive-Denominator Rationals (`Lean 4.35.0 Init`)

For `a / b < c / d` with `0 < b` and `0 < d`, the mediant `(a + c) / (b + d)` satisfies `a / b < (a + c) / (b + d)` and `(a + c) / (b + d) < c / d` via pure cross-multiplication (`a * (b + d) < (a + c) * b` and `(a + c) * d < c * (b + d)`):

```lean
theorem mediant_strict_between (a b c d : Int)
    (hb : 0 < b) (hd : 0 < d)
    (hlt : a * d < c * b) :
    a * (b + d) < (a + c) * b ∧ (a + c) * d < c * (b + d) := by
  have hleft : a * (b + d) < (a + c) * b := by
    rw [Int.mul_add, Int.add_mul, Int.mul_comm c b, Int.mul_comm b c]
    omega
  have hright : (a + c) * d < c * (b + d) := by
    rw [Int.add_mul, Int.mul_add, Int.mul_comm c b, Int.mul_comm b c]
    omega
  exact ⟨hleft, hright⟩

theorem mediant_witness :
    (1 : Int) * (3 + 5) < (1 + 2) * 3 ∧ ((1 : Int) + 2) * 5 < 2 * (3 + 5) :=
  mediant_strict_between 1 3 2 5 (by omega) (by omega) (by omega)
```

### 13.3 Lamport Logical ClockCausality Invariant (`Lean 4.35.0 Init`)

```lean
def localTick (clock : Nat) : Nat :=
  clock + 1

def receiveTick (localClock senderTimestamp : Nat) : Nat :=
  (if localClock < senderTimestamp then senderTimestamp else localClock) + 1

theorem localTick_strict_inc (c : Nat) : c < localTick c := by
  unfold localTick
  omega

theorem receiveTick_strictly_dominates_both (localClock senderTimestamp : Nat) :
    localClock < receiveTick localClock senderTimestamp
    ∧ senderTimestamp < receiveTick localClock senderTimestamp := by
  unfold receiveTick
  split <;> omega

theorem causal_chain_three_events (t1 t2 t3 local2 local3 : Nat)
    (h12 : t2 = receiveTick local2 t1)
    (h23 : t3 = receiveTick local3 t2) :
    t1 + 2 ≤ t3 := by
  have hb1 : t1 < t2 := by
    rw [h12]
    exact (receiveTick_strictly_dominates_both local2 t1).2
  have hb2 : t2 < t3 := by
    rw [h23]
    exact (receiveTick_strictly_dominates_both local3 t2).2
  omega
```

### 13.4 Two-Phase Commit (`2PC`) Atomic Decision Safety (`Lean 4.35.0 Init`)

```lean
inductive Vote where
  | yes
  | no
deriving DecidableEq, Repr

inductive CoordinatorDecision where
  | pending
  | commit
  | abort
deriving DecidableEq, Repr

def decideCoordinator (votes : List Vote) (expectedParticipants : Nat) : CoordinatorDecision :=
  if votes.length == expectedParticipants && expectedParticipants > 0 && votes.all (fun v => v == Vote.yes) then
    CoordinatorDecision.commit
  else
    CoordinatorDecision.abort

/-- Safety: Coordinator commits ONLY when the participant cohort is non-empty, complete,
    and EVERY participant voted `Vote.yes`. -/
theorem decideCoordinator_commit_safety (votes : List Vote) (n : Nat) :
    decideCoordinator votes n = CoordinatorDecision.commit →
    0 < n ∧ votes.length = n ∧ ∀ v ∈ votes, v = Vote.yes := by
  unfold decideCoordinator
  by_cases hcond : (votes.length == n && decide (n > 0) && votes.all (fun v => v == Vote.yes)) = true
  · simp [hcond]
    have hc : (votes.length == n && decide (n > 0) && votes.all (fun v => v == Vote.yes)) = true := hcond
    simp [Bool.and_eq_true] at hc
    rcases hc with ⟨⟨hlen, hpos⟩, hall⟩
    refine ⟨hpos, hlen, ?_⟩
    intro v hv
    exact hall v hv
  · simp [hcond]

/-- Non-vacuity: A complete unanimous cohort of `Vote.yes` produces `CoordinatorDecision.commit`. -/
theorem decideCoordinator_unanimous_yes :
    decideCoordinator [Vote.yes, Vote.yes, Vote.yes] 3 = CoordinatorDecision.commit := rfl

/-- Refusal safety: Even one `Vote.no` forces `CoordinatorDecision.abort`. -/
theorem decideCoordinator_veto_no (pre post : List Vote) (n : Nat) :
    decideCoordinator (pre ++ [Vote.no] ++ post) n = CoordinatorDecision.abort := by
  unfold decideCoordinator
  have hnot : (pre ++ [Vote.no] ++ post).all (fun v => v == Vote.yes) = false := by
    apply List.all_eq_false.mpr
    refine ⟨Vote.no, ?_, by decide⟩
    simp
  rw [hnot]
  simp
```

### 13.5 Exact Absorbing Markov Chain Hitting-Probability Linear Certificate (`Python Exact Fraction`)

For a finite Markov chain with transient states `T` and absorbing states `A`, the probability `h[i]` of absorption into target subset `A_goal` starting from state `i` is the unique solution to:
- `h[a] == 1` for `a in A_goal`, `h[a] == 0` for `a in A - A_goal`
- `h[i] == sum(P[i][j] * h[j] for j in range(n))` for every transient state `i in T`, PROVIDED every transient state can reach `A` (`I - Q` is nonsingular, certified by a rank/inverse witness `(I - Q) @ M_fund == I_|T|` where `M_fund` is the fundamental matrix!).
Checking `M_fund @ (I - Q) == I_|T|` AND `h_T == M_fund @ b_goal` certifies exact hitting probabilities and mean absorption steps in `O(|T|^3)` exact rational dot products without iterative convergence cutoffs!
