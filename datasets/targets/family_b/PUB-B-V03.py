from fractions import Fraction

def _eval_cf_backward(coeffs: list[int]) -> Fraction:
    val = Fraction(coeffs[-1], 1)
    for a in reversed(coeffs[:-1]):
        val = Fraction(a, 1) + Fraction(val.denominator, val.numerator)
    return val

def verify(inst: dict, cert: dict) -> bool:
    num, den = inst.get('num'), inst.get('den')
    coeffs = cert.get('coeffs')
    convs = cert.get('convergents')
    if type(num) is not int or type(den) is not int or den <= 0:
        return False
    if not isinstance(coeffs, list) or not isinstance(convs, list) or len(coeffs) == 0 or len(coeffs) != len(convs):
        return False
    if any(type(a) is not int for a in coeffs):
        return False
    if any(a < 1 for a in coeffs[1:]) or (len(coeffs) > 1 and coeffs[-1] < 2):
        return False
    for idx in range(len(coeffs)):
        pair = convs[idx]
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        pi, qi = pair[0], pair[1]
        if type(pi) is not int or type(qi) is not int or qi <= 0:
            return False
        prefix_val = _eval_cf_backward(coeffs[: idx + 1])
        if prefix_val.numerator != pi or prefix_val.denominator != qi:
            return False
        if idx >= 1:
            pm1, qm1 = convs[idx - 1]
            expected_det = 1 if (idx - 1) % 2 == 0 else -1
            if pi * qm1 - pm1 * qi != expected_det:
                return False
    return Fraction(convs[-1][0], convs[-1][1]) == Fraction(num, den)
