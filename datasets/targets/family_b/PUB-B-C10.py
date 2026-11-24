from fractions import Fraction

def _comb_exact(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    res = 1
    for i in range(1, k + 1):
        res = (res * (n - i + 1)) // i
    return res

def verify(inst: dict, cert: dict) -> bool:
    m, n, r = inst.get('m'), inst.get('n'), inst.get('r')
    tot = cert.get('total_binom')
    ws = cert.get('weights')
    if not all(type(v) is int for v in (m, n, r, tot)) or not isinstance(ws, list):
        return False
    if m < 0 or n < 0 or r < 0 or r > m + n:
        return False
    exp_tot = _comb_exact(m + n, r)
    if tot != exp_tot or len(ws) != r + 1:
        return False
    acc = Fraction(0, 1)
    for k, pair in enumerate(ws):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        num, den = pair[0], pair[1]
        if type(num) is not int or type(den) is not int or den <= 0:
            return False
        fk = Fraction(num, den)
        if fk.numerator != num or fk.denominator != den:
            return False
        if fk != Fraction(_comb_exact(m, k) * _comb_exact(n, r - k), exp_tot):
            return False
        acc += fk
    return acc == Fraction(1, 1)
