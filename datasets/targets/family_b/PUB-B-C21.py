def verify(inst: dict, cert: dict) -> bool:
    n = inst.get('num_nodes')
    votes = inst.get('votes')
    tout = inst.get('timeout')
    dec = cert.get('decision')
    nstates = cert.get('node_states')
    yc = cert.get('yes_count')
    if type(n) is not int or n < 1 or type(tout) is not bool or type(yc) is not int:
        return False
    if dec not in ('COMMIT', 'ABORT') or not isinstance(votes, list) or not isinstance(nstates, list):
        return False
    seen_nodes: dict[int, str] = {}
    for item in votes:
        if not isinstance(item, dict):
            return False
        nid, vt = item.get('node'), item.get('vote')
        if type(nid) is not int or not (0 <= nid < n) or vt not in ('YES', 'NO') or nid in seen_nodes:
            return False
        seen_nodes[nid] = vt
    actual_yes = sum(1 for nid in range(n) if seen_nodes.get(nid) == 'YES')
    if yc != actual_yes:
        return False
    expected_dec = 'COMMIT' if (not tout and len(seen_nodes) == n and actual_yes == n) else 'ABORT'
    if dec != expected_dec or len(nstates) != n:
        return False
    return all(st == expected_dec for st in nstates)
