"""Find OpenStreetMap tagging failures that surfaced while using OSM as evidence, and write OSM_FIXES.md so they can be fixed in OSM.

Two kinds are detected (both from data we already fetched, no extra OSM queries):
  A. a way's `wikidata=*` points to the Wikidata item of a *different* street (e.g. ways named Jupiterweg tagged with the item of Jeneverbes)
  B. a way's `name:etymology:wikidata` names a namesake that contradicts the street (our evidence and the buurt disagree)

  python src/osm_fixes.py            rewrite OSM_FIXES.md (candidate Wikidata items are cached in cache/osm_fix_candidates.json)
"""
from __future__ import annotations

import collections
import difflib
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules.base import ROOT                                  # noqa: E402

WAYS = ROOT / "data" / "raw" / "osm_etymology_ways.json"
ENTS = ROOT / "cache" / "wikidata_entities.json"
CAND = ROOT / "cache" / "osm_fix_candidates.json"
OUT = ROOT / "OSM_FIXES.md"
UA = {"User-Agent": "street-etymology-research/0.1 (open-data research script)"}
STREET_CLASSES = {"Q79007", "Q34442", "Q83620", "Q787113", "Q1068842"}
ABBR = [(r"\bdoctor\b", "dr"), (r"\bprofessor\b", "prof"), (r"\bmonseigneur\b", "mgr"), (r"\bburgemeester\b", "burg"), (r"\bdominee\b", "ds"),
        (r"\bmeester\b", "mr"), (r"\bjonkheer\b", "jhr"), (r"\bsint\b", "st"), (r"\bsaint\b", "st"), (r"\bpastoor\b", "past"), (r"\bkapelaan\b", "kap")]


def norm(s: str) -> str:
    s = (s or "").lower().replace("ij", "y").replace("ï", "i").replace("ë", "e")
    for pat, rep in ABBR:
        s = re.sub(pat, rep, s)
    return re.sub(r"[^a-z0-9]", "", s)


def same_street(name: str, label: str) -> bool:
    a, b = norm(name), norm(label)
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8 or a in b or b in a


def search_candidates(name: str, town: str, cache: dict) -> list:
    key = f"{name}|{town}"
    if key in cache:
        return cache[key]
    out, ok = [], False
    try:
        r = requests.get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": name, "language": "nl", "limit": 8, "format": "json"},
                         headers=UA, timeout=30)
        r.raise_for_status()
        for x in r.json().get("search", []):
            d = x.get("description") or ""
            if "street" in d or "straat" in d:
                out.append({"qid": x["id"], "label": x.get("label"), "description": d, "same_town": bool(town and town.lower() in d.lower())})
        ok = True
    except Exception as e:                                           # noqa: BLE001
        print("search failed (not cached)", name, str(e)[:60])
    if ok:
        cache[key] = out                                             # failures (rate limits) are retried next run, not remembered
    time.sleep(1.6)
    return out if ok else None            # None = lookup failed (rate limit), distinct from [] = searched, nothing found


