def _check_rw_trace(events: list) -> tuple[bool, list[int], int]:
    mode_by_tid: dict[int, str] = {}
    for ev in events:
        if not isinstance(ev, dict):
            return (False, [], -1)
        tid, op = ev.get('tid'), ev.get('op')
        if type(tid) is not int or tid < 0:
            return (False, [], -1)
        w_cnt = sum(1 for m in mode_by_tid.values() if m == 'W')
        r_cnt = sum(1 for m in mode_by_tid.values() if m == 'R')
        if op == 'ACQ_R':
            if w_cnt > 0 or tid in mode_by_tid:
                return (False, [], -1)
            mode_by_tid[tid] = 'R'
        elif op == 'REL_R':
            if mode_by_tid.get(tid) != 'R':
                return (False, [], -1)
            del mode_by_tid[tid]
        elif op == 'ACQ_W':
            if w_cnt > 0 or r_cnt > 0 or tid in mode_by_tid:
                return (False, [], -1)
            mode_by_tid[tid] = 'W'
        elif op == 'REL_W':
            if mode_by_tid.get(tid) != 'W':
                return (False, [], -1)
            del mode_by_tid[tid]
        else:
            return (False, [], -1)
    final_r = sorted(t for t, m in mode_by_tid.items() if m == 'R')
    final_ws = [t for t, m in mode_by_tid.items() if m == 'W']
    return (True, final_r, final_ws[0] if final_ws else -1)

def verify(inst: dict, cert: dict) -> bool:
    events = inst.get('events')
    sf = cert.get('safe')
    fr = cert.get('final_readers')
    fw = cert.get('final_writer')
    if not isinstance(events, list) or type(sf) is not bool or not isinstance(fr, list) or type(fw) is not int:
        return False
    return (sf, fr, fw) == _check_rw_trace(events)
