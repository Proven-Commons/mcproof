def verify(inst: dict, cert: dict) -> bool:
    win = inst.get('window_size')
    arrs = inst.get('arrivals')
    c_base = cert.get('rcv_base')
    c_deliv = cert.get('delivered')
    c_buf = cert.get('buffered_seqs')
    if type(win) is not int or win < 1 or type(c_base) is not int:
        return False
    if not all(isinstance(z, list) for z in (arrs, c_deliv, c_buf)):
        return False
    accepted_payload: dict[int, int] = {}
    frontier = 0
    for pkt in arrs:
        if not isinstance(pkt, dict):
            return False
        sq, pl = pkt.get('seq'), pkt.get('payload')
        if type(sq) is not int or type(pl) is not int or sq < 0:
            return False
        if frontier <= sq < frontier + win and sq not in accepted_payload:
            accepted_payload[sq] = pl
            for cand in range(frontier, frontier + win + len(accepted_payload) + 1):
                if cand in accepted_payload:
                    frontier = cand + 1
                else:
                    break
    exp_deliv = [accepted_payload[i] for i in range(frontier)]
    exp_buf = sorted(k for k in accepted_payload if k >= frontier)
    return c_base == frontier and c_deliv == exp_deliv and c_buf == exp_buf
