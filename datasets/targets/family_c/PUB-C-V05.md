Claim-Tier: CONJECTURE

```json
{
  "id": "audit-comb-tree-custom-axiom",
  "source_repo": "https://github.com/example/audit-comb-tree-custom-axiom",
  "source_commit": "56d46b6edf78fa1bbd3cb7152000db49a76a4baa",
  "claim": "Every finite connected acyclic graph on n >= 1 vertices has exactly n - 1 edges.",
  "claim_link": "https://example.org/audit-comb-tree-custom-axiom.pdf#page=2",
  "lab_statement": {
    "file": "Proofs/TreeEdges.lean",
    "name": "tree_edges_pred",
    "lean": "theorem tree_edges_pred (G : FinGraph) (hconn : Connected G) (hacyc : Acyclic G) : G.edges.length + 1 = G.numVertices"
  },
  "independent_statement": {
    "lean": "theorem tree_edges_pred_ind (G : FinGraph) (hconn : Connected G) (hacyc : Acyclic G) : G.edges.length + 1 = G.numVertices",
    "source": "written for this audit",
    "author": "auditor-seat"
  },
  "tool": {
    "name": "comparator",
    "version": "0.1.0",
    "lean_version": "4.35.0"
  },
  "command": "lake comparator --paranoid",
  "output_summary": "`lake comparator --paranoid` rejected unpermitted custom axiom `TreeEdges.acyclic_leaf_ax`",
  "axioms": [
    "propext",
    "TreeEdges.acyclic_leaf_ax"
  ],
  "verdict": "does not build",
  "reviewer": null
}
```

## What is not proved

- `lake comparator --paranoid` rejected unpermitted custom axiom `TreeEdges.acyclic_leaf_ax`.
- Real-world deployment behavior outside the formal Lean statement `tree_edges_pred`.

## What you must trust

- Lean 4.35.0 kernel and `lake comparator --paranoid` export checking.
- Human adequacy review of `independent_statement` before external publication.
