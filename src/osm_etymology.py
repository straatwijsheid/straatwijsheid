"""OpenStreetMap etymology evidence: what the mapping community says a street is named after.

Independent of our own name matching, so it is both a strong source of namesakes and a yardstick for how accurate our
classifications are. Three kinds of tag on a street's ways are used:

  name:etymology:wikidata   Wikidata item(s) of the namesake            (best: ';'-separated when several)
  name:etymology            free text ("Named after the painter ...")   (kept as a hint)
  wikidata                  the street's own Wikidata item; its 'named after' (P138) statement gives the namesake

  python src/osm_etymology.py --fetch      Overpass -> data/raw/osm_etymology_ways.json   (Noord-Brabant); records a dated snapshot and writes OSM_CHANGES.md
  python src/osm_etymology.py --refresh    fetch + changes report + build
  python src/osm_etymology.py --build      resolve the Wikidata items -> data/enriched/osm_etymology.json
  python src/osm_etymology.py --report     how often our classification agrees with it, by evidence tier
"""
from __future__ import annotations

import config
import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules.base import ROOT, Context                      # noqa: E402

RAW = config.RAW / "osm_etymology_ways.json"
OUT = config.ENRICHED / "osm_etymology.json"
ENTITY_CACHE = config.CACHE / "wikidata_entities.json"
UA = {"User-Agent": "street-etymology-research/0.1 (open-data research script)"}   # generic: no personal details
OVERPASS = config.OVERPASS_URL
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

QUERY = """[out:json][timeout:300];area["ISO3166-2"="NL-NB"]->.a;
(way(area.a)["highway"]["name"]["name:etymology:wikidata"];
 way(area.a)["highway"]["name"]["name:etymology"];
 way(area.a)["highway"]["name"]["name:etymology:wikipedia"];
 way(area.a)["highway"]["name"]["wikidata"];);
out tags center meta;"""

# --- Wikidata item -> our (category, subcategory) -------------------------------------------------------------------
HUMAN, FICTIONAL_HUMAN = "Q5", "Q15632617"
OCCUPATION = {   # occupation (P106) -> subcategory
    "Q82955": "politician_statesman", "Q372436": "politician_statesman", "Q193391": "politician_statesman", "Q189290": "military",
    "Q47064": "military", "Q1028181": "artist_visual", "Q1281618": "artist_visual", "Q483501": "artist_visual", "Q36180": "writer_poet",
    "Q49757": "writer_poet", "Q482980": "writer_poet", "Q6625963": "writer_poet", "Q36834": "musician_composer", "Q639669": "musician_composer",
    "Q158852": "musician_composer", "Q901": "scientist", "Q169470": "scientist", "Q593644": "scientist", "Q170790": "scientist",
    "Q205375": "scientist", "Q81096": "scientist", "Q39631": "scientist_physician", "Q42973": "architect_or_historian", "Q201788": "architect_or_historian",
    "Q11900058": "explorer", "Q131524": "explorer", "Q33999": "other", "Q250867": "religious", "Q42603": "religious", "Q1234713": "religious",
    "Q43115": "religious", "Q116": "monarch_statesman", "Q2259532": "monarch_statesman", "Q12097": "monarch_statesman", "Q4964182": "writer_poet",
    "Q1930187": "writer_poet", "Q40348": "legal_scholar", "Q185351": "legal_scholar", "Q2095549": "aviation_pioneer", "Q16533": "legal_scholar",
}
PRIORITY = ["monarch_statesman", "religious", "military", "musician_composer", "artist_visual", "writer_poet", "scientist", "scientist_physician",
            "explorer", "architect_or_historian", "legal_scholar", "politician_statesman", "aviation_pioneer", "other"]
PLACE_WORDS = re.compile(r"\b(commune|municipality|town|city|province|region|island|country|river|village|capital|department|county|lake|mountain|hamlet|district|settlement|battle)\b", re.I)
BIO_WORDS = re.compile(r"\b(species|genus|bird|insect|fish|mammal|plant|flower|tree|butterfly|dragonfly|beetle|fungus|shrub|herb|taxon)\b", re.I)


KINDS = {k: v for k, v in json.loads((config.GLOBAL / "osm_entity_kinds.json").read_text()).items() if not k.startswith("_")}


