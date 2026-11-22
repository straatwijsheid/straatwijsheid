"""Find OpenStreetMap tagging failures that surfaced while using OSM as evidence, and write OSM_FIXES.md so they can be fixed in OSM.

Two kinds are detected (both from data we already fetched, no extra OSM queries):
  A. a way's `wikidata=*` points to the Wikidata item of a *different* street (e.g. ways named Jupiterweg tagged with the item of Jeneverbes)
  B. a way's `name:etymology:wikidata` names a namesake that contradicts the street (our evidence and the buurt disagree)

  python src/osm_fixes.py            rewrite OSM_FIXES.md (candidate Wikidata items are cached in cache/osm_fix_candidates.json)
"""
from __future__ import annotations

import config
import gemeenten
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

WAYS = config.RAW / "osm_etymology_ways.json"
ENTS = config.CACHE / "wikidata_entities.json"
CAND = config.CACHE / "osm_fix_candidates.json"
OUT = config.OUTPUT / "reports" / "OSM_FIXES.md"
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


def missing_etymology(area) -> list:
    """Section C: ways of streets with a confidently known namesake that still lack name:etymology:wikidata (re-read from OSM now)."""
    import geopandas as gpd
    from shapely.geometry import Point
    sug = json.loads((config.GLOBAL / "osm_suggestions.json").read_text())["suggestions"]
    names = "|".join(re.escape(x["street"]) for x in sug)
    q = f'[out:json][timeout:90];area["ISO3166-2"="NL-NB"]->.a;way(area.a)["name"~"^({names})$"]["highway"];out tags center meta;'
    els = None
    for attempt in range(6):
        try:
            r = requests.post(config.OVERPASS_URL, data={"data": q}, headers=UA, timeout=120)
            r.raise_for_status()
            els = r.json()["elements"]
            break
        except Exception as e:                                       # noqa: BLE001
            print("overpass retry", str(e)[:50])
            time.sleep(8)
    lines = ["", "## C. Missing `name:etymology:wikidata` (suggested additions)", "",
             "Streets where we are confident of the namesake but the ways carry no etymology tag (read from OSM when this file was generated).", ""]
    if els is None:
        return lines + ["(Overpass unreachable when generated; re-run `python src/osm_fixes.py`.)", ""]
    pts = gpd.GeoDataFrame({"i": range(len(els))}, geometry=[Point(e["center"]["lon"], e["center"]["lat"]) for e in els], crs="EPSG:4326")
    gem_of = dict(zip(*[gpd.sjoin(pts, area, how="left", predicate="within")[c] for c in ("i", "gemeente_code")]))
    for x in sug:
        code = gemeenten.code_of(x["gemeente"])          # suggestions name their gemeente (or give its code)
        mine = [(i, e) for i, e in enumerate(els) if e["tags"]["name"] == x["street"] and gem_of.get(i) == code]
        todo = [e for _, e in mine if x["qid"] not in e["tags"].get("name:etymology:wikidata", "")]
        done = [e for _, e in mine if x["qid"] in e["tags"].get("name:etymology:wikidata", "")]
        lines.append(f"### {x['street']}, gemeente {x['gemeente']}")
        lines.append(f"- **What is missing:** `name:etymology:wikidata`. **More correct:** `name:etymology:wikidata=[{x['qid']}](https://www.wikidata.org/wiki/{x['qid']})` ({x['label']}). Why: {x['reason']}")
        lines.append(f"- **Already tagged ({len(done)}):** " + (", ".join(f"[{e['id']}](https://www.openstreetmap.org/way/{e['id']})" for e in done) or "none"))
        lines.append(f"- **Still to tag ({len(todo)}):** " + (", ".join(f"[{e['id']}](https://www.openstreetmap.org/way/{e['id']}) ({e['tags'].get('highway')}, ~{round(e['center']['lat'], 4)}, {round(e['center']['lon'], 4)})" for e in sorted(todo, key=lambda e: e['id'])) or "none"))
        lines.append("")
    for x in json.loads((config.GLOBAL / "osm_suggestions.json").read_text()).get("other_ways", []):
        lines.append(f"### {x['street']}, {x['where']}")
        lines.append(f"- **More correct:** `name:etymology:wikidata=[{x['qid']}](https://www.wikidata.org/wiki/{x['qid']})` ({x['label']}). Why: {x['reason']}")
        lines.append("- **Already tagged:** " + ", ".join(f"[{w}](https://www.openstreetmap.org/way/{w})" for w in x["tagged"]))
        lines.append("- **Still to tag:** " + ", ".join(f"[{w}](https://www.openstreetmap.org/way/{w})" for w in x["todo"]))
        lines.append("")
    checks = json.loads((config.GLOBAL / "osm_suggestions.json").read_text()).get("checks", [])
    if checks:
        lines += ["", "## D. Tags to check (possibly wrong, no certain correction)", ""]
        for x in checks:
            lines.append(f"### {x['street']}, gemeente {x['gemeente']} ({x['buurt']}), way [{x['way']}](https://www.openstreetmap.org/way/{x['way']})")
            lines.append(f"- *Tagged:* `{x['tag']}`: {x['tag_item']}.")
            lines.append(f"- *Problem:* {x['problem']}")
            lines.append(f"- *Candidates:* {x['candidates']}")
            lines.append(f"- *Suggestion:* {x['suggestion']}")
            lines.append("")
    return lines


