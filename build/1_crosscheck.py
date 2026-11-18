"""Step 1: cross-check every URA Master Plan 2025 connector line against NParks (loop, tracks, 2012) and OpenStreetMap."""
import os
DD=os.environ.get('PCN_DATA',os.path.join(os.path.dirname(os.path.abspath(__file__)),'data'))+'/'
import json, numpy as np, shapely
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely import STRtree
from pyproj import Transformer
import networkx as nx
from collections import Counter
D=json.load(open(DD+'pcn_tracks.json'))
O=json.load(open(DD+'pcn_data.json'))
OS=json.load(open(DD+'pcn_osm.json'))
T=Transformer.from_crs(4326,3414,always_xy=True).transform
P=lambda c: LineString([T(x,y) for x,y in c])
mp=[(c,P(p)) for c,parts in D['mp'] for p in parts if len(p)>=2]
tr=[(pk,ty,pt,cy,P(p)) for pk,ty,pt,cy,wk,w,parts in D['tracks'] for p in parts if len(p)>=2]
loop=[P(c) for _,_,parts in O['loop'] for c in parts if len(c)>=2]
old=[P(c) for _,parts in O['line'] for c in parts if len(c)>=2]
def cover(lines, ref, tol=25, step=20):
    """fraction of each line within tol of ref"""
    tree=STRtree(ref); res=[]
    for g in lines:
        n=max(2,int(g.length/step)+1)
        pts=[g.interpolate(d) for d in np.linspace(0,g.length,n)]
        idx=tree.query(pts,predicate='dwithin',distance=tol)
        res.append(len(set(idx[0]))/n)
    return np.array(res)
mpg=[g for c,g in mp]
L=np.array([g.length for g in mpg])
cls=np.array([c for c,g in mp])
tracksG=[t[4] for t in tr]
osmG=[P(w[7]) for w in OS["ways"] if len(w[7])>=2]
for name,ref,tol in [("tracks",tracksG,25),("loop2025",loop,25),("pcn2012",old,25),("osm",osmG,20)]:
    f=cover(mpg,ref,tol=tol); np.save(DD+f'cov_{name}.npy',f)
    for c in set(cls):
        m=cls==c; print(name,c,"km covered",round((f[m]*L[m]).sum()/1000,1),"of",round(L[m].sum()/1000,1))
# reverse: loop & tracks-PCN not covered by MP25
for name,lines in [("loop2025",loop),("tracksPCN",[t[4] for t in tr if t[2]=='Park Connector'])]:
    f=cover(lines,mpg); Ls=np.array([g.length for g in lines])
    print(name,"km NOT near MP25:",round(((1-f)*Ls).sum()/1000,1),"of",round(Ls.sum()/1000,1))