def classify_entity(ent: dict) -> tuple[str | None, str | None]:
    """(category, subcategory) for a Wikidata entity as returned by wbgetentities, or (None, None) if we cannot tell."""
    claims = ent.get("claims", {})
    ids = lambda p: [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get(p, []) if c.get("mainsnak", {}).get("datavalue")]
    p31, p106 = set(ids("P31")), ids("P106")
    desc = (ent.get("descriptions", {}).get("en", {}) or {}).get("value", "")
    if HUMAN in p31:
        subs = {OCCUPATION[o] for o in p106 if o in OCCUPATION}
        for sub in PRIORITY:          # a person with several occupations: the most defining one wins
            if sub in subs:
                return "person", sub
        if re.search(r"\b(king|queen|prince|princess|emperor|duke|count|countess)\b", desc, re.I):
            return "person", "monarch_statesman"
        if re.search(r"\bsaint\b|\bbishop\b|\bpriest\b|\bpope\b", desc, re.I):
            return "person", "religious"
        return "person", "other"
    if FICTIONAL_HUMAN in p31 or re.search(r"\b(fictional|legendary)\b|mytholog|\b(god|goddess|deity|titan)\b", desc, re.I):
        return "person", "mythological_figure" if re.search(r"mytholog|\b(god|goddess|deity|titan)\b", desc, re.I) else "literary_mythical_figure"
    if re.search(r"\bperson from\b|\binhabitant\b", desc, re.I):
        return None, None                      # a demonym (Leuvenaar): says nothing about what the street is named after
    if re.search(r"\btown hall\b|\bcity hall\b|\bcourthouse\b|\bchurch\b|\bbuilding\b", desc, re.I):
        return "place", "local_landmark"
    if re.search(r"\bsaint\b", desc, re.I):
        return "person", "religious"
    if re.search(r"\b(tribe|ethnic group|people of|nation of)\b", desc, re.I):
        return "thing", "archaeology_term"
    if "Q16521" in p31 or BIO_WORDS.search(desc):
        if re.search(r"\b(mammal|bird|fish|insect|rodent|amphibian|reptile|butterfly|dragonfly|beetle|moth|animal)\b", desc, re.I):
            return "thing", "fauna"
        return "thing", "flora" if re.search(r"plant|flower|tree|shrub|herb|fungus|grass", desc, re.I) else "fauna"
    if re.search(r"\b(fruit|vegetable|crop|cereal|grain)\b", desc, re.I):
        return "thing", "flora_food"
    if re.search(r"\b(mineral|gemstone|chalcedony|quartz|variety of)\b", desc, re.I):
        return "thing", "mineral"
    if re.search(r"\b(musical instrument|instrument)\b", desc, re.I):
        return "thing", "instrument"
    if re.search(r"\b(type of (ship|vessel|boat)|sailing ship)\b", desc, re.I):
        return "thing", "vessel_type"
    if re.search(r"\b(field of work|profession|occupation|rank|guild|trade)\b", desc, re.I):
        return "thing", "occupation_guild"
    if re.search(r"\b(fortress|castle|estate|landgoed|manor|abbey|palace|house of|royal house|noble family)\b", desc, re.I):
        return "place", "castle_estate"
    if PLACE_WORDS.search(desc) or re.search(r"\b(stream|brook|canal|continent|border|beek)\b", desc, re.I):
        sub = "river" if re.search(r"\b(river|stream|brook|canal)\b", desc, re.I) else "lake" if re.search(r"\blake\b", desc, re.I) else \
              "country" if re.search(r"\b(country|continent)\b", desc, re.I) else "dutch_town" if re.search(r"Netherlands", desc) else "foreign_town"
        return "place", sub
    return None, None


# --- fetch -----------------------------------------------------------------------------------------------------------
def fetch():
    """Download the etymology-tagged ways, store them as the current snapshot (dated, checksummed, archived: src/snapshots.py) and report what changed
    since the previous snapshot (osm_changes.py). Contributor names are dropped; way version and timestamp are kept."""
    import osm_changes
    import snapshots
    for attempt in range(5):
        try:
            r = requests.post(OVERPASS, data={"data": QUERY}, headers=UA, timeout=400)
            r.raise_for_status()
            els = r.json()["elements"]
            break
        except Exception as e:                                   # noqa: BLE001
            print(f"overpass attempt {attempt + 1} failed: {str(e)[:80]}")
            time.sleep(10 * (attempt + 1))
    else:
        sys.exit("Overpass unreachable; try again later (or another endpoint / VPN)")
    for e in els:
        e.pop("user", None)
        e.pop("uid", None)
    old_sha = snapshots.history("osm_etymology_ways")[-1]["sha256"] if snapshots.history("osm_etymology_ways") else None
    RAW.write_text(json.dumps(els, ensure_ascii=False))
    entry = snapshots.record("osm_etymology_ways", RAW, "Overpass: named highways with etymology/wikidata tags, Noord-Brabant", query=QUERY, rows=len(els))
    print(f"fetched {len(els)} ways -> {config.rel(RAW)} (snapshot {entry['fetched_at']}, sha {entry['sha256'][:10]})")
    prev = snapshots.previous_archive("osm_etymology_ways", entry["sha256"])
    prev_at = next((h["fetched_at"] for h in snapshots.history("osm_etymology_ways") if h["archive"] and prev and config.rel(prev) == h["archive"]), None)
    if prev:
        osm_changes.write_report(osm_changes.diff_ways(snapshots.read_archive(prev), els), entry["fetched_at"], prev_at)
    else:
        print("no earlier snapshot to compare with")
    return els


