"""Step 4: write ../net.json — the routable network, stops along it, start/end points and the area basemap."""
import os
DD=os.environ.get('PCN_DATA',os.path.join(os.path.dirname(os.path.abspath(__file__)),'data'))+'/'
import pickle, math, json, re, numpy as np, networkx as nx
from shapely.geometry import LineString, Point
from shapely import STRtree
from pyproj import Transformer
from collections import defaultdict, Counter
T=Transformer.from_crs(4326,3414,always_xy=True).transform
TI=Transformer.from_crs(3414,4326,always_xy=True).transform
allL,H,cc=pickle.load(open(DD+'net.pkl','rb'))
O=json.load(open(DD+'pcn_data.json')); TR=json.load(open(DD+'pcn_tracks.json'))
# duplicate flag for loop-only pieces parallel to MP25
mp=[a['g'] for a in allL if a['kind']=='pcn' and a['src'].startswith('MP25')]; tmp=STRtree(mp)
dup=set()
for i,a in enumerate(allL):
    if a.get('src') in ('NParks loop','NParks tracks'):
        g=a['g']; n=max(2,int(g.length/10)); pts=[g.interpolate(d) for d in np.linspace(0,g.length,n)]
        if len(set(tmp.query(pts,predicate='dwithin',distance=40)[0]))/n>=0.8: dup.add(i)
def cls_of(d):
    s=d['src']
    if s<0: return 3
    a=allL[s]
    if a['kind']=='pcn':
        if s in dup: return 2
        return 0 if a['status']=='confirmed' else 1
    return 4 if a.get('stairs') else (5 if a.get('cyc')=='N' else 2)
def name_of(d):
    s=d['src']; return '' if s<0 else (allL[s].get('name') or '')
def loop_of(d):
    s=d['src']
    if s<0 or allL[s]['kind']!='pcn': return ''
    lp=allL[s].get('loop') or ''
    return 'Central Urban Loop' if lp=='Urban Central Loop' else lp
# keep components with >=0.3km
keepn=set().union(*[c for c in cc if sum(d['len'] for *_,d in H.subgraph(c).edges(data=True))>300])
G=H.subgraph(keepn).copy()
for u,v,d in G.edges(data=True): d['cls']=cls_of(d); d['name']=name_of(d); d['loop']=loop_of(d); d['coords']=list(d['g'].coords)
# orient coords so they start at u
def oriented(d,u):
    c=d['coords']
    return c if (abs(c[0][0]-u[0])+abs(c[0][1]-u[1]))<(abs(c[-1][0]-u[0])+abs(c[-1][1]-u[1])) else c[::-1]
# contract degree-2 chains with same cls & name
changed=True
while changed:
    changed=False
    for n in list(G.nodes()):
        if G.degree(n)!=2: continue
        (a,),(b,)=[ [x] for x in G.neighbors(n)] if len(list(G.neighbors(n)))==2 else ([None],[None])
        if a is None or a==b: continue
        d1=G[a][n]; d2=G[n][b]
        if d1['cls']!=d2['cls'] or d1['name']!=d2['name'] or d1['loop']!=d2['loop']: continue
        if G.has_edge(a,b): continue
        c=oriented(d1,a)+oriented(d2,n)[1:]
        G.remove_node(n); G.add_edge(a,b,len=d1['len']+d2['len'],cls=d1['cls'],name=d1['name'],loop=d1['loop'],coords=c,src=d1['src']); changed=True
print("contracted:",G.number_of_nodes(),"nodes",G.number_of_edges(),"edges")
nodes=list(G.nodes()); nid={n:i for i,n in enumerate(nodes)}
names=['']; nidx={'':0}; loops=['']; lidx={'':0}
E=[]; geoms=[]
for u,v,d in G.edges(data=True):
    g=LineString(oriented(d,u)).simplify(1.0)
    ll=[TI(x,y) for x,y in g.coords]
    q=[(round(x*1e5),round(y*1e5)) for x,y in ll]
    flat=[q[0][0],q[0][1]]
    for i in range(1,len(q)): flat+= [q[i][0]-q[i-1][0], q[i][1]-q[i-1][1]]
    nm=d['name']
    if nm not in nidx: nidx[nm]=len(names); names.append(nm)
    if d['loop'] not in lidx: lidx[d['loop']]=len(loops); loops.append(d['loop'])
    E.append([nid[u],nid[v],round(d['len']),d['cls'],nidx[nm],flat,lidx[d['loop']]]); geoms.append(g)
Nll=[[round(TI(*n)[0]*1e5),round(TI(*n)[1]*1e5)] for n in nodes]
km=Counter()
for e in E: km[e[3]]+=e[2]/1000
print("km by class",{k:round(v,1) for k,v in sorted(km.items())})
etree=STRtree(geoms)
# ---------- POIs ----------
pois=[]
def addpoi(cat,name,lon,lat,info,maxd):
    p=Point(T(lon,lat))
    idx=etree.query(p,predicate='dwithin',distance=maxd)
    if len(idx)==0: return
    ds=sorted((geoms[j].distance(p),j) for j in idx)[:4]
    near=[[int(j),round(d),round(geoms[j].project(p)/max(geoms[j].length,1),3)] for d,j in ds]
    pois.append([cat,name,round(lon,5),round(lat,5),info,near])
