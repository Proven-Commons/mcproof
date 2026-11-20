def _is_p(x: int) -> bool:
    if x < 2:
        return False
    f = 2
    while f * f <= x:
        if x % f == 0:
            return False
        f += 1
    return True

def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    phi = cert.get('phi')
    pp = cert.get('prime_powers')
    if type(n) is not int or type(phi) is not int or n < 2 or not isinstance(pp, list) or len(pp) == 0:
        return False
    n_prod = 1
    phi_prod = 1
    prev = 1
    for entry in pp:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            return False
        p, k = entry[0], entry[1]
        if type(p) is not int or type(k) is not int or k < 1 or p <= prev or not _is_p(p):
            return False
        prev = p
        pk = p ** k
        n_prod *= pk
        phi_prod *= pk - (pk // p)
    return n_prod == n and phi_prod == phi
