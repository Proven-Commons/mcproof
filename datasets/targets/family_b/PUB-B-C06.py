def _odd_prime(p: int) -> bool:
    if p < 3 or p % 2 == 0:
        return False
    d = 3
    while d * d <= p:
        if p % d == 0:
            return False
        d += 2
    return True

def verify(inst: dict, cert: dict) -> bool:
    a = inst.get('a')
    p = inst.get('p')
    is_qr = cert.get('is_qr')
    roots = cert.get('roots')
    if type(a) is not int or type(p) is not int or type(is_qr) is not bool or not isinstance(roots, list):
        return False
    if not _odd_prime(p) or a % p == 0:
        return False
    leg = pow(a, (p - 1) // 2, p)
    if is_qr:
        if leg != 1 or len(roots) != 2:
            return False
        r1, r2 = roots[0], roots[1]
        if type(r1) is not int or type(r2) is not int:
            return False
        return 0 < r1 < r2 < p and r1 + r2 == p and (r1 * r1 - a) % p == 0 and (r2 * r2 - a) % p == 0
    return leg == p - 1 and len(roots) == 0
