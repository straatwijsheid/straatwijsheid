"""Structured etymology lookup via Wikidata for a list of street names.

For each street, strip the common Dutch street-type suffix to get a "core name",
then search Wikidata for matching entities and pull enough claims (instance-of,
occupation, citizenship, description) to classify the street with a confidence
score. Streets with no confident match are left for the LLM fallback pass.
"""
import difflib
import json
from pathlib import Path
import os
import re
import time
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter, Retry

WD_API = "https://www.wikidata.org/w/api.php"
# Generic client name. Wikimedia asks for a contact in the User-Agent; to provide one,
# set WIKIDATA_CONTACT in the environment (it is never stored in this file).
USER_AGENT = "StreetEtymologyResearch/0.1 (personal research project" + (
    f"; contact: {os.environ['WIKIDATA_CONTACT']}" if os.environ.get("WIKIDATA_CONTACT") else ""
) + ")"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_retry = Retry(
    total=5,
    backoff_factor=2.0,
    status_forcelist=[429, 502, 503, 504],
    respect_retry_after_header=True,
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))

# ordered longest-first so e.g. "plantsoen" isn't shadowed by a shorter suffix
SUFFIXES = sorted(
    [
        "straat", "laan", "weg", "plein", "pad", "hof", "dreef", "singel",
        "kade", "dijk", "gracht", "ring", "baan", "park", "plantsoen",
        "steeg", "erf", "veld", "hoeve", "akker", "tuin", "warande",
        "boulevard", "allee", "brink", "markt", "hage",
    ],
    key=len,
    reverse=True,
)

PERSON_QID = "Q5"
FAMILY_NAME_QID = "Q101352"
GIVEN_NAME_QID = "Q202444"

# tie-breaking for generic "thing" matches: a name can collide with an
# obscure band/film/etc. that happens to share the exact label (e.g. a
# Hungarian band called "Saturnus" outranking the planet). Nudge toward
# types a Dutch street is actually likely to be named after, and away from
# types that are common false-positive traps.
PREFERRED_THING_QIDS = {
    "Q634", "Q3863", "Q6999",       # planet, moon, astronomical object
    "Q11344", "Q7946", "Q498640",   # chemical element, mineral, gemstone variety
    "Q16521", "Q55983715",          # taxon, taxon (organism)
    "Q34379", "Q1051067",           # musical instrument, instrument family
    "Q11446", "Q2235308",           # ship, ship class
}
DEPRIORITIZED_THING_QIDS = {
    "Q215380", "Q5398426", "Q11424",  # musical group, TV series, film
    "Q4167410", "Q4167836",           # Wikimedia disambiguation/category page
    "Q7366", "Q134556",               # single, song
}
PLACE_TYPES = {
    "Q515": "city", "Q6256": "country", "Q23397": "lake", "Q4022": "river",
    "Q8502": "mountain", "Q486972": "human settlement", "Q3957": "town",
    "Q532": "village", "Q107390": "region",
}

OCCUPATION_BUCKETS = {
    "scientist": {"Q901", "Q350979", "Q170790", "Q169470", "Q593644", "Q864503", "Q1622272"},
    "engineer": {"Q81096", "Q13582652"},
    "mathematician": {"Q170790"},
    "physician_medical": {"Q39631", "Q182436"},
    "artist_visual": {"Q1028181", "Q483501"},
    "writer_poet": {"Q36180", "Q49757", "Q6625963"},
    "musician_composer": {"Q639669", "Q36834", "Q855091"},
    "politician_statesman": {"Q82955", "Q372436", "Q30461"},
    "military": {"Q189290", "Q47064"},
    "religious": {"Q42603", "Q1234713"},
    "athlete": {"Q2066131"},
}


@dataclass
class Candidate:
    qid: str
    label: str
    description: str
    instance_of: list = field(default_factory=list)
    occupation: list = field(default_factory=list)
    citizenship: list = field(default_factory=list)


def core_name(street_name: str) -> str:
    low = street_name.lower()
    for suf in SUFFIXES:
        if low.endswith(suf) and len(street_name) > len(suf) + 2:
            return street_name[: -len(suf)].strip("- ")
    return street_name


