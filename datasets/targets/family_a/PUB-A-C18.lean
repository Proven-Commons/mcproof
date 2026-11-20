namespace PubAC18

def ratEq (n1 d1 n2 d2 : Int) : Prop := n1 * d2 = n2 * d1
def ratAddNum (n1 d1 n2 d2 : Int) : Int := n1 * d2 + n2 * d1
def ratAddDen (d1 d2 : Int) : Int := d1 * d2

theorem ratEq_symm (n1 d1 n2 d2 : Int) (h : ratEq n1 d1 n2 d2) : ratEq n2 d2 n1 d1 := by
  exact h.symm

theorem ratAdd_comm_eq (n1 d1 n2 d2 : Int) :
    ratEq (ratAddNum n1 d1 n2 d2) (ratAddDen d1 d2) (ratAddNum n2 d2 n1 d1) (ratAddDen d2 d1) := by
  unfold ratEq ratAddNum ratAddDen
  rw [Int.add_comm (n1 * d2) (n2 * d1), Int.mul_comm d2 d1]

end PubAC18
