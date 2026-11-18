"""Download every source dataset PCN Explorer is built from, into build/data/.

Sources
  data.gov.sg (Open Data Licence): NParks Park Connector Loop, NParks Park Connector (2012),
    NParks Tracks, URA Master Plan 2025 Park Connector line, NEA Hawker Centres,
    URA Master Plan 2019 Planning Area boundaries
  OpenStreetMap via the Overpass API (ODbL): toilets, water points, shelters, cafés,
    food courts, bike repair stations, cycle paths, footpaths, MRT/LRT stations

Usage:  python3 build/fetch_data.py
"""
import json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('PCN_DATA', os.path.join(HERE, 'data'))
UA = {'User-Agent': 'pcn-explorer-build/1.0 (personal project)'}
BBOX = '(1.15,103.59,1.48,104.1)'
OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']

DATASETS = {
    'pcnloop': 'd_a69ef89737379f231d2ae93fd1c5707f',   # NParks Park Connector Loop
    'pcnline': 'd_b860850d042e90586f07c945dedec6fa',   # NParks Park Connector (2012)
    'tracks':  'd_306cc1018cb733346681883ee6d73054',   # NParks Tracks
    'mp25':    'd_cebde179d5cd6b85be36d618c8fe3b85',   # URA MP2025 Park Connector line
    'hawker':  'd_4a086da0a5553be1d89383cd90d07ecd',   # NEA Hawker Centres
    'areas':   'd_4765db0e87b9c86336792efe8a1f7a66',   # URA MP2019 Planning Area boundary
}


