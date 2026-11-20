from fractions import Fraction

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    vec_b = inst.get('b')
    raw_y = cert.get('y')
    if not all(isinstance(z, list) for z in (mat_a, vec_b, raw_y)) or len(mat_a) == 0:
        return False
    m = len(mat_a)
    if len(vec_b) != m or len(raw_y) != m or not isinstance(mat_a[0], list) or len(mat_a[0]) == 0:
        return False
    n = len(mat_a[0])
    if any(not isinstance(r, list) or len(r) != n or any(type(v) is not int for v in r) for r in mat_a):
        return False
    if any(type(v) is not int for v in vec_b):
        return False
    y_vec = []
    for pair in raw_y:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        num, den = pair[0], pair[1]
        if type(num) is not int or type(den) is not int or den <= 0:
            return False
        fy = Fraction(num, den)
        if fy.numerator != num or fy.denominator != den:
            return False
        y_vec.append(fy)
    for col in range(n):
        dual_col = Fraction(0, 1)
        for row in range(m):
            dual_col += y_vec[row] * Fraction(mat_a[row][col], 1)
        if dual_col < Fraction(0, 1):
            return False
    dual_rhs = sum(y_vec[row] * Fraction(vec_b[row], 1) for row in range(m))
    return dual_rhs < Fraction(0, 1)
