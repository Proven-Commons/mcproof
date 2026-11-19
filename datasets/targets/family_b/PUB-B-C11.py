def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    edges = inst.get('edges')
    is_dag = cert.get('is_dag')
    topo = cert.get('topo_order')
    cyc = cert.get('cycle')
    if type(n) is not int or n < 1 or type(is_dag) is not bool:
        return False
    if not all(isinstance(x, list) for x in (edges, topo, cyc)):
        return False
    edge_set = set()
    for e in edges:
        if not isinstance(e, (list, tuple)) or len(e) != 2:
            return False
        u, v = e[0], e[1]
        if type(u) is not int or type(v) is not int or not (0 <= u < n and 0 <= v < n):
            return False
        edge_set.add((u, v))
    if is_dag:
        if len(cyc) != 0 or len(topo) != n:
            return False
        if any(type(v) is not int for v in topo) or set(topo) != set(range(n)):
            return False
        pos = {v: idx for idx, v in enumerate(topo)}
        return all(pos[u] < pos[v] for (u, v) in edge_set)
    if len(topo) != 0 or len(cyc) == 0:
        return False
    if any(type(v) is not int or not (0 <= v < n) for v in cyc) or len(set(cyc)) != len(cyc):
        return False
    k = len(cyc)
    return all((cyc[i], cyc[(i + 1) % k]) in edge_set for i in range(k))
