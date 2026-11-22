"""Named OSM geographic features (places, water, heath, woods, nature reserves...) in Noord-Brabant, as independent evidence that a
street name is a place name: a street called Zwartven is a 'lake' reading only if a feature called Zwartven lies nearby.

  python src/osm_places.py --fetch     Overpass -> data/raw/osm_places.json   (name, kind, lat, lon)
"""
from __future__ import annotations

import config
import json
import math
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = config.RAW / "osm_places.json"
UA = {"User-Agent": "street-etymology-research/0.1 (open-data research script)"}
OVERPASS = config.OVERPASS_URL
QUERY = """[out:json][timeout:300];area["ISO3166-2"="NL-NB"]->.a;
(nwr(area.a)["name"]["place"~"^(city|town|village|hamlet|suburb|neighbourhood|locality|isolated_dwelling|farm|square)$"];
 nwr(area.a)["name"]["natural"~"^(water|heath|wood|scrub|wetland|bay|grassland|sand|peninsula|hill)$"];
 nwr(area.a)["name"]["waterway"~"^(river|stream|canal|ditch|brook|drain)$"];
 nwr(area.a)["name"]["leisure"~"^(nature_reserve|park)$"];
 nwr(area.a)["name"]["landuse"~"^(forest|meadow)$"];
 nwr(area.a)["name"]["historic"~"^(castle|manor|ruins|fort)$"];
 nwr(area.a)["name"]["boundary"="protected_area"];);
out tags center;"""


def fetch():
    for attempt in range(8):
        r = requests.post(OVERPASS, data={"data": QUERY}, headers=UA, timeout=400)
        if r.status_code == 200:
            break
        print("overpass", r.status_code, "retrying", file=sys.stderr)
        time.sleep(30 * (attempt + 1))
    else:
        raise SystemExit("overpass failed")
    out = []
    for e in r.json()["elements"]:
        t = e.get("tags", {})
        c = e.get("center") or e
        if "lat" not in c:
            continue
        kind = next((f"{k}={t[k]}" for k in ("place", "natural", "waterway", "leisure", "landuse", "historic", "boundary") if k in t), "?")
        out.append({"name": t["name"], "kind": kind, "lat": round(c["lat"], 5), "lon": round(c["lon"], 5), "id": f'{e["type"][0]}{e["id"]}'})
    RAW.write_text(json.dumps(out, ensure_ascii=False))
    import snapshots
    e = snapshots.record("osm_places", RAW, "Overpass: named places, water, parks, reserves, Noord-Brabant", query=QUERY, rows=len(out))
    print(f"wrote {config.rel(RAW)} ({len(out)} features; snapshot {e['fetched_at']}, sha {e['sha256'][:10]})")


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
