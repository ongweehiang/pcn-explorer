"""Step 2: merge sources into one set of lines, snap loose ends, and split lines where they cross."""
import os
DD=os.environ.get('PCN_DATA',os.path.join(os.path.dirname(os.path.abspath(__file__)),'data'))+'/'
import json, numpy as np, shapely, re, math, heapq
from shapely.geometry import LineString, Point, MultiLineString
from shapely.ops import unary_union, substring
from shapely import STRtree
from pyproj import Transformer
import networkx as nx
from collections import Counter, defaultdict
D=json.load(open(DD+'pcn_tracks.json')); O=json.load(open(DD+'pcn_data.json')); OS=json.load(open(DD+'pcn_osm.json'))
T=Transformer.from_crs(4326,3414,always_xy=True).transform
TI=Transformer.from_crs(3414,4326,always_xy=True).transform
P=lambda c: LineString([T(x,y) for x,y in c])
def lines_of(g):
    if g.is_empty: return []
    if g.geom_type=='LineString': return [g]
    if hasattr(g,'geoms'): return [x for gg in g.geoms for x in lines_of(gg)]
    return []
log=[]
def say(*a):
    s=' '.join(str(x) for x in a); print(s); log.append(s)

# ---------- primary sources ----------
mp=[(c,P(p)) for c,parts in D['mp'] for p in parts if len(p)>=2]
covs=np.maximum.reduce([np.load(DD+f'cov_{n}.npy') for n in ['tracks','loop2025','pcn2012','osm']])
loop=[(n,lp,P(c)) for n,lp,parts in O['loop'] for c in parts if len(c)>=2]
tr=[dict(park=pk,type=ty,pt=pt,cyc=cy,g=P(p)) for pk,ty,pt,cy,wk,w,parts in D['tracks'] for p in parts if len(p)>=2]
trPCN=[t for t in tr if t['pt']=='Park Connector']
# names for MP25 parts: nearest named loop / tracks PCN within 30m of midpoint
named=[(n,g) for n,lp,g in loop]+[(t['park'],t['g']) for t in trPCN]
ntree=STRtree([g for _,g in named])
def nice(n):
    n=(n or '').strip()
    n=re.sub(r'\bPC\b','Park Connector',n,flags=re.I); n=re.sub(r'\bPK\b','Park',n,flags=re.I); n=re.sub(r'\bNP\b','Nature Park',n)
    n=re.sub(r'\bNR\b','Nature Reserve',n)
    if n.isupper(): n=n.title()
    n=re.sub(r'\s+',' ',n)
    return n
looptree=STRtree([g for _,_,g in loop])
prim=[]
for i,(c,g) in enumerate(mp):
    mid=g.interpolate(0.5,normalized=True)
    j=ntree.query_nearest(mid,max_distance=30)
    name=nice(named[j[0]][0]) if len(j) else ''
    if c=='RIR': name=name or 'Round Island Route'
    if c=='RAIL CORRIDOR': name='Rail Corridor'
    k=looptree.query_nearest(mid,max_distance=30); lp=loop[k[0]][1] if len(k) else ''
    prim.append(dict(g=g,name=name,loop=lp,src='MP25-'+c,status='confirmed' if covs[i]>=0.5 else 'unverified',cov=float(covs[i])))
mpU=unary_union([g for _,g in mp]).buffer(15)
addB=0
for n,lp,g in loop:
    if not g.intersects(mpU): rest=[g]
    else: rest=lines_of(g.difference(mpU))
    for r in rest:
        if r.length>=20: prim.append(dict(g=r,name=nice(n),loop=lp,src='NParks loop',status='confirmed',cov=1)); addB+=r.length
U2=unary_union([mpU]+[g for n,lp,g in loop]).buffer(15) if False else None
loopU=unary_union([g for _,_,g in loop]).buffer(15)
addC=0
for t in trPCN:
    g=t['g']
    if g.intersects(mpU): g=g.difference(mpU)
    if not g.is_empty and g.intersects(loopU): g=g.difference(loopU)
    for r in lines_of(g):
        if r.length>=20: prim.append(dict(g=r,name=nice(t['park']),loop='',src='NParks tracks',status='confirmed',cov=1)); addC+=r.length
