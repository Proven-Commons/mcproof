from fractions import Fraction

def _rf(p: object) -> Fraction | None:
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        return None
    if type(p[0]) is not int or type(p[1]) is not int or p[1] <= 0:
        return None
    f = Fraction(p[0], p[1])
    return f if (f.numerator == p[0] and f.denominator == p[1]) else None

def verify(inst: dict, cert: dict) -> bool:
    vecs = inst.get('vectors')
    rq = cert.get('Q')
    rr = cert.get('R')
    rns = cert.get('norms_sq')
    if not all(isinstance(z, list) for z in (vecs, rq, rr, rns)) or len(vecs) == 0 or len(vecs[0]) == 0:
        return False
    k, d = len(vecs), len(vecs[0])
    if len(rq) != k or len(rr) != k or len(rns) != k:
        return False
    if any(not isinstance(v, list) or len(v) != d or any(type(x) is not int for x in v) for v in vecs):
        return False
    q_vecs = []
    for row in rq:
        if not isinstance(row, list) or len(row) != d:
            return False
        prow = [_rf(p) for p in row]
        if any(x is None for x in prow):
            return False
        q_vecs.append(prow)
    r_mat = []
    for row in rr:
        if not isinstance(row, list) or len(row) != k:
            return False
        prow = [_rf(p) for p in row]
        if any(x is None for x in prow):
            return False
        r_mat.append(prow)
    nsq = [_rf(p) for p in rns]
    if any(x is None or x <= 0 for x in nsq):
        return False
    for a in range(k):
        if r_mat[a][a] != Fraction(1, 1):
            return False
        for b in range(a):
            if r_mat[a][b] != Fraction(0, 1):
                return False
        for b in range(k):
            ip = sum(q_vecs[a][t] * q_vecs[b][t] for t in range(d))
            if a == b and ip != nsq[a]:
                return False
            if a != b and ip != Fraction(0, 1):
                return False
    for i in range(k):
        for t in range(d):
            recon = sum(r_mat[j][i] * q_vecs[j][t] for j in range(i + 1))
            if recon != Fraction(vecs[i][t], 1):
                return False
    return True
