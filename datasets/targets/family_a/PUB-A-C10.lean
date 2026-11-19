namespace PubAC10

def zipAdd : List Nat → List Nat → List Nat
  | x :: xs, y :: ys => (x + y) :: zipAdd xs ys
  | _, _ => []

def sumList : List Nat → Nat
  | [] => 0
  | x :: xs => x + sumList xs

theorem sumList_append (xs ys : List Nat) : sumList (xs ++ ys) = sumList xs + sumList ys := by
  induction xs with
  | nil => simp [sumList]
  | cons x xs ih =>
    simp only [List.cons_append, sumList, ih]
    omega

theorem zipAdd_adj (a : Nat) (row : List Nat) :
    sumList (zipAdd (a :: row) (row ++ [0])) = a + 2 * sumList row := by
  induction row generalizing a with
  | nil =>
    simp only [List.nil_append, zipAdd, sumList]
  | cons b rest ih =>
    simp only [List.cons_append, zipAdd, sumList]
    have hrest := ih b
    omega

theorem zipAdd_zero_sides (row : List Nat) :
    sumList (zipAdd (0 :: row) (row ++ [0])) = 2 * sumList row := by
  have h := zipAdd_adj 0 row
  omega

end PubAC10
