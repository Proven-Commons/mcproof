# TraceAdd

`TraceAdd` checks linearity of the matrix trace on exact `2x2` integer matrices. It proves `trace(A + B) = trace(A) + trace(B)`, for exact linear-algebra library maintainers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC13.trace2_additive
Claim: Entrywise addition of two `2x2` integer matrices preserves exact trace additivity.
Verdict-Commit: d6b3f2d5061fb24bec8c65b39845b98e1bc70ca7
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC13

structure M2 where
  a11 : Int
  a12 : Int
  a21 : Int
  a22 : Int

def tr2 (M : M2) : Int := M.a11 + M.a22
def addM2 (A B : M2) : M2 := ⟨A.a11 + B.a11, A.a12 + B.a12, A.a21 + B.a21, A.a22 + B.a22⟩

theorem trace2_additive (A B : M2) : tr2 (addM2 A B) = tr2 A + tr2 B := by
  simp only [tr2, addM2]
  omega

end PubDC13
```

## What is not proved

Eigenvalue invariance under similarity transforms over `Q` is not proved in this module. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