def main():
    ways = json.loads(WAYS.read_text())
    ents = json.loads(ENTS.read_text())
    cache = json.loads(CAND.read_text()) if CAND.exists() else {}
    import geopandas as gpd
    from shapely.geometry import Point
    b = gpd.read_file(config.RAW / "buurten.geojson")
    area = b.dissolve(by="gemeente_code").reset_index()[["gemeente_code", "geometry"]].to_crs("EPSG:4326")
    pts = gpd.GeoDataFrame({"i": range(len(ways))}, geometry=[Point(w["center"]["lon"], w["center"]["lat"]) for w in ways], crs="EPSG:4326")
    joined = gpd.sjoin(pts, area, how="left", predicate="within")
    gem = {ways[i]["id"]: g for i, g in zip(joined["i"], joined["gemeente_code"]) if isinstance(g, str)}
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
            A.append({"way": w["id"], "gemeente_code": gem.get(w["id"]), "gemeente": gemeenten.name_of(gem[w["id"]]) if w["id"] in gem else "?", "name": t["name"], "wikidata": q, "item_label": label, "item_desc": desc,
                      "lat": round(w["center"]["lat"], 5), "lon": round(w["center"]["lon"], 5), "highway": t.get("highway")})
    town = lambda d: (re.search(r"street in (.+?),", d) or [None, ""])[1]
    for a in A:
        a["candidates"] = search_candidates(a["name"], town(a["item_desc"]), cache)
    CAND.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    by_gem = collections.defaultdict(list)
    for a in A:
        by_gem[a["gemeente_code"]].append(a)
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
             f"**{len(A)} ways, {len({(a['gemeente_code'], a['name']) for a in A})} streets, {len(by_gem)} gemeenten.**", "",
             "### Jupiterweg, Oss (gemeente Oss): confirmed in detail",
             "- **Ways:** [6942878](https://www.openstreetmap.org/way/6942878) (residential) and [6942885](https://www.openstreetmap.org/way/6942885) (cycleway), near 51.769, 5.507.",
             "- **What is wrong:** both are named *Jupiterweg* but tagged `wikidata=Q19264983`, which is the item for **Jeneverbes**, a different street in Oss named after juniper (its item says *named after: juniper*). This made the project read 'Jupiterweg is named after juniper'.",
             "- **More correct:** `wikidata=Q19283292` (item *Jupiterweg*, 'street in Oss'), which the third Jupiterweg way [6942639](https://www.openstreetmap.org/way/6942639) already has. Check first that these two ways are really Jupiterweg and not part of Jeneverbes (which has its own ways 6942853 and 6942975).", ""]
    for gcode in sorted(by_gem, key=lambda k: (-len(by_gem[k]), gemeenten.name_of(k) if k else "", k or "")):
        gname = gemeenten.name_of(gcode) if gcode else "?"
        lines.append(f"### Gemeente {gname} ({len({a['name'] for a in by_gem[gcode]})} streets)")
        seen = collections.defaultdict(list)
        for a in by_gem[gcode]:
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
    lines += missing_etymology(area)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {config.rel(OUT)}: {len(A)} ways with a mismatching wikidata tag ({len({a['name'] for a in A})} names)")


if __name__ == "__main__":
    main()