def wd_search(term: str, language: str = "nl", limit: int = 5) -> list[dict]:
    resp = _session.get(
        WD_API,
        params={
            "action": "wbsearchentities",
            "search": term,
            "language": language,
            "format": "json",
            "limit": limit,
            "type": "item",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("search", [])


def wd_get_claims(qids: list[str]) -> dict[str, dict]:
    if not qids:
        return {}
    resp = _session.get(
        WD_API,
        params={
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "claims|labels|descriptions",
            "languages": "nl|en",
            "format": "json",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("entities", {})


def _claim_qids(entity: dict, prop: str) -> list[str]:
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        try:
            out.append(c["mainsnak"]["datavalue"]["value"]["id"])
        except (KeyError, TypeError):
            continue
    return out


def bucket_occupations(occ_qids: list[str]) -> list[str]:
    buckets = []
    for name, qids in OCCUPATION_BUCKETS.items():
        if set(occ_qids) & qids:
            buckets.append(name)
    return buckets


def label_similarity(core: str, label: str) -> float:
    return difflib.SequenceMatcher(None, core.lower(), (label or "").lower()).ratio()


def lookup_street(street_name: str) -> dict:
    core = core_name(street_name)
    hits = wd_search(core, language="nl")
    lang_penalty = 0.0
    if not hits:
        hits = wd_search(core, language="en")
        lang_penalty = 0.15  # nl-first search failing is a weaker signal

    if not hits:
        return {
            "street": street_name, "core_name": core, "category": "unresolved",
            "confidence": 0.0, "source": "wikidata_no_match",
        }

    qids = [h["id"] for h in hits]
    entities = wd_get_claims(qids)

    # prefer the candidate whose label is closest to the core name, among
    # candidates that are a person, a place type we recognize, or a bare surname
    scored = []
    for h in hits:
        ent = entities.get(h["id"], {})
        instance_of = _claim_qids(ent, "P31")
        is_person = PERSON_QID in instance_of
        is_place = bool(set(instance_of) & set(PLACE_TYPES))
        is_surname = FAMILY_NAME_QID in instance_of
        if not (is_person or is_place or is_surname):
            continue
        sim = label_similarity(core, h.get("label", ""))
        scored.append((sim, h, ent, instance_of, is_person, is_place, is_surname))

    # fallback: a "thing" match (planet, constellation, mineral, instrument,
    # animal/plant species, ...) is never captured by the person/place/surname
    # filter above, so a near-exact label match against ANY entity is worth
    # surfacing too -- this is what turns "Saturnusweg -> unresolved" into
    # "Saturnusweg -> Saturn, sixth planet in the Solar System". Self-referential
    # street-stub Wikidata articles ("Saturnusweg: street in Eindhoven") are
    # excluded since they carry no naming information.
    def thing_score(h):
        sim = label_similarity(core, h.get("label", ""))
        instance_of = _claim_qids(entities.get(h["id"], {}), "P31")
        if set(instance_of) & PREFERRED_THING_QIDS:
            sim += 0.1
        if set(instance_of) & DEPRIORITIZED_THING_QIDS:
            sim -= 0.2
        return sim

    thing_candidates = [
        (thing_score(h), h)
        for h in hits
        if "street in" not in (h.get("description") or "").lower()
        and "straat in" not in (h.get("description") or "").lower()
    ]
    thing_candidates.sort(key=lambda t: t[0], reverse=True)
    best_thing_sim, best_thing_hit = thing_candidates[0] if thing_candidates else (0.0, None)

    if not scored:
        if best_thing_hit is not None and best_thing_sim >= 0.85:
            return {
                "street": street_name, "core_name": core,
                "wikidata_qid": best_thing_hit["id"], "wikidata_label": best_thing_hit.get("label"),
                "wikidata_description": best_thing_hit.get("description"),
                "category": "thing", "subcategory": None,
                "confidence": round(0.65 - lang_penalty, 2),
                "source": "wikidata_thing_match",
            }
        top = hits[0]
        return {
            "street": street_name, "core_name": core,
            "wikidata_qid": top["id"], "wikidata_label": top.get("label"),
            "wikidata_description": top.get("description"),
            "category": "unresolved", "confidence": 0.3,
            "source": "wikidata_weak_match",
        }

    scored.sort(key=lambda t: t[0], reverse=True)
    sim, hit, ent, instance_of, is_person, is_place, is_surname = scored[0]

    # a poor label match against every candidate is more likely a coincidence
    # (e.g. "Pink" the singer) than the street's actual namesake -- but check
    # the broader thing-candidate pool before giving up entirely
    if sim < 0.6:
        if best_thing_hit is not None and best_thing_sim >= 0.85:
            return {
                "street": street_name, "core_name": core,
                "wikidata_qid": best_thing_hit["id"], "wikidata_label": best_thing_hit.get("label"),
                "wikidata_description": best_thing_hit.get("description"),
                "category": "thing", "subcategory": None,
                "confidence": round(0.65 - lang_penalty, 2),
                "source": "wikidata_thing_match",
            }
        return {
            "street": street_name, "core_name": core,
            "wikidata_qid": hit["id"], "wikidata_label": hit.get("label"),
            "wikidata_description": hit.get("description"),
            "category": "unresolved", "confidence": 0.3 - lang_penalty,
            "source": "wikidata_low_similarity",
        }

    occupation = _claim_qids(ent, "P106")

    if is_surname:
        return {
            "street": street_name, "core_name": core,
            "wikidata_qid": hit["id"], "wikidata_label": hit.get("label"),
            "wikidata_description": hit.get("description"),
            "category": "person", "subcategory": "unspecified_individual",
            "confidence": round(0.55 - lang_penalty, 2),
            "source": "wikidata_surname_only",
        }

    if is_person:
        category = "person"
        subcats = bucket_occupations(occupation)
        subcategory = subcats[0] if subcats else "other"
        confidence = round((0.9 if sim > 0.9 else 0.75) - lang_penalty, 2)
    else:
        place_type = next((PLACE_TYPES[q] for q in instance_of if q in PLACE_TYPES), "place")
        category = "place"
        subcategory = place_type
        confidence = round((0.85 if sim > 0.9 else 0.7) - lang_penalty, 2)

    return {
        "street": street_name, "core_name": core,
        "wikidata_qid": hit["id"], "wikidata_label": hit.get("label"),
        "wikidata_description": hit.get("description"),
        "category": category, "subcategory": subcategory,
        "confidence": confidence, "source": "wikidata",
    }


def _safe_lookup(name: str) -> dict:
    try:
        return lookup_street(name)
    except requests.RequestException as e:
        return {
            "street": name, "core_name": core_name(name),
            "category": "error", "confidence": 0.0, "source": str(e),
        }


def lookup_all_resumable(
    street_names: list[str], cache_path, workers: int = 4, delay: float = 0.3
) -> None:
    """Append results to a JSONL cache, skipping names already present, so a
    long run can be killed and restarted without losing progress. Uses a
    small thread pool since each lookup is a couple of blocking HTTP calls;
    the shared requests.Session's Retry adapter backs off on 429s so workers
    self-throttle if we go too fast."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    done = set()
    if cache_path.exists():
        with cache_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    done.add(json.loads(line)["street"])
        print(f"Resuming: {len(done)}/{len(street_names)} already cached")

    todo = [n for n in street_names if n not in done]
    lock = threading.Lock()
    count = 0

    def worker(name: str):
        nonlocal count
        time.sleep(delay)
        result = _safe_lookup(name)
        with lock:
            nonlocal_write(result)

    def nonlocal_write(result):
        nonlocal count
        with cache_path.open("a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        count += 1
        if count % 25 == 0:
            print(f"  ...{count}/{len(todo)} new ({len(done) + count}/{len(street_names)} total)")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(worker, todo))


def missing_street_names(cache_path, gemeenten=None) -> list[str]:
    """Distinct street names in data/raw/streets.geojson that the cache has not looked up yet (the same name in several gemeenten is one lookup)."""
    import geopandas as gpd
    root = Path(__file__).resolve().parent.parent
    g = gpd.read_file(root / "data" / "raw" / "streets.geojson")
    if gemeenten:
        g = g[g["gemeente"].isin(gemeenten)]
    done = set()
    if cache_path.exists():
        with cache_path.open() as f:
            done = {json.loads(line)["street"] for line in f if line.strip()}
    return sorted({n for n in g["name"].dropna() if n not in done})


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Look streets up on Wikidata (resumable). Set WIKIDATA_CONTACT for polite, faster access.")
    ap.add_argument("--missing", action="store_true", help="look up every street in streets.geojson that is not cached yet (the normal mode)")
    ap.add_argument("--gemeente", action="append", help="with --missing: only these gemeenten")
    ap.add_argument("--names", help="a text file with one street name per line, instead of --missing")
    ap.add_argument("--cache", default="all_streets_wikidata.jsonl", help="cache file name in data/enriched/")
    ap.add_argument("--dry-run", action="store_true", help="only report how many names would be looked up")
    a = ap.parse_args()
    out_path = Path(__file__).resolve().parent.parent / "data" / "enriched" / a.cache
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if a.names:
        names = [l.strip() for l in Path(a.names).read_text().splitlines() if l.strip()]
    elif a.missing:
        names = missing_street_names(out_path, a.gemeente)
    else:
        ap.error("give --missing or --names FILE")
    print(f"{len(names)} streets to look up on Wikidata -> {out_path}")
    if not a.dry_run:
        lookup_all_resumable(names, out_path)
        print("Done")
