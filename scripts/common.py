import numpy as np, yaml, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
def cfg(): return yaml.safe_load(open(ROOT / "config.yaml"))
_c = cfg()
W, S, E, N = (_c["bounds"][k] for k in ("west", "south", "east", "north"))
RES = _c["resolution_deg"]
NX, NY = int(round((E - W) / RES)), int(round((N - S) / RES))
TYPES = ["flood", "landslide", "earthquake"]
def lon_lat_grid():
    return np.meshgrid(W + (np.arange(NX) + .5) * RES, N - (np.arange(NY) + .5) * RES)
def cell(lon, lat):
    return min(max(int((N - lat) / RES), 0), NY - 1), min(max(int((lon - W) / RES), 0), NX - 1)
def haversine(lo1, la1, lo2, la2):
    p = np.pi / 180
    a = np.sin((la2 - la1) * p / 2) ** 2 + np.cos(la1 * p) * np.cos(la2 * p) * np.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))
