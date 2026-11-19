def verify(inst: dict, cert: dict) -> bool:
    a, b, c = inst.get('a'), inst.get('b'), inst.get('c')
    lo, hi = inst.get('x_lo'), inst.get('x_hi')
    g = cert.get('gcd')
    u, v = cert.get('bezout_u'), cert.get('bezout_v')
    sols = cert.get('solutions')
    if not all(type(z) is int for z in (a, b, c, lo, hi, g, u, v)) or not isinstance(sols, list):
        return False
    if a <= 0 or b <= 0 or lo > hi or g <= 0:
        return False
    if a % g != 0 or b % g != 0 or a * u + b * v != g:
        return False
    if c % g != 0:
        return len(sols) == 0
    stride = b // g
    x0 = (u * (c // g)) % stride
    first_x = lo + ((x0 - lo) % stride)
    if first_x > hi:
        return len(sols) == 0
    expected_count = ((hi - first_x) // stride) + 1
    if len(sols) != expected_count:
        return False
    for idx, pair in enumerate(sols):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        px, py = pair[0], pair[1]
        if type(px) is not int or type(py) is not int:
            return False
        if px != first_x + idx * stride or a * px + b * py != c:
            return False
    return True
