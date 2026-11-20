namespace PubAC22

structure Ring3 where
  t0 : Nat
  t1 : Nat
  t2 : Nat

def oneToken (r : Ring3) : Prop := r.t0 + r.t1 + r.t2 = 1

inductive Hop
  | h01
  | h12
  | h20

def stepRing (r : Ring3) : Hop → Ring3
  | .h01 => if r.t0 > 0 then ⟨r.t0 - 1, r.t1 + 1, r.t2⟩ else r
  | .h12 => if r.t1 > 0 then ⟨r.t0, r.t1 - 1, r.t2 + 1⟩ else r
  | .h20 => if r.t2 > 0 then ⟨r.t0 + 1, r.t1, r.t2 - 1⟩ else r

theorem stepRing_oneToken (r : Ring3) (hp : Hop) (h : oneToken r) :
    oneToken (stepRing r hp) := by
  cases hp <;> simp only [stepRing] <;> split <;> (simp only [oneToken] at *; omega)

theorem fold_oneToken (r : Ring3) (hops : List Hop) (h : oneToken r) :
    oneToken (hops.foldl stepRing r) := by
  induction hops generalizing r with
  | nil => exact h
  | cons hp rest ih =>
    exact ih (stepRing r hp) (stepRing_oneToken r hp h)

theorem ring3_mutex_trace (r : Ring3) (hops : List Hop) (h : oneToken r) :
    let r' := hops.foldl stepRing r; oneToken r' ∧ r'.t0 ≤ 1 ∧ r'.t1 ≤ 1 ∧ r'.t2 ≤ 1 := by
  have ho : oneToken (hops.foldl stepRing r) := fold_oneToken r hops h
  unfold oneToken at ho
  refine ⟨ho, by omega, by omega, by omega⟩

end PubAC22
