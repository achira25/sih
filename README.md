# India Red Zone Atlas

AI-driven, GIS-based red-zone mapping for India (flood, landslide,
earthquake), a live shelters/relief-camp layer, and a relocation planner that
ranks vulnerable habitations and assigns them to safe candidate sites within
capacity — matching the SIH problem statement's ask for real-time hazard
mapping, carrying-capacity assessment, and relocation prioritisation for
State Disaster Management Authorities.

**Status:** the pipeline and web app work end to end and were tested in this
build (see "What's verified" below). Out of the box, the hazard model is
trained on 20 documented disasters and the shelters layer uses clearly
labelled SAMPLE data — both should be replaced with official GSI/NDMA/CWC/
BMTPC/SDMA data before this is used for real decisions (see
`docs/DATA_SOURCES.md`).

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make fetch       # USGS quakes, NASA landslides, real India boundaries (needs internet)
make build       # trains the KDE hazard model, writes the heatmap + shelters feed
make relocate    # ranks habitations, assigns sites (uses sample inputs until you add yours)
make serve       # open http://localhost:8000
```
Without `make`: run `python scripts/<name>.py` in the same order. On GitHub,
none of this is manual — see "Real-time updates" below.

## How it works
1. **AI hazard model:** `scripts/build_hazard.py`'s `ml_kde_layer()` fits a
   **Kernel Density Estimate** (`sklearn.neighbors.KernelDensity`, haversine
   metric) per hazard type on the real coordinates of historical disasters,
   weighted by severity (`log(1+deaths)`). This is genuinely trained on data
   — the standard approach in real seismic/landslide susceptibility research
   for turning a point catalogue of past events into a continuous likelihood
   surface. Hand-drawn `seed_regions` (in `config.yaml`) only fill in for a
   hazard type with fewer than 4 events to train on.
2. **History reinforcement:** each individual documented event additionally
   adds a small local bump, so a specific well-documented disaster site
   stays visibly flagged even where the broader KDE surface is lower.
3. **Red zone:** score of 0.7 or more, on a ~5.5 km grid (`resolution_deg:
   0.05`). `scores.bin` and four PNG heatmaps go to `web/data/`.
4. **Habitation risk:** `100 x (0.7 x max(flood, landslide) + 0.3 x
   vulnerable share)`. Phases: Immediate 60+, Short-term 45+, Medium-term
   30+, else Monitor (thresholds editable in `config.yaml`).
5. **Relocation sites:** candidate land must be in low-hazard cells and
   gentle slope. Capacity is `area_ha x persons_per_ha x suitability`, and
   habitations are assigned greedily by risk, nearest eligible site first.
6. **Shelters (live layer):** `web/data/shelters.json` carries capacity and
   current occupancy per shelter; the web app polls it every 20 seconds and
   shows a "last updated Xs ago" indicator, colouring shelters green/amber/
   red by how full they are. Ships with SAMPLE data — see
   "Making shelters actually real-time" in `docs/DATA_SOURCES.md` for
   pointing it at a live feed (Rakshak ResQ's `evacuationZones` table is a
   natural source).
7. **Web app:** click anywhere for hazard scores, nearby events and advice.
   Click a habitation, shelter, or past disaster marker for its detail.

## Real-time updates
`.github/workflows/pages.yml` runs the full pipeline on GitHub's own servers
— not just your laptop — every 6 hours as well as on every push:
`fetch_open_data.py` (live USGS earthquakes, NASA landslide reports, real
India state boundaries) → `build_hazard.py` (retrains the KDE model) →
`plan_relocation.py` → publish. GitHub's runners have full internet access,
so this is what actually keeps the map current without anyone touching it.

## Rakshak ResQ (linked, not merged)
This repo is the standalone PS deliverable — mapping, red zones, relocation
planning. It intentionally does **not** contain Rakshak ResQ's source code
(the separate SOS/evacuation/chat app). The web app has an "Open Rakshak
ResQ" button (in `web/index.html`) that links out to it instead. To point it
at your Rakshak ResQ deployment, edit `web/partners.config.js`:
```js
window.PARTNERS = { RAKSHAK_RESQ_URL: "https://your-rakshak-resq-url" };
```
Use its live deployed URL once you have one; until then, point it at the
Rakshak ResQ GitHub repo or a release `.zip` link. Leaving it blank disables
the button (with a tooltip explaining why) rather than linking to a dead URL.

## Layout
```
config.yaml   scripts/ (fetch_open_data, build_hazard [KDE model], plan_relocation, backtest)
data/seed/    data/raw/ (official downloads)   data/processed/
web/          web/partners.config.js (Rakshak ResQ link, no code copied in)
docs/DATA_SOURCES.md   .github/workflows/pages.yml (live 6-hourly rebuild)
```

## Publish on GitHub Pages
```bash
git init && git add . && git commit -m "Initial commit"
git branch -M main && git remote add origin https://github.com/<you>/india-redzone-atlas.git
git push -u origin main
```
Then in the repo: Settings, Pages, Source: GitHub Actions. You don't need to
commit `web/data/` yourself — the workflow regenerates it on GitHub before
every publish.

## What's verified vs. not
Tested in this build: the KDE model trains successfully on the real event
data (check the build log for `ML/<hazard>: KernelDensity trained on N real
events`), the shelters feed generates and serves correctly, the page's
JavaScript passes a syntax check, and the higher-resolution (0.05°) grid
builds without error. **Not verified from this environment** (no outbound
internet access here beyond a short allowlist): the NASA Global Landslide
Catalog and geoBoundaries API calls in `fetch_open_data.py` were written from
general knowledge of those APIs but never actually executed — the USGS
earthquake API is a long-established one I'm confident in. The GitHub
Actions workflow, which does have real internet access, is the actual first
test; `continue-on-error` means a broken endpoint won't block deployment, but
check the Actions log after the first run and tell me if a step fails.

## Limits
- Seed regions (used only where a hazard type has too few events for KDE) are simplified approximations. Fatality numbers are rounded from widely reported figures.
- The grid is 5.5 km, so this is regional screening, not parcel-level assessment.
- Backtesting on a small event set is a sanity check, not validation.
- Shelters data is SAMPLE until you wire in a real feed.
- OpenStreetMap tiles are for light use. For heavy traffic use a tile provider.
- Boundaries from geoBoundaries may differ from the official Survey of India outline.

## Roadmap
Supervised classifier (RandomForest/XGBoost) on slope + rainfall + lithology once those rasters are in, live IMD rainfall multiplier, 30 m district rasters, PostGIS and FastAPI backend, SDMA login and alerts, a real live shelters feed.

