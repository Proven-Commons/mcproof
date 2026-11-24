def _audit_ticket_events(events: list) -> tuple[bool, int, int, int]:
    ticket_owner: dict[int, int] = {}
    ticket_state: dict[int, int] = {}  # 0=issued, 1=entered, 2=exited
    cur_turn = 0
    holder_ticket = -1
    ever_entered = 0
    for ev in events:
        if not isinstance(ev, dict):
            return (False, -1, -1, -1)
        kind = ev.get('op')
        cid = ev.get('client')
        if type(cid) is not int or cid < 0:
            return (False, -1, -1, -1)
        if kind == 'ISSUE':
            tid = len(ticket_owner)
            ticket_owner[tid] = cid
            ticket_state[tid] = 0
        elif kind == 'ENTER':
            tid = ev.get('ticket')
            if type(tid) is not int or holder_ticket != -1 or tid != cur_turn:
                return (False, -1, -1, -1)
            if ticket_owner.get(tid) != cid or ticket_state.get(tid) != 0:
                return (False, -1, -1, -1)
            ticket_state[tid] = 1
            holder_ticket = tid
            ever_entered = 1
        elif kind == 'EXIT':
            tid = ev.get('ticket')
            if type(tid) is not int or holder_ticket != tid or ticket_owner.get(tid) != cid:
                return (False, -1, -1, -1)
            ticket_state[tid] = 2
            holder_ticket = -1
            cur_turn += 1
        else:
            return (False, -1, -1, -1)
    return (True, cur_turn, len(ticket_owner), ever_entered)

def verify(inst: dict, cert: dict) -> bool:
    events = inst.get('events')
    vt = cert.get('valid_trace')
    fs = cert.get('final_serving')
    fn = cert.get('final_next_ticket')
    mc = cert.get('max_concurrent')
    if not isinstance(events, list) or type(vt) is not bool or not all(type(x) is int for x in (fs, fn, mc)):
        return False
    exp_ok, exp_fs, exp_fn, exp_mc = _audit_ticket_events(events)
    return (vt, fs, fn, mc) == (exp_ok, exp_fs, exp_fn, exp_mc)
