from fractions import Fraction

def _parse_frac(pair: object, require_reduced: bool) -> Fraction | None:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    num, den = pair[0], pair[1]
    if type(num) is not int or type(den) is not int or den <= 0:
        return None
    f = Fraction(num, den)
    if require_reduced and (f.numerator != num or f.denominator != den):
        return None
    return f

def _parse_iv(iv: object, require_reduced: bool) -> tuple[Fraction, Fraction] | None:
    if not isinstance(iv, (list, tuple)) or len(iv) != 2:
        return None
    lo = _parse_frac(iv[0], require_reduced)
    hi = _parse_frac(iv[1], require_reduced)
    if lo is None or hi is None or lo > hi:
        return None
    return (lo, hi)

def _iv_mul_kaucher_free(a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
    alo, ahi = a
    blo, bhi = b
    c1 = alo * blo
    c2 = alo * bhi
    c3 = ahi * blo
    c4 = ahi * bhi
    lo = c1 if c1 <= c2 else c2
    lo = lo if lo <= c3 else c3
    lo = lo if lo <= c4 else c4
    hi = c1 if c1 >= c2 else c2
    hi = hi if hi >= c3 else c3
    hi = hi if hi >= c4 else c4
    return (lo, hi)

def verify(inst: dict, cert: dict) -> bool:
    a_raw = inst.get('A_iv')
    x_raw = inst.get('x_iv')
    y_raw = cert.get('y_exact_iv')
    if not all(isinstance(z, list) for z in (a_raw, x_raw, y_raw)) or len(a_raw) == 0 or len(x_raw) == 0:
        return False
    m, n = len(a_raw), len(x_raw)
    if len(y_raw) != m:
        return False
    x_ivs = [_parse_iv(iv, False) for iv in x_raw]
    if any(v is None for v in x_ivs):
        return False
    for i in range(m):
        if not isinstance(a_raw[i], list) or len(a_raw[i]) != n:
            return False
        yi = _parse_iv(y_raw[i], True)
        if yi is None:
            return False
        acc_lo = Fraction(0, 1)
        acc_hi = Fraction(0, 1)
        for j in range(n):
            aij = _parse_iv(a_raw[i][j], False)
            if aij is None:
                return False
            plo, phi = _iv_mul_kaucher_free(aij, x_ivs[j])
            acc_lo += plo
            acc_hi += phi
        if yi != (acc_lo, acc_hi):
            return False
    return True
