def _is_prime_int(p: int) -> bool:
    if p < 2:
        return False
    if p in (2, 3):
        return True
    if p % 2 == 0 or p % 3 == 0:
        return False
    k = 5
    while k * k <= p:
        if p % k == 0 or p % (k + 2) == 0:
            return False
        k += 6
    return True

def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('n')
    facs = cert.get('factors')
    if type(n) is not int or n < 2 or not isinstance(facs, list) or len(facs) == 0:
        return False
    acc = 1
    prev_p = 1
    for item in facs:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return False
        p, exp = item[0], item[1]
        if type(p) is not int or type(exp) is not int or exp < 1:
            return False
        if p <= prev_p or not _is_prime_int(p):
            return False
        prev_p = p
        acc *= p ** exp
    return acc == n
