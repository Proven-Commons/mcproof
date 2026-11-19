from fractions import Fraction

def _rat(pair: object) -> Fraction | None:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    if type(pair[0]) is not int or type(pair[1]) is not int or pair[1] <= 0:
        return None
    return Fraction(pair[0], pair[1])

def verify(inst: dict, cert: dict) -> bool:
    leases = inst.get('leases')
    writes = inst.get('writes')
    disj_flag = cert.get('disjoint_leases')
    acc = cert.get('accepted_writes')
    if not all(isinstance(x, list) for x in (leases, writes, acc)) or type(disj_flag) is not bool:
        return False
    parsed_leases = []
    prev_tok = 0
    for item in leases:
        if not isinstance(item, dict):
            return False
        tok, ldr = item.get('token'), item.get('leader')
        st, ex = _rat(item.get('start')), _rat(item.get('expiry'))
        if type(tok) is not int or type(ldr) is not int or tok <= prev_tok or st is None or ex is None or st >= ex:
            return False
        prev_tok = tok
        parsed_leases.append((tok, ldr, st, ex))
    actual_disj = True
    for i in range(len(parsed_leases) - 1):
        if parsed_leases[i][3] > parsed_leases[i + 1][2]:
            actual_disj = False
    if disj_flag != actual_disj:
        return False
    if not actual_disj:
        return len(acc) == 0
    if len(acc) != len(writes) or any(type(b) is not bool for b in acc):
        return False
    by_tok = {t: (ldr, st, ex) for (t, ldr, st, ex) in parsed_leases}
    fencing_floor = 0
    for idx, w in enumerate(writes):
        if not isinstance(w, dict):
            return False
        wt, wl, wts = w.get('token'), w.get('leader'), _rat(w.get('ts'))
        if type(wt) is not int or type(wl) is not int or wts is None:
            return False
        rec = by_tok.get(wt)
        allow = rec is not None and rec[0] == wl and wt >= fencing_floor and rec[1] <= wts < rec[2]
        if acc[idx] != allow:
            return False
        if allow:
            fencing_floor = wt
    return True
