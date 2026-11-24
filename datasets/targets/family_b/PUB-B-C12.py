def verify(inst: dict, cert: dict) -> bool:
    m = inst.get('codomain_size')
    vals = inst.get('values')
    i = cert.get('i')
    j = cert.get('j')
    val = cert.get('value')
    if not all(type(v) is int for v in (m, i, j, val)) or not isinstance(vals, list):
        return False
    if m < 1 or len(vals) <= m:
        return False
    if any(type(x) is not int or not (0 <= x < m) for x in vals):
        return False
    if not (0 <= i < j < len(vals)):
        return False
    if vals[i] != val or vals[j] != val:
        return False
    prefix = vals[:j]
    return len(set(prefix)) == len(prefix)