Hk=O['hawker']['features']; nea=[]
for f in Hk:
    p=f['properties']
    if p['STATUS']=='Under Construction': continue
    lon,lat=f['geometry']['coordinates'][:2]; nea.append(Point(T(lon,lat)))
    info={'addr':p.get('ADDRESS_MYENV'),'stalls':p.get('NUMBER_OF_COOKED_FOOD_STALLS'),'src':'NEA'}
    addpoi('hawker',p['NAME'],lon,lat,info,500)
neat=STRtree(nea)
cnt=Counter()
for oid,lat,lon,t in O['osm']:
    a=t.get('amenity'); nm=t.get('name','')
    info={k:v for k,v in t.items() if k in ('opening_hours','cuisine','brand','fee','wheelchair','operator','access')}
    info['osm']=oid
    if a=='toilets':
        if t.get('access') in ('private','customers','no'): continue
        addpoi('toilet',nm or 'Public toilet',lon,lat,info,150)
    elif a=='drinking_water': addpoi('water',nm or 'Water point',lon,lat,info,100)
    elif a=='bicycle_repair_station': addpoi('repair',nm or 'Bike repair station',lon,lat,info,150)
    elif a=='shelter': addpoi('shelter',nm or 'Shelter',lon,lat,info,30)
    elif a in ('food_court','marketplace'):
        p=Point(T(lon,lat))
        if len(neat.query(p,predicate='dwithin',distance=150)): continue  # already an NEA hawker centre
        if re.search(r'hawker|food cent|food centre|market',nm,re.I) and a!='marketplace' or re.search(r'hawker|food cent',nm,re.I):
            info['src']='OSM'; addpoi('hawker',nm,lon,lat,info,500)
for p in pois: cnt[p[0]]+=1
print("POIs near network",dict(cnt))
def areas():
    from shapely.geometry import Polygon, MultiPolygon
    A=json.load(open(DD+'pcn_areas.json')); res=[]
    for name,polys in A:
        ps=[Polygon(p[0],p[1:]) for p in polys if len(p[0])>=4]
        g=MultiPolygon(ps).buffer(0).simplify(0.0004)
        gs=[g] if g.geom_type=='Polygon' else list(g.geoms)
        rings=[[[round(x,4),round(y,4)] for x,y in pg.exterior.coords] for pg in gs if pg.area>1e-6]
        c=g.representative_point(); res.append([name.title(),[round(c.x,4),round(c.y,4)],rings])
    return res
# ---------- waypoints ----------
mainset=set(nid[n] for n in cc[0] if n in nid)
mainnodes=[i for i in range(len(nodes)) if i in mainset]
ntree=STRtree([Point(nodes[i]) for i in mainnodes])
def snap(lon,lat,maxd):
    p=Point(T(lon,lat)); j=ntree.query_nearest(p,max_distance=maxd)
    if len(j)==0: return None
    i=mainnodes[j[0]]; return i, round(Point(nodes[i]).distance(p))
wps=[]
S=json.load(open(DD+'pcn_stations2.json'))
st=defaultdict(list)
for sid,nm,en,typ,net,ref,lat,lon in S:
    if typ in ('subway','light_rail','monorail') and nm:
        nm=re.sub(r'\s+(MRT|LRT)( Station)?$','',nm); st[nm].append((lon,lat,typ,ref))
for nm,L in st.items():
    lon=np.mean([x[0] for x in L]); lat=np.mean([x[1] for x in L])
    typ='LRT' if all(x[2]!='subway' for x in L) else 'MRT'
    refs=' / '.join(sorted({r.strip() for x in L if x[3] for r in x[3].split(';') if re.match(r'^[A-Z]{2}\d+$',r.strip())}))
    s=snap(lon,lat,600)
    if s: wps.append(['station',f"{nm} {typ}"+(f" ({refs})" if refs else ''),s[0],s[1],round(lon,5),round(lat,5)])
for p in pois:
    if p[0]=='hawker':
        s=snap(p[2],p[3],500)
        if s: wps.append(['hawker',p[1],s[0],s[1],p[2],p[3]])
print("waypoints",Counter(w[0] for w in wps))
out=dict(nodes=Nll,edges=E,names=names,loops=loops,pois=pois,wps=wps,mainComp=sorted(mainset),
  meta=dict(built=__import__('datetime').date.today().isoformat(),version=__import__('datetime').datetime.now().strftime('%Y-%m-%d-%H%M'),sources=['NParks Park Connector Loop (data.gov.sg, 2025)','URA Master Plan 2025 Park Connector line (data.gov.sg, Dec 2025)','NParks Tracks (data.gov.sg, Aug 2025)','NParks Park Connector (2012)','NEA Hawker Centres (data.gov.sg)','OpenStreetMap contributors (ODbL), '+__import__('datetime').date.today().strftime('%b %Y')]))
out['areas']=areas()
s=json.dumps(out,separators=(',',':'),ensure_ascii=False)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','net.json'),'w').write(s); print("bytes",len(s.encode()))
