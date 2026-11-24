def verify(inst: dict, cert: dict) -> bool:
    cap = inst.get('capacity')
    ops = inst.get('ops')
    popped = cert.get('popped')
    rem = cert.get('remaining')
    dropped = cert.get('dropped_count')
    if type(cap) is not int or cap < 1 or type(dropped) is not int:
        return False
    if not all(isinstance(x, list) for x in (ops, popped, rem)):
        return False
    q_list: list[int] = []
    out_list: list[int] = []
    rej = 0
    for step in ops:
        if not isinstance(step, dict):
            return False
        kind = step.get('op')
        if kind == 'PUSH':
            val = step.get('val')
            if type(val) is not int:
                return False
            if len(q_list) < cap:
                q_list.append(val)
            else:
                rej += 1
        elif kind == 'POP':
            if len(q_list) > 0:
                out_list.append(q_list.pop(0))
        else:
            return False
    return out_list == popped and q_list == rem and rej == dropped
