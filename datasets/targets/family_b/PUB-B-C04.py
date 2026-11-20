def _check_prime(n: int) -> bool:
    if n < 2:
        return False
    k = 2
    while k * k <= n:
        if n % k == 0:
            return False
        k += 1
    return True

def verify(inst: dict, cert: dict) -> bool:
    a = inst.get('a')
    m = inst.get('m')
    ord_d = cert.get('order')
    pdivs = cert.get('prime_divisors')
    if not all(type(v) is int for v in (a, m, ord_d)) or not isinstance(pdivs, list):
        return False
    if m <= 2 or ord_d < 1 or pow(a, ord_d, m) != 1:
        return False
    reduced = ord_d
    last_q = 1
    for q in pdivs:
        if type(q) is not int or q <= last_q or not _check_prime(q):
            return False
        if reduced % q != 0:
            return False
        while reduced % q == 0:
            reduced //= q
        if pow(a, ord_d // q, m) == 1:
            return False
        last_q = q
    return reduced == 1
