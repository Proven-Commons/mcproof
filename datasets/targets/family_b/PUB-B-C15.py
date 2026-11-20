from fractions import Fraction

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    raw_inv = cert.get('inv')
    if not isinstance(mat_a, list) or not isinstance(raw_inv, list) or len(mat_a) == 0:
        return False
    n = len(mat_a)
    if len(raw_inv) != n:
        return False
    if any(not isinstance(r, list) or len(r) != n or any(type(v) is not int for v in r) for r in mat_a):
        return False
    b_mat = []
    for row in raw_inv:
        if not isinstance(row, list) or len(row) != n:
            return False
        b_row = []
        for pair in row:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return False
            num, den = pair[0], pair[1]
            if type(num) is not int or type(den) is not int or den <= 0:
                return False
            fb = Fraction(num, den)
            if fb.numerator != num or fb.denominator != den:
                return False
            b_row.append(fb)
        b_mat.append(b_row)
    for i in range(n):
        for j in range(n):
            target = Fraction(1 if i == j else 0, 1)
            ab = sum(Fraction(mat_a[i][k], 1) * b_mat[k][j] for k in range(n))
            ba = sum(b_mat[i][k] * Fraction(mat_a[k][j], 1) for k in range(n))
            if ab != target or ba != target:
                return False
    return True
