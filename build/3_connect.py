"""Step 3: join broken pieces using real paths (park paths, OSM footpaths/bridges), then short straight gaps."""
import os
DD=os.environ.get('PCN_DATA',os.path.join(os.path.dirname(os.path.abspath(__file__)),'data'))+'/'
import pickle, json, networkx as nx, numpy as np
from shapely.geometry import LineString, Point
from shapely import STRtree
allL,G=pickle.load(open(DD+'graph.pkl','rb'))
isP=lambda d: allL[d['src']]['kind']=='pcn'
GP=nx.Graph(); GL=nx.Graph()
for u,v,d in G.edges(data=True):
    if isP(d):
        if not GP.has_edge(u,v) or GP[u][v]['len']>d['len']: GP.add_edge(u,v,**d)
    else:
        if not GL.has_edge(u,v) or GL[u][v]['len']>d['len']: GL.add_edge(u,v,**d)
km=lambda H,c: sum(d['len'] for *_,d in H.subgraph(c).edges(data=True))/1000
cc=sorted(nx.connected_components(GP),key=lambda c:-km(GP,c))
comp={n:i for i,c in enumerate(cc) for n in c}
print("PCN-only components",len(cc),"largest km",[round(km(GP,c),1) for c in cc[:10]])
# bridging via links from every dead end AND every node of small comps (<2km)
keep=set(); bridges=0
dead=[n for n in GP if GP.degree(n)==1]
starts=set(dead)
for i,c in enumerate(cc):
    if km(GP,c)<3: starts|=set(c)
print("dead ends",len(dead),"start nodes",len(starts))
for u in starts:
    if u not in GL: continue
    dist,path=nx.single_source_dijkstra(GL,u,cutoff=800,weight='len')
    best={}
    for n,dn in dist.items():
        if n in comp and comp[n]!=comp[u]:
            cid=comp[n]
            if cid not in best or dn<best[cid][0]: best[cid]=(dn,n)
    for cid,(dn,n) in best.items():
        p=path[n]
        for a,b in zip(p[:-1],p[1:]): keep.add(frozenset((a,b)))
        bridges+=1
print("link bridges",bridges,"link edges kept",len(keep))
H=nx.Graph(GP)
for e in keep:
    a,b=tuple(e)
    if not H.has_edge(a,b): H.add_edge(a,b,**GL[a][b])
# shortcut pass: link paths much shorter than current network distance (missing bridges/crossings)
pcn_nodes=list(GP.nodes()); sc=0
for u in pcn_nodes:
    if u not in GL: continue
    dl,pl=nx.single_source_dijkstra(GL,u,cutoff=700,weight="len")
    targets=[(d,v) for v,d in dl.items() if v in GP and v!=u and d>=15]
    if not targets: continue
    dh=nx.single_source_dijkstra_path_length(H,u,cutoff=2500,weight="len")
    for d,v in sorted(targets):
        if dh.get(v,1e9) > 2.2*d+250:
            p=pl[v]
            for a_,b_ in zip(p[:-1],p[1:]):
                if not H.has_edge(a_,b_): H.add_edge(a_,b_,**GL[a_][b_])
            sc+=1
            dh=nx.single_source_dijkstra_path_length(H,u,cutoff=2500,weight="len")
print("shortcuts added",sc)
# straight crossings: iteratively join each component to nearest other component within 120m
cross=0
for it in range(6):
    ccs=list(nx.connected_components(H)); comp2={n:i for i,c in enumerate(ccs) for n in c}
    nodes=list(H.nodes()); pts=[Point(n) for n in nodes]; t=STRtree(pts)
    added=0
    for c in sorted(ccs,key=len)[:-1]:
        best=None
        for u in c:
            for j in t.query(Point(u),predicate='dwithin',distance=120):
                v=nodes[j]
                if comp2[v]==comp2[u]: continue
                d=Point(u).distance(pts[j])
                if best is None or d<best[0]: best=(d,u,v)
        if best:
            d,u,v=best
            if comp2[u]!=comp2[v]:
                H.add_edge(u,v,len=d,src=-1,g=LineString([u,v])); cross+=1; added+=1
                cu,cv=comp2[u],comp2[v]
                for n in list(comp2):
                    if comp2[n]==cv: comp2[n]=cu
    if not added: break
print("straight crossings added",cross)
cc3=sorted(nx.connected_components(H),key=lambda c:-km(H,c))
pk=lambda c: sum(d['len'] for *_,d in H.subgraph(c).edges(data=True) if d['src']>=0 and allL[d['src']]['kind']=='pcn')/1000
totp=sum(pk(c) for c in cc3)
print("final components",len(cc3),"PCN km per comp",[round(pk(c),1) for c in cc3[:12]],"total PCN km",round(totp,1))
print("share of PCN km in largest",round(pk(cc3[0])/totp*100,1))
small=[(round(pk(c),2),np.mean([n[0] for n in c]),np.mean([n[1] for n in c])) for c in cc3[1:] if pk(c)>0.3]
print("isolated pieces >300m:",len(small))
pickle.dump((allL,H,cc3),open(DD+'net.pkl','wb'))
