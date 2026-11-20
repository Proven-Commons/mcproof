namespace PubAV09

structure Vec3 where
  x : Int
  y : Int
  z : Int

def add3 (u v : Vec3) : Vec3 := ⟨u.x + v.x, u.y + v.y, u.z + v.z⟩

def dot3 (u v : Vec3) : Int := u.x * v.x + u.y * v.y + u.z * v.z

theorem dot3_comm (u v : Vec3) : dot3 u v = dot3 v u := by
  unfold dot3
  rw [Int.mul_comm u.x v.x, Int.mul_comm u.y v.y, Int.mul_comm u.z v.z]

theorem dot3_bilinear (u v w : Vec3) : dot3 (add3 u v) w = dot3 u w + dot3 v w := by
  unfold dot3 add3
  simp only [Int.add_mul]
  omega

end PubAV09
