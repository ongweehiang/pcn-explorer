# PCN Explorer

A map of Singapore's Park Connector Network (PCN) for following a park connector from one end to the other, or planning a route between MRT/LRT stations and hawker centres. It shows what's along the way (toilets, water points, hawker centres, shelters, bike repair stations) and tracks which connectors you've covered.

Two modes:
- **Whole connector** — pick a named connector (e.g. Kallang Park Connector, Rail Corridor, Round Island Route) and see it laid out end to end, with stops in order and how much of it you've done.
- **Point to point** — route between any two MRT/LRT stations or hawker centres, staying on connectors where possible.

**Live site:** https://ongweehiang.github.io/pcn-explorer/

## What's in this repo

| Path | What it is |
|---|---|
| `index.html` | The whole app: map, routing, stops along the route, coverage tracking, sync |
| `net.json` | The prebuilt network, stops and start/end points (built by `build/`) |
| `leaflet.css` | Map library styles |
| `apps-script/Code.gs` | Optional backend that syncs your progress to a Google Sheet |
| `build/` | Scripts that rebuild `net.json` from the source data |

## 1. Turn on GitHub Pages

Repo **Settings → Pages → Build and deployment**: Source *Deploy from a branch*, Branch `main`, folder `/ (root)`. The site appears at the address above within a minute or two.

## 2. Sync progress across devices (Google Sheet)

Without this, progress is saved in each browser separately.

1. Create a new Google Sheet (e.g. "PCN progress").
2. In the Sheet: **Extensions → Apps Script**. Replace the code with `apps-script/Code.gs` and save.
3. **Project Settings (gear) → Script properties → Add script property**: name `SECRET`, value a long random string (a password manager's generator is ideal). Keep it private.
4. **Deploy → New deployment → Select type: Web app**. *Execute as:* Me. *Who has access:* Anyone. Deploy, authorise, and copy the **Web app URL** (ends in `/exec`).
5. On the site, open **My PCN coverage → Sync settings**, paste the URL and the secret, and press **Save & sync**. Do this once on each device.

"Anyone" only means the URL works without a Google login; every request must carry your secret or it's refused. Your covered segments land in the **Segments** tab and your routes in the **Log** tab.

If you later edit `Code.gs`, use **Deploy → Manage deployments → Edit → New version** so the URL stays the same.

## 3. Rebuild the data (optional, every few months)

```bash
./build/run_all.sh      # ~10 minutes, then commit net.json
```

Your saved progress carries over: each covered segment is stored with its midpoint, so it's matched onto the rebuilt network.

## How the network is built

- **Base:** URA Master Plan 2025 park connector lines (incl. Round Island Route and Rail Corridor), plus NParks Park Connector Loop and NParks Tracks connector stretches the Master Plan doesn't have.
- **Cross-check:** every Master Plan line is compared with NParks Park Connector Loop, NParks Tracks, the 2012 NParks connector map and OpenStreetMap. Lines no other source shows are marked **unverified** (dashed orange) — they may be planned, not built — and routing avoids them a little.
- **Joining it up:** breaks between connectors are joined with real paths (park paths, OpenStreetMap footpaths, bridges and crossings). Anything left under 120 m is joined with a straight **gap** line (red) — usually a road crossing.
- **Whole connectors** (`build/5_routes.py`): connector stretches are grouped by name; each group's longest continuous line is its end-to-end route, and the rest are side branches. NParks' seven loops aren't included yet — their source lines overlap and break up too much to put in order reliably.
- **Routing** prefers connectors: link paths count about 2× their length, so routes stay mostly on the PCN. Cycle mode avoids steps and no-cycling paths.

## Data sources and licences

- data.gov.sg (Singapore Open Data Licence): NParks Park Connector Loop, NParks Park Connector, NParks Tracks, URA Master Plan 2025 Park Connector, URA Master Plan 2019 Planning Area Boundary, NEA Hawker Centres.
- © OpenStreetMap contributors (ODbL): toilets, water points, shelters, bike repair stations, footpaths, cycle paths, MRT/LRT stations.
- Street map tiles: OneMap © Singapore Land Authority.

`net.json` is a derived database of OpenStreetMap data and is shared under the ODbL.
