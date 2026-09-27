"""Rank habitations by risk and assign them to safe candidate sites within capacity."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from common import *

def pick(path, sample):
    p = ROOT / path
    if p.exists(): return pd.read_csv(p), False
    print(f"WARNING: {path} missing, using SAMPLE data {sample}"); return pd.read_csv(ROOT / "data/seed" / sample), True

def main():
    R = cfg()["relocation"]; T = R["thresholds"]
    sc = np.load(ROOT / "data/processed/scores.npy")
    hab, s1 = pick(R["habitations"], "habitations_sample.csv"); sites, s2 = pick(R["candidate_sites"], "candidate_sites_sample.csv")
    for t in range(3): hab[TYPES[t]] = [sc[t][cell(r.lon, r.lat)] for r in hab.itertuples()]
    hab["hazard"] = hab[["flood", "landslide"]].max(axis=1)          # earthquakes: retrofit, not relocate
    hab["risk"] = (100 * (.7 * hab.hazard + .3 * hab.vulnerable_share)).round(1)
    hab["phase"] = np.where(hab.risk >= T["immediate"], "Immediate", np.where(hab.risk >= T["short_term"], "Short-term", np.where(hab.risk >= T["medium_term"], "Medium-term", "Monitor")))
    sites["hazard"] = [max(sc[0][cell(r.lon, r.lat)], sc[1][cell(r.lon, r.lat)]) for r in sites.itertuples()]
    ok = (sites.hazard <= R["max_site_hazard"]) & (sites.slope_deg <= R["max_site_slope_deg"])
    print(f"{ok.sum()} of {len(sites)} candidate sites pass hazard and slope screening")
    sites = sites[ok].reset_index(drop=True)
    sites["suit"] = .4 * (1 - sites.slope_deg.clip(0, 30) / 30) + .3 * sites.water_score + .3 * (1 - sites.road_km.clip(0, 10) / 10)
    sites["left"] = sites.area_ha * R["persons_per_ha"] * sites.suit
    hab["site"], hab["distance_km"] = None, np.nan
    for i in hab[hab.phase != "Monitor"].sort_values("risk", ascending=False).index:
        h = hab.loc[i]
        if len(sites) == 0: break
        d = haversine(h.lon, h.lat, sites.lon.values, sites.lat.values)
        for j in np.argsort(d):
            if sites.loc[j, "left"] >= h.population:
                sites.loc[j, "left"] -= h.population
                hab.loc[i, "site"] = sites.loc[j, "name"]; hab.loc[i, "distance_km"] = round(float(d[j]), 1); break
    (ROOT / "data/processed").mkdir(exist_ok=True); (ROOT / "web/data").mkdir(parents=True, exist_ok=True)
    hab.to_csv(ROOT / "data/processed/relocation_plan.csv", index=False)
    json.dump(json.loads(hab.round(3).to_json(orient="records")), open(ROOT / "web/data/habitations.json", "w"))
    print(hab[["name", "population", "risk", "phase", "site", "distance_km"]].to_string(index=False))
    if s1 or s2: print("NOTE: sample inputs used. Replace with Census/SECC habitations and revenue-department sites.")

if __name__ == "__main__": main()
