from fractions import Fraction

def _det_int(sub: list[list[int]]) -> int:
    k = len(sub)
    if k == 0:
        return 1
    if k == 1:
        return sub[0][0]
    acc = 0
    for j in range(k):
        minor = [rw[:j] + rw[j + 1:] for rw in sub[1:]]
        acc += (1 if j % 2 == 0 else -1) * sub[0][j] * _det_int(minor)
    return acc

def verify(inst: dict, cert: dict) -> bool:
    mat_a = inst.get('A')
    rk = cert.get('rank')
    prows = cert.get('pivot_rows')
    pcols = cert.get('pivot_cols')
    fcols = cert.get('free_cols')
    nbasis = cert.get('null_basis')
    if type(rk) is not int or rk < 0 or not all(isinstance(z, list) for z in (mat_a, prows, pcols, fcols, nbasis)):
        return False
    if len(mat_a) == 0 or not isinstance(mat_a[0], list) or len(mat_a[0]) == 0:
        return False
    m, n = len(mat_a), len(mat_a[0])
    if len(prows) != rk or len(pcols) != rk or len(fcols) != n - rk or len(nbasis) != n - rk:
        return False
    if pcols != sorted(set(pcols)) or fcols != sorted(set(fcols)) or prows != sorted(set(prows)):
        return False
    if set(pcols) | set(fcols) != set(range(n)) or any(not (0 <= r < m) for r in prows):
        return False
    if _det_int([[mat_a[ri][ci] for ci in pcols] for ri in prows]) == 0:
        return False
    for s_idx, raw_v in enumerate(nbasis):
        if not isinstance(raw_v, list) or len(raw_v) != n:
            return False
        vec = []
        for pair in raw_v:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return False
            num, den = pair[0], pair[1]
            if type(num) is not int or type(den) is not int or den <= 0:
                return False
            fv = Fraction(num, den)
            if fv.numerator != num or fv.denominator != den:
                return False
            vec.append(fv)
        for t_idx, fc in enumerate(fcols):
            if vec[fc] != Fraction(1 if s_idx == t_idx else 0, 1):
                return False
        for i in range(m):
            if sum(Fraction(mat_a[i][j], 1) * vec[j] for j in range(n)) != Fraction(0, 1):
                return False
    return True
