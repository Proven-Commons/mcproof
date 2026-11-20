def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    edges = inst.get('edges')
    bip = cert.get('bipartite')
    colors = cert.get('colors')
    cyc = cert.get('odd_cycle')
    if type(n) is not int or n < 1 or not isinstance(edges, list) or type(bip) is not bool:
        return False
    if not isinstance(colors, list) or not isinstance(cyc, list):
        return False
    edge_set = set()
    for e in edges:
        if not isinstance(e, (list, tuple)) or len(e) != 2:
            return False
        u, v = e[0], e[1]
        if type(u) is not int or type(v) is not int or not (0 <= u < n and 0 <= v < n):
            return False
        edge_set.add((u, v))
        edge_set.add((v, u))
    if bip:
        if len(cyc) != 0 or len(colors) != n:
            return False
        if any(type(c) is not int or c not in (0, 1) for c in colors):
            return False
        return all(colors[e[0]] != colors[e[1]] for e in edges)
    if len(colors) != 0 or len(cyc) < 3 or len(cyc) % 2 == 0:
        return False
    if any(type(v) is not int or not (0 <= v < n) for v in cyc) or len(set(cyc)) != len(cyc):
        return False
    k = len(cyc)
    return all((cyc[i], cyc[(i + 1) % k]) in edge_set for i in range(k))
