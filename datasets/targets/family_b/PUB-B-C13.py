from fractions import Fraction

def _det_exact(mat: list[list[int]]) -> int:
    n = len(mat)
    if n == 1:
        return mat[0][0]
    total = 0
    for col in range(n):
        minor = [row[:col] + row[col + 1:] for row in mat[1:]]
        sign = 1 if col % 2 == 0 else -1
        total += sign * mat[0][col] * _det_exact(minor)
    return total

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    vec_b = inst.get('b')
    raw_x = cert.get('x')
    if not all(isinstance(z, list) for z in (mat_a, vec_b, raw_x)) or len(mat_a) == 0:
        return False
    n = len(mat_a)
    if len(vec_b) != n or len(raw_x) != n:
        return False
    if any(not isinstance(row, list) or len(row) != n or any(type(v) is not int for v in row) for row in mat_a):
        return False
    if any(type(v) is not int for v in vec_b):
        return False
    if _det_exact(mat_a) == 0:
        return False
    sol = []
    for pair in raw_x:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        num, den = pair[0], pair[1]
        if type(num) is not int or type(den) is not int or den <= 0:
            return False
        fx = Fraction(num, den)
        if fx.numerator != num or fx.denominator != den:
            return False
        sol.append(fx)
    for i in range(n):
        lhs = sum(Fraction(mat_a[i][j], 1) * sol[j] for j in range(n))
        if lhs != Fraction(vec_b[i], 1):
            return False
    return True
