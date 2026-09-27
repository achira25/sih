"""Download the open, scriptable datasets. Official GSI/NDMA/CWC/BMTPC layers need manual download: see docs/DATA_SOURCES.md."""
from datetime import date
from pathlib import Path
import requests, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data/raw", ROOT / "data/processed"; PROC.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)

def usgs():
    rows = []
    for y0 in range(1950, date.today().year + 1, 10):
        r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query", timeout=180, params=dict(
            format="geojson", starttime=f"{y0}-01-01", endtime=f"{min(y0 + 9, date.today().year)}-12-31", minmagnitude=5,
            minlatitude=6, maxlatitude=37.5, minlongitude=68, maxlongitude=98, limit=20000, orderby="time"))
        r.raise_for_status()
        for f in r.json()["features"]:
            p, (lo, la, _) = f["properties"], f["geometry"]["coordinates"]; m = p["mag"] or 5
            rows.append(dict(name=p["place"], type="earthquake", year=pd.to_datetime(p["time"], unit="ms").year, lon=lo, lat=la,
                             deaths=0, weight=round(0.03 * 10 ** (0.5 * (m - 5)), 4), show=int(m >= 6.5)))
    pd.DataFrame(rows).to_csv(PROC / "usgs_quakes.csv", index=False); print("USGS quakes:", len(rows))

def nasa_glc():
    r = requests.get("https://data.nasa.gov/resource/dd9e-wu2v.json", params={"country_name": "India", "$limit": 50000}, timeout=180)
    r.raise_for_status(); d = pd.DataFrame(r.json())
    out = pd.DataFrame(dict(name=d.event_title, type="landslide", year=pd.to_numeric(d.event_date.str[:4], errors="coerce"),
                            lon=pd.to_numeric(d.longitude), lat=pd.to_numeric(d.latitude),
                            deaths=pd.to_numeric(d.get("fatality_count"), errors="coerce").fillna(0)))
    out["show"] = (out.deaths >= 1).astype(int); out.to_csv(PROC / "nasa_glc.csv", index=False); print("NASA landslides:", len(out))

def boundaries():
    for level, dest in (("ADM0", RAW / "india_adm0.geojson"), ("ADM1", ROOT / "web/data/states.geojson")):
        meta = requests.get(f"https://www.geoboundaries.org/api/current/gbOpen/IND/{level}/", timeout=60).json()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(requests.get(meta["simplifiedGeometryGeoJSON"], timeout=180).content); print("boundary:", level)

for fn in (usgs, nasa_glc, boundaries):
    try: fn()
    except Exception as e: print(f"! {fn.__name__} failed ({e}). Download it manually, see docs/DATA_SOURCES.md")
