def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    edges = inst.get('edges')
    verts = cert.get('vertices')
    eord = cert.get('edge_order')
    if type(n) is not int or n < 1 or not all(isinstance(x, list) for x in (edges, verts, eord)) or len(edges) == 0:
        return False
    m = len(edges)
    if len(eord) != m or len(verts) != m + 1:
        return False
    if any(type(v) is not int or not (0 <= v < n) for v in verts):
        return False
    if verts[0] != 0 or verts[-1] != 0:
        return False
    if any(type(eid) is not int for eid in eord) or set(eord) != set(range(m)):
        return False
    for step_i, eid in enumerate(eord):
        e = edges[eid]
        if not isinstance(e, (list, tuple)) or len(e) != 2:
            return False
        a, b = verts[step_i], verts[step_i + 1]
        u, v = e[0], e[1]
        if not ((a == u and b == v) or (a == v and b == u)):
            return False
    return True
