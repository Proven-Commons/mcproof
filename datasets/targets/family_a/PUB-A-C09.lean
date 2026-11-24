namespace PubAC09

def deg (v : Nat) : List (Nat × Nat) → Nat
  | [] => 0
  | (a, b) :: es => (if a == v then 1 else 0) + (if b == v then 1 else 0) + deg v es

def edgeEndpointCount : List (Nat × Nat) → Nat
  | [] => 0
  | _ :: es => 2 + edgeEndpointCount es

theorem handshaking_degSum (es : List (Nat × Nat)) : edgeEndpointCount es = 2 * es.length := by
  induction es with
  | nil => rfl
  | cons _ tail ih =>
    simp only [edgeEndpointCount, List.length_cons]
    omega

theorem deg_append (v : Nat) (es1 es2 : List (Nat × Nat)) :
    deg v (es1 ++ es2) = deg v es1 + deg v es2 := by
  induction es1 with
  | nil => simp [deg]
  | cons hd tail ih =>
    cases hd with
    | mk a b =>
      simp only [List.cons_append, deg, ih]
      omega

end PubAC09
