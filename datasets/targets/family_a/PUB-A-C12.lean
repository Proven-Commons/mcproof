namespace PubAC12

inductive TreeTrace
  | root : TreeTrace
  | attachLeaf : TreeTrace → TreeTrace

def numVertices : TreeTrace → Nat
  | .root => 1
  | .attachLeaf t => numVertices t + 1

def numEdges : TreeTrace → Nat
  | .root => 0
  | .attachLeaf t => numEdges t + 1

theorem tree_vertices_eq_edges_add_one (t : TreeTrace) : numVertices t = numEdges t + 1 := by
  induction t with
  | root => rfl
  | attachLeaf sub ih =>
    simp only [numVertices, numEdges, ih]

end PubAC12