say("primary: MP25 km",round(sum(g.length for _,g in mp)/1000,1),"+ loop-only km",round(addB/1000,1),"+ tracks-PCN-only km",round(addC/1000,1))
say("MP25 status km",{s:round(sum(p['g'].length for p in prim if p['status']==s and p['src'].startswith('MP25'))/1000,1) for s in ['confirmed','unverified']})

# ---------- link candidates ----------
links=[]
for t in tr:
    if t['pt']!='Park Connector': links.append(dict(g=t['g'],name=nice(t['park']),src='NParks park path',stairs=t['type']=='Staircase',cyc=t['cyc']))
for wid,hw,nm,bic,foot,acc,bt,geom in OS['ways']:
    if acc in ('private','no') or not hw: continue
    if len(geom)<2: continue
    links.append(dict(g=P(geom),name=nm,src='OSM '+hw,stairs=hw=='steps',cyc='N' if bic=='no' else 'Y'))
for wid,hw,fw,bt,bic,cov,geom in json.load(open(DD+'pcn_osm_foot.json')):
    if len(geom)<2: continue
    links.append(dict(g=P(geom),name='',src='OSM '+hw+(' '+fw if fw else ''),stairs=hw=='steps',cyc='N' if bic=='no' else 'Y'))
say("link candidates",len(links))

# ---------- noding ----------
allL=[dict(p,kind='pcn') for p in prim]+[dict(l,kind='link') for l in links]
geoms=[shapely.set_precision(a['g'],0.5) for a in allL]
# endpoint snapping: extend endpoints onto nearby lines within 6m
tree=STRtree(geoms)
ext=0
for i,g in enumerate(geoms):
    if g.is_empty or g.length==0: continue
    cs=list(g.coords)
    changed=False
    for end in (0,-1):
        pt=Point(cs[end])
        cand=tree.query(pt,predicate='dwithin',distance=6)
        best=None
        for j in cand:
            if j==i: continue
            d=geoms[j].distance(pt)
            if d<1e-6: best=None; break
            if best is None or d<best[0]: best=(d,j)
        if best:
            q=geoms[best[1]].interpolate(geoms[best[1]].project(pt))
            if end==0: cs.insert(0,(q.x,q.y))
            else: cs.append((q.x,q.y))
            changed=True; ext+=1
    if changed: geoms[i]=LineString(cs)
say("endpoint snaps",ext)
# node: split each line at intersections with others
geoms=[shapely.set_precision(g,0.5) for g in geoms]
tree=STRtree(geoms)
pieces=[]
for i,g in enumerate(geoms):
    if g.is_empty or g.length<0.5: continue
    cand=tree.query(g,predicate='intersects')
    ds={0.0,g.length}
    for j in cand:
        if j==i: continue
        x=g.intersection(geoms[j])
        for pt in ([x] if x.geom_type=='Point' else getattr(x,'geoms',[])):
            if pt.geom_type=='Point': ds.add(g.project(pt))
            elif pt.geom_type=='LineString':
                ds.add(g.project(Point(pt.coords[0]))); ds.add(g.project(Point(pt.coords[-1])))
        if x.geom_type=='LineString':
            ds.add(g.project(Point(x.coords[0]))); ds.add(g.project(Point(x.coords[-1])))
    # self intersections / vertices that touch? also split at own vertices shared with others handled above
    ds=sorted(d for d in ds)
    for a,b in zip(ds[:-1],ds[1:]):
        if b-a<0.3: continue
        s=substring(g,a,b)
        if s.geom_type=='LineString' and s.length>=0.3: pieces.append((i,s))
say("noded pieces",len(pieces))
key=lambda c:(round(c[0]*2)/2,round(c[1]*2)/2)
G=nx.MultiGraph()
for i,s in pieces:
    a=key(s.coords[0]); b=key(s.coords[-1])
    if a==b: continue
    G.add_edge(a,b,len=s.length,src=i,g=s)
say("graph nodes",G.number_of_nodes(),"edges",G.number_of_edges())
import pickle; pickle.dump((allL,G),open(DD+'graph.pkl','wb'))
json.dump(log,open(DD+'log1.json','w'))
