def verify(inst: dict, cert: dict) -> bool:
    a = inst.get('a')
    b = inst.get('b')
    g = cert.get('g')
    x = cert.get('x')
    y = cert.get('y')
    if not all(type(v) is int for v in (a, b, g, x, y)):
        return False
    if a <= 0 or b <= 0 or g <= 0:
        return False
    if a % g != 0 or b % g != 0:
        return False
    return a * x + b * y == g
