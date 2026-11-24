# CreditFlow

`CreditFlow` verifies receiver-credit flow control across send and replenish events. It proves `credits + inflight = maxWindow` holds across guarded transitions, for transport-protocol checkers.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDC22.credit_conservation
Claim: Sending 1 frame when `credits > 0` and replenishing 1 credit when `inflight > 0` both preserve `credits + inflight = win`.
Verdict-Commit: 133061b41c0feb319e0108ff6a2d708d21efc5d1
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDC22

structure Flow where
  win : Nat
  credits : Nat
  inflight : Nat

def flowInv (f : Flow) : Prop := f.credits + f.inflight = f.win
def onSend (f : Flow) : Flow := if f.credits > 0 then ⟨f.win, f.credits - 1, f.inflight + 1⟩ else f
def onAck (f : Flow) : Flow := if f.inflight > 0 then ⟨f.win, f.credits + 1, f.inflight - 1⟩ else f

theorem credit_conservation (f : Flow) (h : flowInv f) :
    flowInv (onSend f) ∧ flowInv (onAck f) ∧ (onSend f).inflight ≤ f.win := by
  refine ⟨?_, ?_, ?_⟩
  · unfold onSend; split <;> (simp only [flowInv] at *; omega)
  · unfold onAck; split <;> (simp only [flowInv] at *; omega)
  · unfold onSend; split <;> (simp only [flowInv] at *; omega)

end PubDC22
```

## What is not proved

Packet payload corruption in transit must be checked by a separate checksum layer. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
