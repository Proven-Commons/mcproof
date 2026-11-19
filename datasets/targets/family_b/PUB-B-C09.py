def verify(inst: dict, cert: dict) -> bool:
    nl = inst.get('n_left')
    nr = inst.get('n_right')
    adj = inst.get('adj')
    ok_perf = cert.get('has_left_perfect')
    ml = cert.get('match_right_of_left')
    hsub = cert.get('hall_subset')
    if type(nl) is not int or type(nr) is not int or nl < 1 or nr < 1 or type(ok_perf) is not bool:
        return False
    if not all(isinstance(x, list) for x in (adj, ml, hsub)) or len(adj) != nl:
        return False
    if ok_perf:
        if len(hsub) != 0 or len(ml) != nl:
            return False
        seen_r = set()
        for u in range(nl):
            v = ml[u]
            if type(v) is not int or not (0 <= v < nr) or v not in adj[u] or v in seen_r:
                return False
            seen_r.add(v)
        return True
    if len(ml) != 0 or len(hsub) == 0:
        return False
    prev = -1
    nbrs = set()
    for u in hsub:
        if type(u) is not int or not (0 <= u < nl) or u <= prev:
            return False
        prev = u
        nbrs.update(adj[u])
    return len(nbrs) < len(hsub)
