def verify(inst: dict, cert: dict) -> bool:
    a = inst.get('a')
    b = inst.get('b')
    g = cert.get('gcd')
    lcm_val = cert.get('lcm')
    u = cert.get('u')
    v = cert.get('v')
    s = cert.get('s')
    t = cert.get('t')
    if not all(type(z) is int for z in (a, b, g, lcm_val, u, v, s, t)):
        return False
    if a <= 0 or b <= 0 or g <= 0 or lcm_val <= 0 or u <= 0 or v <= 0:
        return False
    if g * u != a or g * v != b:
        return False
    if s * u + t * v != 1:
        return False
    return a * b == g * lcm_val and lcm_val == g * u * v