def _wd_entities(qids: list[str]) -> dict:
    cache = json.loads(ENTITY_CACHE.read_text()) if ENTITY_CACHE.exists() else {}
    need = [q for q in dict.fromkeys(qids) if q not in cache]
    for i in range(0, len(need), 50):
        batch = need[i:i + 50]
        for attempt in range(4):
            try:
                r = requests.get(WIKIDATA_API, params={"action": "wbgetentities", "ids": "|".join(batch), "props": "labels|descriptions|claims",
                                                       "languages": "en|nl", "format": "json"}, headers=UA, timeout=60)
                r.raise_for_status()
                for q, ent in r.json().get("entities", {}).items():
                    claims = ent.get("claims", {})
                    slim = {"labels": ent.get("labels", {}), "descriptions": ent.get("descriptions", {}),
                            "claims": {p: claims[p] for p in ("P31", "P106", "P138") if p in claims}}
                    cache[q] = slim
                break
            except Exception as e:                               # noqa: BLE001
                print("wikidata retry", str(e)[:60])
                time.sleep(5 * (attempt + 1))
        ENTITY_CACHE.parent.mkdir(exist_ok=True)
        ENTITY_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        time.sleep(1.0)
    return cache


def _label(ent):
    return (ent.get("labels", {}).get("en") or ent.get("labels", {}).get("nl") or {}).get("value")


def _desc(ent):
    return (ent.get("descriptions", {}).get("en") or ent.get("descriptions", {}).get("nl") or {}).get("value")


def build():
    ways = json.loads(RAW.read_text())
    import geopandas as gpd
    from shapely.geometry import Point
    b = gpd.read_file(config.RAW / "buurten.geojson")
    gem = b.dissolve(by="gemeente").reset_index()[["gemeente", "geometry"]]
    pts = gpd.GeoDataFrame({"i": range(len(ways))}, geometry=[Point(w["center"]["lon"], w["center"]["lat"]) for w in ways], crs="EPSG:4326")
    joined = gpd.sjoin(pts, gem.to_crs("EPSG:4326"), how="left", predicate="within")
    gem_of = dict(zip(joined["i"], joined["gemeente"]))
    per = collections.defaultdict(lambda: {"ways": [], "etymology_qids": [], "own_qids": [], "text": []})
    for i, w in enumerate(ways):
        t, g = w.get("tags", {}), gem_of.get(i)
        if not isinstance(g, str):
            continue
        rec = per[(g, t["name"])]
        rec["ways"].append(w["id"])
        rec.setdefault("raw_tags", {})
        for k in ("name:etymology:wikidata", "name:etymology", "name:etymology:wikipedia", "wikidata"):
            if t.get(k):
                rec["raw_tags"].setdefault(k, set()).add(t[k])
        rec.setdefault("centers", []).append((round(w["center"]["lat"], 5), round(w["center"]["lon"], 5)))
        for q in re.split(r"[;,]\s*", t.get("name:etymology:wikidata", "")):
            if re.fullmatch(r"Q\d+", q.strip()):
                rec["etymology_qids"].append(q.strip())
        if t.get("wikidata") and re.fullmatch(r"Q\d+", t["wikidata"].split(";")[0]):
            rec["own_qids"].append(t["wikidata"].split(";")[0])
        if t.get("name:etymology"):
            rec["text"].append(t["name:etymology"])
        if t.get("name:etymology:wikipedia"):
            rec["text"].append("wikipedia: " + t["name:etymology:wikipedia"])
    ents = _wd_entities([q for r in per.values() for q in r["etymology_qids"] + r["own_qids"]])
    # the street's own item may state what it is named after (P138)
    p138 = {}
    for r in per.values():
        for q in r["own_qids"]:
            for c in ents.get(q, {}).get("claims", {}).get("P138", []):
                dv = c.get("mainsnak", {}).get("datavalue")
                if dv:
                    p138.setdefault(q, []).append(dv["value"]["id"])
    ents = _wd_entities(list(ents) + [q for v in p138.values() for q in v])
    out = []
    for (g, s), r in sorted(per.items()):
        named = list(dict.fromkeys(r["etymology_qids"]))
        via_p138 = list(dict.fromkeys(q for o in r["own_qids"] for q in p138.get(o, [])))
        qids = named or via_p138
        if not qids and not r["text"]:
            continue
        items = []
        for q in qids:
            e = ents.get(q, {})
            cat, sub = classify_entity(e)
            if q in KINDS:
                cat, sub = KINDS[q][0], KINDS[q][1]
            items.append({"qid": q, "label": _label(e), "description": _desc(e), "category": cat, "subcategory": sub})
        out.append({"gemeente": g, "street": s, "via": "name:etymology:wikidata" if named else "wikidata P138" if via_p138 else "text only",
                    "ways": len(r["ways"]), "way_ids": r["ways"][:12], "tags": {k: sorted(v) for k, v in r.get("raw_tags", {}).items()},
                    "center": r["centers"][0] if r.get("centers") else None, "items": items, "text": r["text"][:2]})
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    c = collections.Counter(o["via"] for o in out)
    print(f"{len(out)} streets with OSM etymology evidence ({dict(c)}) -> {config.rel(OUT)}")
    return out


def load():
    return json.loads(OUT.read_text()) if OUT.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="fetch + report changes + rebuild (everything except applying the rules)")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    if a.fetch or a.refresh:
        fetch()
    if a.build or a.refresh:
        build()
    if a.report:
        from osm_report import report
        report()


if __name__ == "__main__":
    main()
