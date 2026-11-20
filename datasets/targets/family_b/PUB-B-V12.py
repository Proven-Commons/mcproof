def verify(inst: dict, cert: dict) -> bool:
    ns = inst.get('num_states')
    init_s = inst.get('init')
    trans = inst.get('transitions')
    bad_s = inst.get('bad')
    inv = cert.get('inductive_set')
    if type(ns) is not int or ns < 1 or not all(isinstance(x, list) for x in (init_s, trans, bad_s, inv)):
        return False
    if any(type(x) is not int or not (0 <= x < ns) for x in init_s + bad_s + inv):
        return False
    if inv != sorted(set(inv)):
        return False
    inv_set = set(inv)
    if not set(init_s).issubset(inv_set):
        return False
    if len(inv_set & set(bad_s)) > 0:
        return False
    for edge in trans:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            return False
        u, v = edge[0], edge[1]
        if type(u) is not int or type(v) is not int or not (0 <= u < ns and 0 <= v < ns):
            return False
        if u in inv_set and v not in inv_set:
            return False
    return True
