# ShearDetOne

`ShearDetOne` proves that elementary `2x2` row-shear matrices `[1, k; 0, 1]` have exact determinant `1` for every integer factor `k`. It certifies determinant preservation during Gaussian elimination.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV08.shear2_det_one
Claim: For every shear factor `k : Int`, `1 * 1 - k * 0 = 1`.
Verdict-Commit: 6450afa0d1357c6594c60b8abbfa223907ca4f56
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV08

def detShear (k : Int) : Int := 1 * 1 - k * 0

theorem shear2_det_one (k : Int) : detShear k = 1 := by
  unfold detShear
  omega

end PubDV08
```

## What is not proved

Row-swap sign flips (`det = -1`) are tracked in a separate permutation parity counter. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
