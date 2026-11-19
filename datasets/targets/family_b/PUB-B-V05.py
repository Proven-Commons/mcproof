def verify(inst: dict, cert: dict) -> bool:
    perm = inst.get('perm')
    is_der = cert.get('is_derangement')
    cycs = cert.get('cycles')
    if not isinstance(perm, list) or len(perm) < 2 or type(is_der) is not bool or not isinstance(cycs, list):
        return False
    n = len(perm)
    if any(type(v) is not int for v in perm) or set(perm) != set(range(n)):
        return False
    rebuilt = [-1] * n
    seen: set[int] = set()
    prev_min = -1
    min_cyc_len = n + 1
    for cyc in cycs:
        if not isinstance(cyc, list) or len(cyc) == 0:
            return False
        if any(type(x) is not int or not (0 <= x < n) or x in seen for x in cyc):
            return False
        if cyc[0] != min(cyc) or cyc[0] <= prev_min:
            return False
        prev_min = cyc[0]
        seen.update(cyc)
        k = len(cyc)
        if k < min_cyc_len:
            min_cyc_len = k
        for i in range(k):
            rebuilt[cyc[i]] = cyc[(i + 1) % k]
    if len(seen) != n or rebuilt != perm:
        return False
    return is_der == (min_cyc_len >= 2)
