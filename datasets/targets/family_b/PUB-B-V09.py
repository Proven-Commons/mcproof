from fractions import Fraction

def _rf(pair: object) -> Fraction | None:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    if type(pair[0]) is not int or type(pair[1]) is not int or pair[1] <= 0:
        return None
    f = Fraction(pair[0], pair[1])
    return f if (f.numerator == pair[0] and f.denominator == pair[1]) else None

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    vec_b = inst.get('b')
    raw_r = cert.get('R')
    raw_xm = cert.get('x_mid')
    rad = _rf(cert.get('rad'))
    if rad is None or rad <= 0 or not all(isinstance(z, list) for z in (mat_a, vec_b, raw_r, raw_xm)) or len(mat_a) == 0:
        return False
    n = len(mat_a)
    if len(vec_b) != n or len(raw_r) != n or len(raw_xm) != n:
        return False
    if any(not isinstance(r, list) or len(r) != n or any(type(x) is not int for x in r) for r in mat_a) or any(type(x) is not int for x in vec_b):
        return False
    r_mat = []
    for row in raw_r:
        if not isinstance(row, list) or len(row) != n:
            return False
        prow = [_rf(p) for p in row]
        if any(x is None for x in prow):
            return False
        r_mat.append(prow)
    xm = [_rf(p) for p in raw_xm]
    if any(x is None for x in xm):
        return False
    c_inf = Fraction(0, 1)
    for i in range(n):
        row_sum = Fraction(0, 1)
        for j in range(n):
            ra_ij = sum(r_mat[i][k] * Fraction(mat_a[k][j], 1) for k in range(n))
            c_ij = (Fraction(1, 1) if i == j else Fraction(0, 1)) - ra_ij
            row_sum += abs(c_ij)
        if row_sum > c_inf:
            c_inf = row_sum
    if c_inf >= Fraction(1, 1):
        return False
    res_b = [Fraction(vec_b[k], 1) - sum(Fraction(mat_a[k][j], 1) * xm[j] for j in range(n)) for k in range(n)]
    rvec_inf = max(abs(sum(r_mat[i][k] * res_b[k] for k in range(n))) for i in range(n))
    return rvec_inf + c_inf * rad <= rad
