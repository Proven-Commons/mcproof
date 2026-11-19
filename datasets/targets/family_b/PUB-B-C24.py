def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('num_nodes')
    init_h = inst.get('initial_holder')
    hops = inst.get('hops')
    is_val = cert.get('valid')
    fh = cert.get('final_holder')
    vc = cert.get('visit_counts')
    rot = cert.get('full_rotations')
    if not all(type(x) is int for x in (n, init_h, fh, rot)) or type(is_val) is not bool:
        return False
    if n < 2 or not (0 <= init_h < n) or not isinstance(hops, list) or not isinstance(vc, list):
        return False
    state_vec = [1 if i == init_h else 0 for i in range(n)]
    visits = [1 if i == init_h else 0 for i in range(n)]
    legal = True
    for step in hops:
        if not isinstance(step, (list, tuple)) or len(step) != 2:
            return False
        s, d = step[0], step[1]
        if type(s) is not int or type(d) is not int or not (0 <= s < n and 0 <= d < n):
            return False
        if state_vec[s] != 1 or d != (s + 1) % n:
            legal = False
            break
        state_vec[s] = 0
        state_vec[d] = 1
        visits[d] += 1
    if not legal:
        return (is_val, fh, vc, rot) == (False, -1, [], -1)
    holder = state_vec.index(1)
    return is_val is True and sum(state_vec) == 1 and fh == holder and vc == visits and sum(vc) == len(hops) + 1 and rot == len(hops) // n
