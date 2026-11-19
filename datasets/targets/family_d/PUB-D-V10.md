# TokenPairSwap

`TokenPairSwap` checks conservation of total tokens across a symmetric two-peer exchange `(a, b) -> (b, a)`. It backs peer-handoff state auditors.

<div class="formal-claim" data-eido-skip>
Claim-Tier: PROVEN
Theorem: PubDV10.swap_conserves_sum
Claim: Swapping state `(a, b)` to `(b, a)` preserves total token sum `b + a = a + b`.
Verdict-Commit: 76a0f69049cd159073cad875fa9de6a32cf1e274
Permitted-Axioms: propext, Classical.choice, Quot.sound
</div>

```lean
namespace PubDV10

def swapPeers (p : Nat × Nat) : Nat × Nat := (p.2, p.1)

theorem swap_conserves_sum (p : Nat × Nat) : (swapPeers p).1 + (swapPeers p).2 = p.1 + p.2 := by
  unfold swapPeers
  omega

end PubDV10
```

## What is not proved

Message loss during asynchronous non-atomic swap over a network requires a two-phase handshake. Execution speed and host memory limits also sit outside the logical kernel.

## What you must trust

You must trust the Lean 4.35.0 kernel, external export checkers, the compiler, the runtime, and the host hardware.
