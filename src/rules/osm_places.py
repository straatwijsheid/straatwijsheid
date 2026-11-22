"""Streets named after the place they lie in or beside: independent evidence from OpenStreetMap.

A street whose name equals a named OSM feature (hamlet, neighbourhood, suburb, square, stream, lake, park, nature reserve...) within
1 km is read as named after that local place. Policy (decided 2026-11-21): a street named after its own neighbourhood or hamlet is
`place / local name` (`local_landscape_feature`); a same-named stream or lake is `river` / `lake`. The OSM feature is the independent
evidence that the place exists there; it does not prove the street was named for it, so the result is tier 2, not tier 1.

Data: build/raw/osm_places.json (`python src/osm_places.py --fetch`). Never overrides tier 1-2, species/vocabulary things at tier 3-4,
or streets already read as a non-local kind of place (towns, regions: the directional-road rule handles those)."""
from __future__ import annotations

import config
import collections
import json
import re
import unicodedata

from .base import Context, Override, ROOT, core

RULE = "osm_places"
RAW = config.RAW / "osm_places.json"
MAX_KM = 1.0
KIND = {"waterway=river": ("river", "river"), "waterway=stream": ("river", "stream"), "waterway=canal": ("river", "canal"), "waterway=ditch": ("river", "ditch"),
        "natural=water": ("lake", "body of water")}
WORD = {"place=hamlet": "hamlet", "place=neighbourhood": "neighbourhood", "place=suburb": "suburb", "place=village": "village", "place=locality": "locality",
        "place=square": "square", "place=isolated_dwelling": "isolated dwelling", "leisure=park": "park", "leisure=nature_reserve": "nature reserve",
        "historic=fort": "fort", "landuse=forest": "forest", "natural=grassland": "grassland"}


def _norm(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode())


def _locations():
    import geopandas as gpd
    g = gpd.read_file(config.RAW / "streets.geojson")[["gemeente_code", "name", "geometry"]]
    pts = g.geometry.representative_point()
    loc = {}
    for gem, name, p in zip(g["gemeente_code"], g["name"], pts):
        loc.setdefault((gem, name), (p.y, p.x))
    return loc


def propose(ctx: Context, features: list | None = None) -> list[Override]:
    from osm_places import haversine_km
    from tiers import evidence_tier
    features = features if features is not None else json.loads(RAW.read_text())
    idx = collections.defaultdict(list)
    for f in features:
        idx[_norm(f["name"])].append(f)
    loc = _locations()
    out = []
    for row in ctx.final:
        if evidence_tier(row) < 3:
            continue
        cat, sub = row["category"], row.get("subcategory")
        if cat == "thing" and sub is not None:                  # species words, trades, terms: the word has its own meaning
            continue
        if cat == "place" and sub not in (None, "local_landscape_feature", "local_landmark"):
            continue
        p = loc.get((row["gemeente_code"], row["street"]))
        if not p:
            continue
        best = None
        for k in {_norm(core(row["street"])), _norm(row["street"])}:
            for f in idx.get(k, ()):
                d = haversine_km(p[0], p[1], f["lat"], f["lon"])
                if d <= MAX_KM and (best is None or d < best[0]):
                    best = (d, f)
        if not best:
            continue
        d, f = best
        if f["kind"] in ("leisure=park", "place=square") and _norm(f["name"]) == _norm(row["street"]):
            continue        # the park/square is just the street's own plein/park: no independent evidence of what it is named after
        new_cat, new_sub = "place", "local_landscape_feature"
        if f["kind"] in KIND:
            new_sub, word = KIND[f["kind"]][0], KIND[f["kind"]][1]
        else:
            word = WORD.get(f["kind"], f["kind"])
        if cat == "place" and sub == "local_landmark" and new_sub == "local_landscape_feature":
            new_sub = "local_landmark"
        out.append(Override(row["gemeente_code"], row["street"], new_cat, new_sub, f["name"],
                            f"{word} (OpenStreetMap {f['kind']}); the street is named after this local place", 0.55, source="osm_place",
                            source_url=f"https://www.openstreetmap.org/{ {'n': 'node', 'w': 'way', 'r': 'relation'}[f['id'][0]] }/{f['id'][1:]}",
                            notes=f"Same-named OpenStreetMap feature '{f['name']}' ({f['kind']}) {round(d * 1000)} m from the street; read as named after the local place "
                                  f"(policy: streets named after their own neighbourhood/hamlet are place / local name). Independent evidence the place exists here, "
                                  f"not proof of the naming.", rule=RULE))
    return out
