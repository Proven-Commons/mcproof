# LatchTerminal

`LatchTerminal` proves irreversibility of an emergency abort latch in safety-critical state controllers. Once `aborted = true`, no subsequent input event can clear it, for control-loop reviewers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC24.abortLatch_irreversible
Claim: Transition `stepLatch aborted trip := aborted || trip` guarantees `aborted = true -> stepLatch aborted trip = true`.
Verdict-Commit: ecd5051e7891e82d16ba6201c900fa70a3093098
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC24

def stepLatch (aborted trip : Bool) : Bool := aborted || trip

theorem abortLatch_irreversible (aborted trip : Bool) (h : aborted = true) :
    stepLatch aborted trip = true := by
  unfold stepLatch
  rw [h]
  rfl

end PubDC24
```

## What is not proved

Electrical sensor latency prior to raising `trip = true` lies outside the discrete transition proof. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
