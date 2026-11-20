from fractions import Fraction

def _to_reduced_frac(pair: object) -> Fraction | None:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    num, den = pair[0], pair[1]
    if type(num) is not int or type(den) is not int or den <= 0:
        return None
    f = Fraction(num, den)
    if f.numerator != num or f.denominator != den:
        return None
    return f

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    vec_b = inst.get('b')
    vec_c = inst.get('c')
    rx = cert.get('x')
    ry = cert.get('y')
    robj = _to_reduced_frac(cert.get('obj'))
    if robj is None or not all(isinstance(z, list) for z in (mat_a, vec_b, vec_c, rx, ry)):
        return False
    if len(mat_a) == 0 or len(vec_c) == 0:
        return False
    m, n = len(mat_a), len(vec_c)
    if len(vec_b) != m or len(rx) != n or len(ry) != m:
        return False
    if any(not isinstance(r, list) or len(r) != n or any(type(v) is not int for v in r) for r in mat_a):
        return False
    if any(type(v) is not int for v in vec_b) or any(type(v) is not int for v in vec_c):
        return False
    x_vec = [_to_reduced_frac(p) for p in rx]
    y_vec = [_to_reduced_frac(p) for p in ry]
    if any(v is None or v < 0 for v in x_vec) or any(v is None or v < 0 for v in y_vec):
        return False
    for i in range(m):
        if sum(Fraction(mat_a[i][j], 1) * x_vec[j] for j in range(n)) < Fraction(vec_b[i], 1):
            return False
    for j in range(n):
        if sum(Fraction(mat_a[i][j], 1) * y_vec[i] for i in range(m)) > Fraction(vec_c[j], 1):
            return False
    p_obj = sum(Fraction(vec_c[j], 1) * x_vec[j] for j in range(n))
    d_obj = sum(Fraction(vec_b[i], 1) * y_vec[i] for i in range(m))
    return p_obj == d_obj and p_obj == robj
