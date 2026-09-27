"""Hold out events from year CUTOFF onward, build hazard without them, and check how many fall in red/orange cells."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *
from build_hazard import compute, load_events
cut = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
ev = load_events(); ev = ev[ev.year.notna()]
sc = compute(ev[ev.year < cut]); test = ev[ev.year >= cut]
hits = np.array([sc[TYPES.index(r.type)][cell(r.lon, r.lat)] for r in test.itertuples() if r.type in TYPES])
if len(hits) == 0: sys.exit("no held-out events")
print(f"held-out events: {len(hits)}")
for t in (.5, .7): print(f"  in cells with score >= {t}: {(hits >= t).mean():.0%}   (map area with score >= {t}: {(sc.max(0) >= t).mean():.0%})")
print("Sanity check only: the seed regions were drawn with knowledge of major events.")
