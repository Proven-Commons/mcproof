def verify(inst: dict, cert: dict) -> bool:
    k_procs = inst.get('num_procs')
    events = inst.get('events')
    ts_list = cert.get('timestamps')
    f_clocks = cert.get('final_clocks')
    if type(k_procs) is not int or k_procs < 1 or not all(isinstance(x, list) for x in (events, ts_list, f_clocks)):
        return False
    if len(ts_list) != len(events) or len(f_clocks) != k_procs:
        return False
    proc_last = {p: 0 for p in range(k_procs)}
    in_flight: dict[int, int] = {}
    seen_msgs: set[int] = set()
    for idx, ev in enumerate(events):
        t_val = ts_list[idx]
        if not isinstance(ev, dict) or type(t_val) is not int:
            return False
        p = ev.get('proc')
        kind = ev.get('kind')
        if type(p) is not int or not (0 <= p < k_procs):
            return False
        prev_t = proc_last[p]
        if kind == 'LOCAL':
            if t_val != prev_t + 1:
                return False
        elif kind == 'SEND':
            mid = ev.get('msg_id')
            if type(mid) is not int or mid in seen_msgs or t_val != prev_t + 1:
                return False
            seen_msgs.add(mid)
            in_flight[mid] = t_val
        elif kind == 'RECV':
            mid = ev.get('msg_id')
            if type(mid) is not int or mid not in in_flight:
                return False
            send_t = in_flight.pop(mid)
            req_t = (prev_t if prev_t >= send_t else send_t) + 1
            if t_val != req_t:
                return False
        else:
            return False
        proc_last[p] = t_val
    return [proc_last[p] for p in range(k_procs)] == f_clocks