def get(url, data=None, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:
            if k == tries - 1:
                raise
            print('  retry', url[:60], e)
            time.sleep(5 * (k + 1))


def datagov(id_):
    meta = json.loads(get(f'https://api-open.data.gov.sg/v1/public/api/datasets/{id_}/poll-download'))
    if meta.get('code') != 0:
        raise RuntimeError(f'data.gov.sg {id_}: {meta}')
    return json.loads(get(meta['data']['url']))


def overpass(q):
    body = ('data=' + urllib.parse.quote(q)).encode()
    last = None
    for ep in OVERPASS * 2:
        try:
            t = get(ep, body, tries=1)
            if t[:1] == b'{':
                return json.loads(t)
            last = t[:200]
        except Exception as e:
            last = e
        time.sleep(10)
    raise RuntimeError(f'Overpass failed: {last}')


# ---------- transforms (kept identical to the original in-browser export) ----------
def r5(c):
    return [[round(p[0], 5), round(p[1], 5)] for p in c]


def lines(g):
    if not g:
        return []
    if g['type'] == 'LineString':
        return [r5(g['coordinates'])]
    if g['type'] == 'MultiLineString':
        return [r5(c) for c in g['coordinates']]
    return []


POI_TAGS = ['name', 'amenity', 'opening_hours', 'cuisine', 'brand', 'access', 'fee', 'unisex', 'wheelchair',
            'changing_table', 'description', 'operator', 'building']


def pack_main(loop, line, osm_pois, hawker):
    osm = []
    for e in osm_pois['elements']:
        t = {k: e['tags'][k] for k in POI_TAGS if e.get('tags', {}).get(k)}
        la = e.get('lat', (e.get('center') or {}).get('lat'))
        lo = e.get('lon', (e.get('center') or {}).get('lon'))
        if la is None:
            continue
        osm.append([e['type'][0] + str(e['id']), round(la, 5), round(lo, 5), t])
    return {
        'loop': [[f['properties'].get('PARK'), f['properties'].get('PCN_LOOP'), lines(f['geometry'])] for f in loop['features']],
        'line': [[f['properties'].get('NAME'), lines(f['geometry'])] for f in line['features']],
        'osm': osm,
        'hawker': hawker,
    }


def pack_tracks(tracks, mp):
    t = [[p.get('PARK'), p.get('TYPE'), p.get('PARK_TYPE'), p.get('ALLOW_CYCLING'), p.get('ALLOW_WALKING'), p.get('PATH_WIDTH'),
          lines(f['geometry'])] for f in tracks['features'] for p in [f['properties']]]
    m = [[f['properties'].get('CLASSIFCTN'), lines(f['geometry'])] for f in mp['features']]
    return {'tracks': t, 'mp': m}


def pack_cycleways(J):
    return {'ways': [[w['id'], w['tags'].get('highway'), w['tags'].get('name', ''), w['tags'].get('bicycle', ''),
                      w['tags'].get('foot', ''), w['tags'].get('access', ''),
                      w['tags'].get('bridge') or w['tags'].get('tunnel') or '',
                      [[round(p['lon'], 5), round(p['lat'], 5)] for p in w['geometry']]]
                     for w in J['elements'] if w.get('geometry')]}


def pack_footways(J):
    out = []
    for w in J['elements']:
        if not w.get('geometry'):
            continue
        t = w['tags']
        if any(x in (t.get('access') or '') for x in ('private', 'no')):
            continue
        out.append([w['id'], t.get('highway'), t.get('footway', ''), t.get('bridge') or t.get('tunnel') or '', t.get('bicycle', ''),
                    t.get('covered', ''), [[round(p['lon'], 5), round(p['lat'], 5)] for p in w['geometry']]])
    return out


def pack_stations(J):
    out = []
    for e in J['elements']:
        t = e.get('tags', {})
        la = e.get('lat', (e.get('center') or {}).get('lat'))
        lo = e.get('lon', (e.get('center') or {}).get('lon'))
        if la is None:
            continue
        out.append([e['type'][0] + str(e['id']), t.get('name', ''), t.get('name:en', ''), t.get('station') or t.get('railway') or '',
                    t.get('network', ''), t.get('ref', ''), round(la, 5), round(lo, 5)])
    return out


def pack_areas(J):
    out = []
    for f in J['features']:
        g = f['geometry']
        polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        out.append([f['properties'].get('PLN_AREA_N', ''), [[[[round(p[0], 4), round(p[1], 4)] for p in ring] for ring in pl] for pl in polys]])
    return out


Q_POIS = f'[out:json][timeout:180];(' + ''.join(
    f'nwr["amenity"="{a}"]{BBOX};' for a in ['toilets', 'drinking_water', 'cafe', 'food_court', 'shelter', 'bicycle_repair_station', 'marketplace']
) + ');out center tags;'
Q_CYCLE = (f'[out:json][timeout:240];(way["highway"="cycleway"]{BBOX};way["highway"="path"]{BBOX};'
           f'way["highway"~"footway|pedestrian|track|service"]["bicycle"~"yes|designated"]{BBOX};'
           f'way["name"~"Park Connector|PCN|Round Island|Rail Corridor",i]{BBOX};);out geom;')
Q_FOOT = f'[out:json][timeout:300];(way["highway"~"^(footway|pedestrian|steps|living_street)$"]{BBOX};);out geom;'
Q_STATIONS = (f'[out:json][timeout:120];(nwr["railway"="station"]{BBOX};nwr["public_transport"="station"]{BBOX};'
              f'node["railway"="stop"]["subway"="yes"]{BBOX};);out center tags;')


def save(name, obj):
    p = os.path.join(DATA, name)
    with open(p, 'w') as f:
        json.dump(obj, f, separators=(',', ':'), ensure_ascii=False)
    print(f'  wrote {name} ({os.path.getsize(p) / 1e6:.1f} MB)')


def main():
    os.makedirs(DATA, exist_ok=True)
    print('data.gov.sg…')
    d = {k: datagov(v) for k, v in DATASETS.items()}
    print('OpenStreetMap…')
    pois = overpass(Q_POIS)
    cyc = overpass(Q_CYCLE)
    foot = overpass(Q_FOOT)
    st = overpass(Q_STATIONS)
    save('pcn_data.json', pack_main(d['pcnloop'], d['pcnline'], pois, d['hawker']))
    save('pcn_tracks.json', pack_tracks(d['tracks'], d['mp25']))
    save('pcn_osm.json', pack_cycleways(cyc))
    save('pcn_osm_foot.json', pack_footways(foot))
    save('pcn_stations2.json', pack_stations(st))
    save('pcn_areas.json', pack_areas(d['areas']))
    print('done')


if __name__ == '__main__':
    sys.exit(main())
