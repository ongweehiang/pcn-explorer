"""Step 5: define whole routes — Round Island Route, Rail Corridor and each named park connector —
and lay each one out end to end as a continuous path. Adds `routes` to ../net.json.
(NParks loops are not included yet: their source lines overlap and break up too much to order reliably.)"""
import json, math, os, re, heapq
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.join(HERE, '..', 'net.json')
D = json.load(open(NET))
N = D['nodes']; E = D['edges']; NAMES = D['names']; LOOPS = D['loops']
KX = 111320 * math.cos(1.35 * math.pi / 180) / 1e5; KY = 110574 / 1e5


def xy(n):
    return N[n][0] * KX, N[n][1] * KY


def dist(a, b):
    (x1, y1), (x2, y2) = xy(a), xy(b)
    return math.hypot(x1 - x2, y1 - y2)


adj = defaultdict(list)
for i, e in enumerate(E):
    adj[e[0]].append(i); adj[e[1]].append(i)
PCN = lambda i: E[i][3] < 2


def norm(n):
    n = re.sub(r'\(.*?\)', '', n or '')
    n = re.sub(r'\s+', ' ', n).strip(' -–,')
    if not n:
        return ''
    n = ' '.join(w if (w.isupper() and len(w) <= 3 and w not in ('PARK',)) else w.capitalize() if w.isupper() else w for w in n.split())
    n = re.sub(r'\bPc\b|\bPcn\b', 'Park Connector', n)
    return n


# ---------- groups ----------
groups = defaultdict(set)   # (kind, name) -> edge ids
ename = {}
for i, e in enumerate(E):
    if not PCN(i):
        continue
    nm = norm(NAMES[e[4]])
    if nm in ('Round Island Route',) or 'RIR' in nm.split():
        groups[('long', 'Round Island Route')].add(i)
        continue
    if nm == 'Rail Corridor':
        groups[('long', 'Rail Corridor')].add(i)
        continue
    if nm:
        ename[i] = nm

# propagate connector names onto unnamed connector edges whose two ends both touch the same name
for _ in range(6):
    add = {}
    for i, e in enumerate(E):
        if not PCN(i) or i in ename:
            continue
        a = {ename[j] for j in adj[e[0]] if j in ename}
        b = {ename[j] for j in adj[e[1]] if j in ename}
        common = a & b
        if len(common) == 1:
            add[i] = common.pop()
    if not add:
        break
    ename.update(add)
for i, nm in ename.items():
    groups[('connector', nm)].add(i)



