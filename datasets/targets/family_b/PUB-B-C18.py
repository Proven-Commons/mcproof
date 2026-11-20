from fractions import Fraction

def _decode_mat(raw: object, n: int) -> list[list[Fraction]] | None:
    if not isinstance(raw, list) or len(raw) != n:
        return None
    out = []
    for r in raw:
        if not isinstance(r, list) or len(r) != n:
            return None
        row = []
        for pair in r:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return None
            num, den = pair[0], pair[1]
            if type(num) is not int or type(den) is not int or den <= 0:
                return None
            f = Fraction(num, den)
            if f.numerator != num or f.denominator != den:
                return None
            row.append(f)
        out.append(row)
    return out

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    perm = cert.get('perm')
    if not isinstance(mat_a, list) or len(mat_a) == 0 or not isinstance(perm, list):
        return False
    n = len(mat_a)
    if any(not isinstance(r, list) or len(r) != n or any(type(v) is not int for v in r) for r in mat_a):
        return False
    if len(perm) != n or any(type(p) is not int for p in perm) or set(perm) != set(range(n)):
        return False
    mat_l = _decode_mat(cert.get('L'), n)
    mat_u = _decode_mat(cert.get('U'), n)
    if mat_l is None or mat_u is None:
        return False
    for i in range(n):
        if mat_l[i][i] != Fraction(1, 1):
            return False
        for j in range(i + 1, n):
            if mat_l[i][j] != Fraction(0, 1):
                return False
        for j in range(i):
            if mat_u[i][j] != Fraction(0, 1):
                return False
    for i in range(n):
        pa_row = mat_a[perm[i]]
        for j in range(n):
            prod_ij = sum(mat_l[i][k] * mat_u[k][j] for k in range(n))
            if prod_ij != Fraction(pa_row[j], 1):
                return False
    return True
