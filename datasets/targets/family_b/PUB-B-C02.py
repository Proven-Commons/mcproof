def _coprime_int(u: int, v: int) -> bool:
    while v != 0:
        u, v = v, u % v
    return u == 1

def verify(inst: dict, cert: dict) -> bool:
    rems = inst.get('remainders')
    mods = inst.get('moduli')
    x = cert.get('x')
    big_m = cert.get('M')
    if not isinstance(rems, list) or not isinstance(mods, list) or len(rems) == 0 or len(rems) != len(mods):
        return False
    if type(x) is not int or type(big_m) is not int:
        return False
    prod_m = 1
    n = len(mods)
    for i in range(n):
        mi = mods[i]
        ri = rems[i]
        if type(mi) is not int or type(ri) is not int or mi <= 1:
            return False
        if x % mi != ri % mi:
            return False
        for j in range(i + 1, n):
            if type(mods[j]) is not int or mods[j] <= 1 or not _coprime_int(mi, mods[j]):
                return False
        prod_m *= mi
    return big_m == prod_m and 0 <= x < big_m
