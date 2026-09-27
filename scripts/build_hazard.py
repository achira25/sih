"""Combine hazard layers + historical events into scores and web outputs."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
from common import *

def _k(a):
    s = str(a).strip()
    try:
        f = float(s); return str(int(f)) if f == int(f) else s
    except ValueError:
        return s

def load_events(paths=None):
    c = cfg(); frames = []
    for p in paths or c["events"]:
        if (ROOT / p).exists(): frames.append(pd.read_csv(ROOT / p))
        else: print("skip events (missing):", p)
    ev = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["name","type","year","lon","lat","deaths"])
    for col, d in (("weight", np.nan), ("show", 1), ("deaths", 0)):
        if col not in ev: ev[col] = d
    ev["weight"] = ev["weight"].fillna(c["default_event_weight"]); ev["show"] = ev["show"].fillna(1)
    return ev.dropna(subset=["lon", "lat", "type"])

def _polygon(L, path):
    import geopandas as gpd
    from rasterio import features
    from rasterio.transform import from_origin
    g = gpd.read_file(path).to_crs(4326); m = {_k(a): v for a, v in L["mapping"].items()}
    shapes = sorted(((geo, m[_k(a)]) for geo, a in zip(g.geometry, g[L["attr"]]) if _k(a) in m), key=lambda s: s[1])
    if not shapes: return np.zeros((NY, NX), np.float32)
    return features.rasterize(shapes, out_shape=(NY, NX), transform=from_origin(W, N, RES, RES), fill=0, dtype="float32")

def _raster(L, path):
    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_origin
    dst = np.zeros((NY, NX), np.float32)
    with rasterio.open(path) as s:
        reproject(rasterio.band(s, 1), dst, src_nodata=s.nodata, dst_transform=from_origin(W, N, RES, RES),
                  dst_crs="EPSG:4326", resampling=Resampling.mode if "mapping" in L else Resampling.average)
    if "mapping" in L:
        out = np.zeros_like(dst)
        for k, v in L["mapping"].items(): out[dst == float(k)] = v
        return out
    lo, hi = L["scale"]; return np.clip((dst - lo) / (hi - lo), 0, 1)

def ml_kde_layer(ev, c):
    """Real, trained machine learning: a Kernel Density Estimate (KDE) fit on
    the actual lat/lon of historical disasters (weighted by severity), one
    model per hazard type. This is what actually drives the map now, not the
    hand-drawn seed circles -- KDE is the standard approach used in real
    seismic/landslide susceptibility studies for turning a point catalogue of
    past events into a continuous likelihood surface. Falls back to zero
    (letting seed_regions and any official layers carry that hazard type) if
    there are too few events to fit a meaningful density.
    """
    ml_cfg = c.get("ml", {})
    if not ml_cfg.get("enabled", True):
        return {t: np.zeros((NY, NX), np.float32) for t in TYPES}
    from sklearn.neighbors import KernelDensity
    LON, LAT = lon_lat_grid()
    grid_rad = np.radians(np.stack([LAT.ravel(), LON.ravel()], axis=1))  # haversine wants (lat, lon)
    bw_km = ml_cfg.get("bandwidth_km", {"flood": 120, "landslide": 80, "earthquake": 150})
    min_events = ml_cfg.get("min_events", 4)
    out = {}
    for t in TYPES:
        sub = ev[ev.type == t].dropna(subset=["lat", "lon"])
        if len(sub) < min_events:
            print(f"  ML/{t}: only {len(sub)} events (need {min_events}+), skipping KDE for this hazard")
            out[t] = np.zeros((NY, NX), np.float32)
            continue
        X = np.radians(sub[["lat", "lon"]].values)
        sample_weight = np.log1p(sub["deaths"].fillna(0).values) + 1  # severity-weighted, never zero
        kde = KernelDensity(bandwidth=bw_km.get(t, 100) / 6371.0, metric="haversine", kernel="gaussian")
        kde.fit(X, sample_weight=sample_weight)
        density = np.exp(kde.score_samples(grid_rad)).reshape(NY, NX)
        out[t] = (density / density.max()).astype(np.float32) if density.max() > 0 else density.astype(np.float32)
        print(f"  ML/{t}: KernelDensity trained on {len(sub)} real events, bandwidth {bw_km.get(t, 100)} km")
    return out

def layer_scores(c):
    LON, LAT = lon_lat_grid(); out = {t: np.zeros((NY, NX), np.float32) for t in TYPES}
    for L in c["layers"]:
        if not L.get("enabled"): continue
        path = ROOT / L["path"]
        if not path.exists(): print("skip layer (missing file):", L["name"]); continue
        if L["kind"] == "gaussian":
            for r in pd.read_csv(path).itertuples():
                d2 = ((LON - r.lon) ** 2 + (LAT - r.lat) ** 2) / r.radius ** 2
                out[r.type] = np.maximum(out[r.type], r.level / 3 * .85 * np.exp(-d2))
        else:
            fn = _polygon if L["kind"] == "polygon" else _raster
            out[L["type"]] = np.maximum(out[L["type"]], fn(L, path))
        print("layer used:", L["name"])
    return out

def compute(ev, c=None):
    c = c or cfg(); s = layer_scores(c); LON, LAT = lon_lat_grid(); k = c["event_kernel_deg"]
    # Blend in the trained KDE hazard model: where the ML layer has learned a
    # real signal from event data, let it raise the score above the hand-drawn
    # seed-region prior (max, not average, so a well-evidenced hazard isn't
    # diluted by a conservative seed region drawn before all the data was in).
    ml_cfg = c.get("ml", {}); ml_weight = ml_cfg.get("weight", 0.9)
    ml_scores = ml_kde_layer(ev, c)
    for t in TYPES:
        s[t] = np.maximum(s[t], ml_scores[t] * ml_weight)
    w = int(3 * k / RES)
    for r in ev.itertuples():
        if r.type not in s: continue
        i, j = cell(r.lon, r.lat); i0, i1, j0, j1 = max(0, i - w), min(NY, i + w + 1), max(0, j - w), min(NX, j + w + 1)
        d2 = ((LON[i0:i1, j0:j1] - r.lon) ** 2 + (LAT[i0:i1, j0:j1] - r.lat) ** 2) / k ** 2
        s[r.type][i0:i1, j0:j1] += r.weight * np.exp(-d2)
    return np.stack([np.clip(s[t], 0, 1) for t in TYPES])

def india_mask():
    p = ROOT / "data/raw/india_adm0.geojson"
    if not p.exists(): print("no country outline: run fetch_open_data.py to mask ocean/neighbours"); return np.ones((NY, NX), bool)
    import geopandas as gpd
    from rasterio import features
    from rasterio.transform import from_origin
    g = gpd.read_file(p).to_crs(4326)
    return features.rasterize(((geo, 1) for geo in g.geometry), out_shape=(NY, NX), transform=from_origin(W, N, RES, RES), fill=0).astype(bool)

STOPS = np.array([[0, 250, 220, 90, 0], [.12, 250, 220, 90, 90], [.3, 245, 170, 50, 150], [.5, 230, 100, 40, 190], [.75, 190, 30, 30, 225], [1, 120, 10, 30, 245]])
def to_png(score, mask, path):
    rgba = np.stack([np.interp(score, STOPS[:, 0], STOPS[:, k]) for k in range(1, 5)], -1).astype(np.uint8)
    rgba[..., 3] *= mask.astype(np.uint8)
    y = lambda la: np.log(np.tan(np.pi / 4 + np.radians(la) / 2))       # web-mercator rows so MapLibre aligns it
    lats = np.degrees(2 * np.arctan(np.exp(np.linspace(y(N), y(S), int(NY * 1.15)))) - np.pi / 2)
    Image.fromarray(rgba[np.clip(((N - lats) / RES).astype(int), 0, NY - 1)], "RGBA").save(path, optimize=True)

def load_shelters(c):
    """Shelters/relief camps layer. Falls back to the labelled SAMPLE file if
    no real feed is configured -- see docs/DATA_SOURCES.md for how to point
    this at a live source (e.g. Rakshak ResQ's evacuationZones API, or an
    SDMA/NDMA relief-camp feed) instead of a static CSV."""
    p = ROOT / c.get("shelters", "data/raw/shelters.csv")
    is_sample = not p.exists()
    if is_sample: p = ROOT / "data/seed/shelters_sample.csv"
    df = pd.read_csv(p)
    return df, is_sample

def main():
    out = ROOT / "web/data"; out.mkdir(parents=True, exist_ok=True)
    c = cfg()
    ev = load_events(); sc = compute(ev, c); mask = india_mask(); sc = sc * mask
    np.save(ROOT / "data/processed/scores.npy", sc)
    (sc * 255).astype(np.uint8).tofile(out / "scores.bin")
    json.dump({"bounds": dict(west=W, south=S, east=E, north=N), "res": RES, "nx": NX, "ny": NY, "types": TYPES,
               "generated_at": pd.Timestamp.now("UTC").isoformat()}, open(out / "meta.json", "w"))
    to_png(sc.max(0), mask, out / "heat_all.png")
    for i, t in enumerate(TYPES): to_png(sc[i], mask, out / f"heat_{t}.png")
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]},
              "properties": {"name": r.name, "type": r.type, "year": int(r.year) if pd.notna(r.year) else None, "deaths": int(r.deaths) if pd.notna(r.deaths) else 0}}
             for r in ev[ev["show"] == 1].itertuples()]
    json.dump({"type": "FeatureCollection", "features": feats}, open(out / "events.geojson", "w"))
    shelters, is_sample = load_shelters(c)
    shelters["occupancy_pct"] = (100 * shelters.occupancy / shelters.capacity).round(1)
    json.dump({"is_sample": is_sample, "generated_at": pd.Timestamp.now("UTC").isoformat(),
               "shelters": json.loads(shelters.to_json(orient="records"))}, open(out / "shelters.json", "w"))
    print(f"shelters: {len(shelters)} loaded ({'SAMPLE data' if is_sample else 'from ' + str(c.get('shelters'))})")
    print(f"done: {len(ev)} events used, {len(feats)} shown; red cells (>=0.7): {(sc.max(0) >= .7).sum()}")

if __name__ == "__main__": main()