def clusters(eids, join=400):
    """connected pieces of a group, joining pieces whose nodes are within `join` metres"""
    nodes = defaultdict(set)
    for i in eids:
        nodes[E[i][0]].add(i); nodes[E[i][1]].add(i)
    parent = {i: i for i in eids}

    def f(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for n, es in nodes.items():
        es = list(es)
        for j in es[1:]:
            parent[f(j)] = f(es[0])
    comp = defaultdict(set)
    for i in eids:
        comp[f(i)].add(i)
    comps = list(comp.values())
    # join pieces that are close
    merged = True
    while merged and len(comps) > 1:
        merged = False
        for a in range(len(comps)):
            na = {E[i][k] for i in comps[a] for k in (0, 1)}
            for b in range(a + 1, len(comps)):
                nb = {E[i][k] for i in comps[b] for k in (0, 1)}
                if min(dist(x, y) for x in list(na)[:200] for y in list(nb)[:200]) <= join:
                    comps[a] |= comps[b]; comps.pop(b); merged = True; break
            if merged:
                break
    return sorted(comps, key=lambda c: -sum(E[i][2] for i in c))


BASE = {0: 1, 1: 1.4, 2: 2.2, 3: 3, 4: 2.6, 5: 2.2}


def dijkstra(s, t, w):
    dd = {s: 0}; prev = {}; h = [(0, s)]
    while h:
        d, u = heapq.heappop(h)
        if u == t:
            break
        if d > dd.get(u, 1e18):
            continue
        for i in adj[u]:
            e = E[i]; v = e[1] if e[0] == u else e[0]
            nd = d + w(i)
            if nd < dd.get(v, 1e18):
                dd[v] = nd; prev[v] = i; heapq.heappush(h, (nd, v))
    if t not in prev and s != t:
        return None
    path = []; u = t
    while u != s:
        i = prev[u]; path.append(i); e = E[i]; u = e[0] if e[1] == u else e[1]
    return path[::-1]


wps = [w for w in D['wps']]


def end_label(n):
    best = None
    for w in wps:
        d = dist(n, w[2]) + (0 if w[0] == 'station' else 300)
        if d < 1500 and (best is None or d < best[0]):
            best = (d, w)
    if not best:
        return ''
    nm = re.sub(r'\s*\(.*\)$', '', best[1][1])
    return nm


routes = []
for (kind, name), eids in sorted(groups.items(), key=lambda kv: (kv[0][0] != 'loop', kv[0][0] != 'long', kv[0][1])):
    cs = clusters(eids)
    main = set().union(*[c for c in cs if sum(E[i][2] for i in c) >= 1000]) if kind == 'loop' else cs[0]
    if not main:
        continue
    glen = sum(E[i][2] for i in main)
    if glen < (1500 if kind == 'connector' else 3000):
        continue
    # join the group's pieces with the shortest real paths between them
    aug = set(main)
    comps = clusters(main, join=0)
    while len(comps) > 1:
        base = comps[0]
        bn = list({E[i][k] for i in base for k in (0, 1)})
        best = None
        for c in comps[1:]:
            cn = list({E[i][k] for i in c for k in (0, 1)})
            d, x, y = min((dist(x, y), x, y) for x in bn[:300] for y in cn[:300])
            if best is None or d < best[0]:
                best = (d, x, y, c)
        d, x, y, c = best
        link = dijkstra(x, y, lambda i: E[i][2] * BASE[E[i][3]]) or []
        aug |= set(link) | c
        comps = [base | c | set(link)] + [k for k in comps[1:] if k is not c]
    def far(s0):
        dd = {s0: 0}; prev = {}; h = [(0, s0)]
        while h:
            d, u = heapq.heappop(h)
            if d > dd[u]:
                continue
            for i in adj[u]:
                if i not in aug:
                    continue
                e = E[i]; v = e[1] if e[0] == u else e[0]
                if d + e[2] < dd.get(v, 1e18):
                    dd[v] = d + e[2]; prev[v] = i; heapq.heappush(h, (dd[v], v))
        t = max(dd, key=dd.get)
        path = []; u = t
        while u != s0:
            i = prev[u]; path.append(i); e = E[i]; u = e[0] if e[1] == u else e[1]
        return t, path[::-1]
    a, _ = far(E[next(iter(main))][0])
    b, path = far(a)
    if not path:
        continue
    if kind == 'loop':
        used = set(path)
        def back_w(i):
            if i in used: return E[i][2] * 4
            if i in aug: return E[i][2] * 0.3
            return E[i][2] * BASE[E[i][3]] * 1.5
        back = dijkstra(b, a, back_w)
        if back:
            path = path + back
            aug |= set(back)
    # orient west/north -> east/south consistently: start at the westernmost end
    if kind != 'loop' and N[a][0] > N[b][0]:
        a, b = b, a
        path = path[::-1]
    if kind == 'loop':
        b = a
    onpath = set(path)
    cover = sum(E[i][2] for i in main if i in onpath) / glen
    plen = sum(E[i][2] for i in path)
    pcn = sum(E[i][2] for i in path if E[i][3] < 2)
    extra = sorted(i for i in aug if i not in onpath)
    routes.append(dict(name=name, kind=kind, start=a, end=b, edges=path, extra=extra, len=round(plen), total=round(sum(E[i][2] for i in aug)),
                       pcn=round(pcn / plen, 3), cover=round(cover, 3), ends=[end_label(a), end_label(b)]))

# drop connectors that are basically a duplicate stretch of a longer route with the same edges
routes.sort(key=lambda r: ({'loop': 0, 'long': 1, 'connector': 2}[r['kind']], r['name']))
D['routes'] = [r for r in routes if r['len'] >= 1000]
s = json.dumps(D, separators=(',', ':'), ensure_ascii=False)
open(NET, 'w').write(s)
c = Counter(r['kind'] for r in routes)
print('routes', dict(c), 'bytes', len(s.encode()))
for r in routes:
    if r['kind'] != 'connector' or r['len'] > 6000:
        print(f"  {r['kind']:9} {r['name'][:45]:45} {r['len'] / 1000:5.1f}/{r['total']/1000:5.1f} km  cover {r['cover']:.0%}  on PCN {r['pcn']:.0%}  {r['ends']}")
print('low cover:', [(r['name'], r['cover']) for r in routes if r['cover'] < 0.6][:20])