def main():
    ways = json.loads(WAYS.read_text())
    ents = json.loads(ENTS.read_text())
    cache = json.loads(CAND.read_text()) if CAND.exists() else {}
    import geopandas as gpd
    from shapely.geometry import Point
    b = gpd.read_file(ROOT / "data" / "raw" / "buurten.geojson")
    area = b.dissolve(by="gemeente").reset_index()[["gemeente", "geometry"]].to_crs("EPSG:4326")
    pts = gpd.GeoDataFrame({"i": range(len(ways))}, geometry=[Point(w["center"]["lon"], w["center"]["lat"]) for w in ways], crs="EPSG:4326")
    joined = gpd.sjoin(pts, area, how="left", predicate="within")
    gem = {ways[i]["id"]: g for i, g in zip(joined["i"], joined["gemeente"]) if isinstance(g, str)}
    A = []
    for w in ways:
        t = w["tags"]
        q = (t.get("wikidata") or "").split(";")[0]
        e = ents.get(q)
        if not e:
            continue
        p31 = {c["mainsnak"]["datavalue"]["value"]["id"] for c in e.get("claims", {}).get("P31", []) if c.get("mainsnak", {}).get("datavalue")}
        label = (e.get("labels", {}).get("nl") or e.get("labels", {}).get("en") or {}).get("value")
        desc = (e.get("descriptions", {}).get("en") or {}).get("value", "")
        if (p31 & STREET_CLASSES or "street in" in desc) and label and not same_street(t["name"], label):
            A.append({"way": w["id"], "gemeente": gem.get(w["id"], "?"), "name": t["name"], "wikidata": q, "item_label": label, "item_desc": desc,
                      "lat": round(w["center"]["lat"], 5), "lon": round(w["center"]["lon"], 5), "highway": t.get("highway")})
    town = lambda d: (re.search(r"street in (.+?),", d) or [None, ""])[1]
    for a in A:
        a["candidates"] = search_candidates(a["name"], town(a["item_desc"]), cache)
    CAND.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    by_gem = collections.defaultdict(list)
    for a in A:
        by_gem[a["gemeente"]].append(a)
    lines = ["# OSM fixes to make", "",
             "Tagging failures found while using OpenStreetMap as evidence for the street-name project (generated by `python src/osm_fixes.py`).",
             "Every entry gives: the street, its gemeente, the way(s) to edit, **what is wrong**, and **what would be more correct**. Verify on the map before editing.", "",
             "## A. `name:etymology:wikidata` that contradicts the street", "",
             "### Romeinsestraat, Budel (gemeente Cranendonck): one way still to fix",
             "- **Ways:** [1458273757](https://www.openstreetmap.org/way/1458273757) (near 51.279, 5.575) still needs the edit; [306751646](https://www.openstreetmap.org/way/306751646) was already corrected to `Q220` on 2026-11-21.",
             "- **What is wrong:** way 1458273757 has `name:etymology:wikidata=Q47162`, which says the street is named after **Romain Rolland** (French writer). (An earlier version of this list wrongly suggested the Romans; the street is named after **Rome**.)",
             "- **More correct:** `name:etymology:wikidata=Q220` (**Rome**), as on the other way. The Budel buurt names roads after European places and rivers (Duitsestraat, Brusselsestraat, Luxemburgsestraat, Utrechtsestraat, Seinestraat, Moezelstraat, Rijnstraat).", "",
             "## B. `wikidata` tag points to a different street's Wikidata item", "",
             "These ways carry the Wikidata item of *another* street (the item's label does not match the way's name; Dr./Doctor-style abbreviations and spelling variants were filtered out).",
             "The `wikidata` tag should be the item of the way's own street. A wrong item can also give the street a wrong namesake via its 'named after' statement.", "",
             f"**{len(A)} ways, {len({(a['gemeente'], a['name']) for a in A})} streets, {len(by_gem)} gemeenten.**", "",
             "### Jupiterweg, Oss (gemeente Oss): confirmed in detail",
             "- **Ways:** [6942878](https://www.openstreetmap.org/way/6942878) (residential) and [6942885](https://www.openstreetmap.org/way/6942885) (cycleway), near 51.769, 5.507.",
             "- **What is wrong:** both are named *Jupiterweg* but tagged `wikidata=Q19264983`, which is the item for **Jeneverbes**, a different street in Oss named after juniper (its item says *named after: juniper*). This made the project read 'Jupiterweg is named after juniper'.",
             "- **More correct:** `wikidata=Q19283292` (item *Jupiterweg*, 'street in Oss'), which the third Jupiterweg way [6942639](https://www.openstreetmap.org/way/6942639) already has. Check first that these two ways are really Jupiterweg and not part of Jeneverbes (which has its own ways 6942853 and 6942975).", ""]
    for gname in sorted(by_gem, key=lambda k: (-len(by_gem[k]), k)):
        lines.append(f"### Gemeente {gname} ({len({a['name'] for a in by_gem[gname]})} streets)")
        seen = collections.defaultdict(list)
        for a in by_gem[gname]:
            seen[(a["name"], a["wikidata"], a["item_label"])].append(a)
        for (name, q, lab), L in sorted(seen.items()):
            ways_txt = ", ".join(f"[{a['way']}](https://www.openstreetmap.org/way/{a['way']})" for a in L)
            cands = [c for c in (L[0]["candidates"] or []) if c["qid"] != q][:3]
            if L[0]["candidates"] is None:
                fix = "candidate lookup was rate-limited; re-run `python src/osm_fixes.py` to fill in the correct item"
            elif cands:
                fix = "; ".join(f"[{c['qid']}](https://www.wikidata.org/wiki/{c['qid']}) \"{c['label']}\" ({c['description'][:55]})" + (" **same town**" if c["same_town"] else "") for c in cands)
                fix = f"set `wikidata` to the item for this street: {fix}"
            else:
                fix = "no street item found by name; if none exists, remove the `wikidata` tag (or create the Wikidata item)"
            lines.append(f"- **{name}**, gemeente {gname} (~{L[0]['lat']}, {L[0]['lon']}); way(s) {ways_txt}.\n  - *Wrong:* tagged `wikidata={q}`, the item for \"{lab}\" ({L[0]['item_desc'][:55]}), a different street.\n  - *More correct:* {fix}.")
        lines.append("")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(A)} ways with a mismatching wikidata tag ({len({a['name'] for a in A})} names)")


if __name__ == "__main__":
    main()
