def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    edges = inst.get('edges')
    m_ids = cert.get('matching_edge_ids')
    vc = cert.get('vertex_cover')
    if type(n) is not int or n < 1 or not all(isinstance(x, list) for x in (edges, m_ids, vc)):
        return False
    for e in edges:
        if not isinstance(e, (list, tuple)) or len(e) != 2 or type(e[0]) is not int or type(e[1]) is not int:
            return False
        if not (0 <= e[0] < n and 0 <= e[1] < n) or e[0] == e[1]:
            return False
    matched_verts: set[int] = set()
    seen_ids: set[int] = set()
    for idx in m_ids:
        if type(idx) is not int or not (0 <= idx < len(edges)) or idx in seen_ids:
            return False
        seen_ids.add(idx)
        u, v = edges[idx]
        if u in matched_verts or v in matched_verts:
            return False
        matched_verts.add(u)
        matched_verts.add(v)
    if vc != sorted(matched_verts) or len(vc) != 2 * len(m_ids):
        return False
    cover_set = set(vc)
    return all((e[0] in cover_set or e[1] in cover_set) for e in edges)
