# Getting the official data

Portals change and several need a free registration or an official request, so verify each link and licence. Save files under `data/raw/`, then edit the matching layer in `config.yaml` (`enabled: true`, correct `path`, `attr`, `mapping`) and run `make build`.

| Need | Official source | What to get | How it plugs in |
|---|---|---|---|
| Landslide susceptibility | GSI **Bhukosh** (bhukosh.gsi.gov.in), National Landslide Susceptibility Mapping | NLSM raster or shapefile, landslide inventory | Raster: set `kind: raster`, `mapping` from class value to score. Shapefile: `kind: polygon`, set `attr` |
| Landslide history | GSI Landslide inventory (Bhukosh); NASA Global Landslide Catalog | Point events with date and fatalities | NASA one is fetched by `make fetch`. Convert GSI points to `name,type,year,lon,lat,deaths` and list in `events:` |
| Earthquake zones | BIS **IS 1893:2016** seismic zone map; BMTPC Vulnerability Atlas of India | Zone II to V polygons (digitise the map if no GIS file is published) | `kind: polygon`, `attr: ZONE`, `mapping: {II: .2, III: .4, IV: .7, V: 1}` |
| Earthquake history | National Center for Seismology (seismo.gov.in) catalogue; USGS ComCat | Magnitude, location, date | USGS is fetched by `make fetch`. Add NCS rows in the same CSV format |
| Flood hazard | NRSC/ISRO **Bhuvan** flood hazard atlases and NDEM; Rashtriya Barh Ayog flood-prone area maps; state flood-hazard zonation | Flood-prone or hazard-class polygons | `kind: polygon`, set `attr` and `mapping` (Low/Moderate/High to 0.3/0.6/0.9) |
| Flood history and river levels | **CWC** flood forecasting and **India-WRIS** (indiawris.gov.in): gauge stations, danger levels, historical peaks | Station tables, Flood Hazard/Danger-level exceedances | Convert flood events to the events CSV. Danger-level exceedance years are good event records |
| Cloudburst and rainfall | **IMD** gridded rainfall (imdpune.gov.in; Python package `imdlib`), CHIRPS (UCSB CHC) | Daily rainfall grids | Next step: use extreme-rainfall percentiles as a live multiplier on landslide and flood scores |
| Elevation and slope | SRTM (NASA Earthdata, free login), Cartosat DEM via Bhuvan | DEM tiles | Derive slope with `gdaldem slope`. Use it for candidate-site screening (`slope_deg`) |
| Habitations and population | **Census of India** Primary Census Abstract (village level), SECC, state village directories, Survey of India boundaries | Village name, population, coordinates | Build `data/raw/habitations.csv`: `name,lon,lat,population,vulnerable_share` |
| Candidate relocation land | State revenue department land records, panchayat and forest-department parcels | Parcel centroid, area, slope, water, road distance | Build `data/raw/candidate_sites.csv` |
| **Shelters / relief camps (live)** | State SDMA relief-camp registers, NDMA's National Emergency Response System, or your own **Rakshak ResQ** deployment's `evacuationZones` API | Name, coordinates, capacity, current occupancy | Build `data/raw/shelters.csv` (same columns as `data/seed/shelters_sample.csv`), or point the build step at a live URL instead of a file — see "Making shelters actually real-time" below |
| Past relocation outcomes | State DMA and NDMA reports, World Bank project documents (Latur/Killari, Bhuj, Kosi) | Households moved, cost, return rates | Use to tune `persons_per_ha` and site rules |

## The AI layer: what it actually is
`scripts/build_hazard.py`'s `ml_kde_layer()` fits a **Kernel Density Estimate**
(`sklearn.neighbors.KernelDensity`, haversine metric, gaussian kernel) per
hazard type on the real lat/lon of historical disasters, weighted by
`log(1+deaths)` so severe events pull more weight. This is a legitimate,
widely-used technique in seismic and landslide susceptibility research for
turning a point catalogue of past events into a continuous likelihood
surface — it is genuinely trained on data, not hand-tuned. The hand-drawn
`seed_regions` only fill in where a hazard type has fewer than `min_events`
(default 4) events to fit a density on — check the build log for lines like
`ML/earthquake: KernelDensity trained on 8 real events` to see which hazards
are model-driven versus prior-driven for your current dataset. As you add
more events (via `make fetch`, or your own GSI/NCS/CWC records), more of the
map becomes genuinely learned rather than assumed. A natural next step once
you have real slope/rainfall rasters: swap the unsupervised KDE for a
supervised classifier (e.g. `RandomForestClassifier` or `XGBoost`) trained on
event-cells vs. background-cells with slope, rainfall and lithology as
features — `min_events` and the KDE bandwidths in `config.yaml` are the place
to start tuning either way.

## Making shelters actually real-time
Right now `web/data/shelters.json` is a static file, regenerated whenever the
pipeline runs (see the CI workflow below for how often that is). To make it
genuinely live:
1. Stand up an endpoint that returns the same shape as `shelters.json`
   (`{is_sample, generated_at, shelters: [...]}`) — if you're running
   **Rakshak ResQ**, its `evacuationZones` table already tracks capacity and
   occupancy, so add a small `GET /api/evacuation-zones/public` route there
   that returns it in this shape.
2. In `web/index.html`, change `loadShelters()`'s fetch URL from
   `data/shelters.json` to your endpoint's full URL (it must allow
   cross-origin requests — add CORS headers on that route).
3. Remove the `is_sample` labelling once it's a real feed.

## Making the map refresh itself (already wired up)
`.github/workflows/pages.yml` now runs the whole pipeline — `fetch_open_data.py`,
`build_hazard.py`, `plan_relocation.py` — on GitHub's own servers every 6
hours (`cron: "0 */6 * * *"`), not just when you push code. GitHub's runners
have full internet access, so this is what actually pulls live USGS
earthquakes and NASA landslide reports and retrains the KDE model on them,
then republishes the site automatically. Tighten the schedule once you have
a rainfall or shelter feed frequent enough to justify it.

## Steps
1. Run `make fetch`. Open sources (USGS, NASA GLC, boundaries) download automatically. If one fails, its message tells you to fetch it by hand.
2. Download each official layer you can access. If a portal offers only a PDF map, use QGIS to georeference and digitise it.
3. Open each file in QGIS: check the CRS, the attribute column and the class values, and write them into `config.yaml`.
4. Set `seed_regions` to `enabled: false` once you have enough real events (4+ per hazard type) for the KDE model to take over, or once official hazard layers cover all three hazards.
5. Run `make build`, then `make backtest` to see how held-out events fall on the map.
6. Prepare habitations, candidate sites and shelters, then run `make relocate`.
7. Have geologists and district officials verify the top-ranked habitations on site before any relocation decision.

## Notes
- Earthquake hazard is not a relocation trigger in this tool. It reports retrofit advice, since shaking cannot be avoided by moving a few km.
- The grid is about 5.5 km (`resolution_deg: 0.05`). For village-level decisions, rasterise at 30 m in a smaller area.
- Event weights and the risk formula are transparent starting points. Calibrate them with local experts.
- **Unverified from this environment:** the USGS earthquake API is a long-established, stable public API and should work as written. The NASA Global Landslide Catalog and geoBoundaries endpoints in `fetch_open_data.py` were written from general knowledge of those APIs but could not be tested here (no outbound internet access in this sandbox to anything outside a short allowlist). The first time the GitHub Actions workflow runs (which does have real internet access), check its log — `continue-on-error` on those two steps means a broken URL won't stop deployment, but it will silently mean that source isn't updating. If a step fails, paste me the error and I'll fix the endpoint.

