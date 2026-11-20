def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    edges = inst.get('edges')
    tedges = cert.get('tree_edges')
    par = cert.get('parent')
    dep = cert.get('depth')
    tw = cert.get('total_weight')
    if type(n) is not int or n < 1 or type(tw) is not int:
        return False
    if not all(isinstance(x, list) for x in (edges, tedges, par, dep)):
        return False
    if len(tedges) != n - 1 or len(set(tedges)) != n - 1 or len(par) != n or len(dep) != n:
        return False
    if par[0] != -1 or dep[0] != 0:
        return False
    chosen_pairs = set()
    w_sum = 0
    for idx in tedges:
        if type(idx) is not int or not (0 <= idx < len(edges)):
            return False
        u, v, w = edges[idx]
        if u == v:
            return False
        pair = (u, v) if u < v else (v, u)
        if pair in chosen_pairs:
            return False
        chosen_pairs.add(pair)
        w_sum += w
    if w_sum != tw:
        return False
    parent_pairs = set()
    for v in range(1, n):
        pv, dv = par[v], dep[v]
        if type(pv) is not int or type(dv) is not int or not (0 <= pv < n):
            return False
        if dv != dep[pv] + 1 or dv <= 0:
            return False
        parent_pairs.add((pv, v) if pv < v else (v, pv))
    return parent_pairs == chosen_pairs
