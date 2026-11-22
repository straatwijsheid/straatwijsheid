"""Reconcile per-street Wikidata classifications with buurt-level naming themes.

A street's individual match is trusted when it's high-confidence AND agrees
with its buurt's dominant theme. When it's low-confidence or conflicts with
a strongly monothematic buurt, the buurt theme wins (this is what fixes
Pinkstraat -> "Pink" the singer, Pluvierlaan -> an unrelated person, etc.).
"""
import config
import json
import re
from pathlib import Path

from tiers import evidence_tier  # src/ is on sys.path when run as a script


CONFIDENT_THRESHOLD = 0.7
STRONG_THEME_THRESHOLD = 0.8

# sources whose entity_label/entity_description reflect an actual identification,
# as opposed to a rejected/weak guess or a generic theme inference
TRUSTED_ENTITY_SOURCES = {
    "wikidata", "wikidata_surname_only",
    "web_search", "osm_etymology", "claude_knowledge",
}

# a title/honorific prefix is a strong, cheap signal that a street is named
# after a person, regardless of what the buurt's dominant theme is (this is
# what fixes cases like "Ingenieur Kalffstraat" getting swept into a
# buurt's "thing" theme just because that subtheme had the bigger share)
PERSON_TITLE_PREFIXES = [
    "Ingenieur", "Professor", "Doctor", "Dr", "Meester", "Mr", "Burgemeester",
    "Generaal", "Kapitein", "Monseigneur", "Pastoor", "Kardinaal", "Sint",
    "Dominee", "Rector", "Kanunnik", "Deken", "Baron", "Graaf", "Hertog",
    "Prins", "Prinses", "Koning", "Koningin", "Vicaris", "Pater", "President",
    "Minister", "Veldmaarschalk", "Kolonel", "Majoor", "Admiraal",
    "Dokter", "Wethouder", "Prelaat", "Heer",
]
_TITLE_RE = re.compile(
    r"^(" + "|".join(re.escape(p) for p in PERSON_TITLE_PREFIXES) + r")\s+\S", re.IGNORECASE
)


def has_person_title(street_name: str) -> bool:
    return bool(_TITLE_RE.match(street_name))


# Wikidata descriptions / labels of things that are NOT the person a title-prefixed
# street honors: the street itself, a stop, a district, a windmill...
_NOT_A_PERSON_DESC = re.compile(
    r"street|tram stop|district|windmill|village|town|hamlet|city|sculpture|barracks|"
    r"farmhouse|monument|flat\b|park\b|square|road|building|noble title|municipality",
    re.IGNORECASE,
)
_STREET_WORD_LABEL = re.compile(
    r"(straat|laan|plein|weg|pad|hof|dreef|plantsoen|kazerne|flat|monument|park)\b", re.IGNORECASE
)


def plausible_person_entity(label, description) -> bool:
    """For title-prefixed streets ("Generaal Anthinglaan") Wikidata usually only finds the
    street itself, a tram stop, a windmill... Keep a matched entity only if it looks like
    an actual person."""
    if not label or not description:
        return False
    return not (_NOT_A_PERSON_DESC.search(description) or _STREET_WORD_LABEL.search(label))


def load_json(path: Path):
    return json.loads(path.read_text())


def reconcile(wikidata_results: list[dict], context: dict, themes_by_buurt: dict) -> list[dict]:
    """context maps street name -> [{"gemeente", "buurt"}, ...] (a name can exist in
    several gemeenten); themes_by_buurt is keyed by (gemeente, buurt). Wikidata results
    are per street *name*, so the same result fans out to each gemeente that has it."""
    final = []
    unplaced = [{"gemeente": None, "buurt": None}]
    pairs = [(r, place) for r in wikidata_results for place in context.get(r["street"], unplaced)]
    for r, place in pairs:
        street = r["street"]
        buurt = place["buurt"]
        theme = themes_by_buurt.get((place["gemeente"], buurt))

        wd_conf = r.get("confidence", 0.0)
        wd_category = r.get("category")

        row = {
            "street": street,
            "gemeente": place["gemeente"],
            "buurt": buurt,
            "category": wd_category,
            "subcategory": r.get("subcategory"),
            "entity_label": r.get("wikidata_label"),
            "entity_description": r.get("wikidata_description"),
            "confidence": wd_conf,
            "source": r.get("source"),
            "buurt_theme": theme.get("theme") if theme else None,
            "notes": "",
        }

        def theme_supports_person(theme) -> bool:
            if not theme:
                return False
            if theme.get("category") == "person":
                return True
            if theme.get("category") == "mixed":
                share = sum(
                    s.get("share", 0) for s in theme.get("subthemes", []) if s["category"] == "person"
                )
                return share >= 0.4
            return False

        if has_person_title(street) and wd_category != "person":
            subcategory = "other"
            if theme:
                if theme.get("category") == "person":
                    subcategory = theme.get("subcategory") or "other"
                elif theme.get("category") == "mixed":
                    person_subs = [s for s in theme.get("subthemes", []) if s["category"] == "person"]
                    if person_subs:
                        subcategory = person_subs[0].get("subcategory") or "other"
            row["category"] = "person"
            row["subcategory"] = subcategory
            row["confidence"] = 0.65
            row["source"] = "title_heuristic"
            title = street.split()[0]
            row["notes"] = (
                f"street name starts with the person-title '{title}', overriding the "
                f"{wd_category or 'unresolved'} guess from Wikidata/buurt theme"
            )
            if not plausible_person_entity(row["entity_label"], row["entity_description"]):
                row["entity_label"] = None
                row["entity_description"] = None
            final.append(row)
            continue

        if theme is None:
            final.append(row)
            continue

        theme_conf = theme.get("confidence", 0.0)
        theme_category = theme.get("category")

        agrees = (
            wd_category == theme_category
            or (theme_category == "mixed" and wd_category in {
                s["category"] for s in theme.get("subthemes", [])
            })
        )

        if wd_conf >= CONFIDENT_THRESHOLD and (agrees or theme_category is None):
            row["notes"] = "individual match kept (confident + consistent with buurt)"
        elif theme_conf >= STRONG_THEME_THRESHOLD and not agrees:
            # buurt theme overrides a weak or conflicting individual match
            if theme_category != "mixed":
                row["category"] = theme_category
                row["subcategory"] = theme.get("subcategory")
                row["confidence"] = round(theme_conf * 0.9, 2)
            else:
                subthemes = theme.get("subthemes", [])
                if subthemes:
                    best_sub = max(subthemes, key=lambda s: s.get("share", 0))
                    row["category"] = best_sub["category"]
                    row["subcategory"] = best_sub.get("subcategory")
                    row["confidence"] = round(theme_conf * best_sub.get("share", 0.5) * 0.9, 2)
            row["source"] = "buurt_theme_override"
            row["notes"] = (
                f"overridden: individual match ({wd_category}, conf={wd_conf}) "
                f"conflicted with strong buurt theme '{theme['theme']}'"
            )
        elif wd_conf < CONFIDENT_THRESHOLD and theme_conf >= 0.6:
            if theme_category != "mixed":
                row["category"] = theme_category
                row["subcategory"] = theme.get("subcategory")
                row["confidence"] = round(theme_conf * 0.8, 2)
            else:
                # pick the largest sub-theme as the best guess; discount further
                # since within-buurt we can't tell which sub-cluster a given
                # street belongs to without more signal (e.g. its actual name)
                subthemes = theme.get("subthemes", [])
                if subthemes:
                    best_sub = max(subthemes, key=lambda s: s.get("share", 0))
                    row["category"] = best_sub["category"]
                    row["subcategory"] = best_sub.get("subcategory")
                    row["confidence"] = round(theme_conf * best_sub.get("share", 0.5) * 0.8, 2)
            row["source"] = "buurt_theme_fallback"
            row["notes"] = f"no confident individual match; inferred from buurt theme '{theme['theme']}'"
        else:
            row["notes"] = "kept as-is; theme present but not strong enough to override or assist"
            if row["source"] == "wikidata_surname_only" and not has_person_title(street) \
                    and not theme_supports_person(theme):
                # a "family name" Wikidata hit is weak on its own: Dutch surnames are
                # often derived from ordinary words (Wal, Vloet, Bogert, Molendijk...),
                # so a common-word street can false-positive as "person" with no real
                # signal, and here nothing else (title, strong buurt theme) corroborates it
                row["category"] = "unresolved"
                row["subcategory"] = None
                row["confidence"] = 0.25
                row["source"] = "surname_unsupported"
                row["notes"] = (
                    f"Wikidata matched '{row['entity_label']}' as a family name, but nothing "
                    f"corroborates a person-naming pattern here -- likely a plain Dutch word that "
                    f"happens to coincide with a rare surname, not evidence of the real origin"
                )
                row["entity_label"] = None
                row["entity_description"] = None

        # entity_label/entity_description only mean something when they come
        # from a source that actually identifies a specific named thing --
        # every other path here (buurt theme override/fallback, or a
        # rejected/weak Wikidata guess kept as unresolved) leaves whatever
        # raw wikidata_label was on the original hit sitting in the row,
        # which silently looks like a real identification downstream (e.g.
        # "Acaciastraat" showing entity 'Acacia' when that's just the
        # rejected guess, not a confirmed match). Clear it here so entity
        # presence reliably means "we know what this is specifically named after".
        # a bare "family name" Wikidata item says the surname exists, not whom the street
        # honors, so it never counts as an identification (the person category still stands)
        if row["source"] not in TRUSTED_ENTITY_SOURCES or row["source"] == "wikidata_surname_only":
            row["entity_label"] = None
            row["entity_description"] = None

        final.append(row)
    return final


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def apply_manual_overrides(final: list[dict], exclude=(), upto: str | None = None) -> list[dict]:
    """The override layers (src/overrides.py) applied in order, later layers winning: hand classifications first, reviewed corrections last.
    `upto` / `exclude` let a rule see the state below its own layer when it computes its proposals."""
    import overrides
    layers = overrides.merged(exclude=exclude, upto=upto)
    for row in final:
        o = layers.get((row["gemeente"], row["street"]))
        if not o:
            continue
        row.update({
            "category": o["category"], "subcategory": o.get("subcategory"),
            "entity_label": o.get("entity_label"), "entity_description": o.get("entity_description"),
            "confidence": o["confidence"], "source": o["source"],
            "source_url": o.get("source_url"),
            "notes": o.get("notes") or f"manually researched ({o['source']})",
        })
    return final


def compute_final(exclude=(), upto: str | None = None) -> list[dict]:
    """Classify every street in data/raw/streets.geojson from the Wikidata cache, the buurt themes and the override layers (in memory)."""
    import geopandas as gpd

    wikidata_results = load_jsonl(config.ENRICHED / "all_streets_wikidata.jsonl")
    gdf = gpd.read_file(config.RAW / "streets.geojson")
    context = {}
    for _, row in gdf.iterrows():
        context.setdefault(row["name"], []).append({"gemeente": row["gemeente"], "buurt": row["buurt"]})
    # the cache keeps lookups for gemeenten that were dropped from the map: don't emit unplaced rows for them
    wikidata_results = [r for r in wikidata_results if r["street"] in context]
    themes = load_json(config.ENRICHED / "buurt_themes_full.json")["buurten"]
    themes_by_buurt = {(t["gemeente"], t["buurt"]): t for t in themes}

    final = apply_manual_overrides(reconcile(wikidata_results, context, themes_by_buurt), exclude=exclude, upto=upto)
    ways = {}
    if "way_class" in gdf:
        ways = {(g, n): (h, w) for g, n, h, w in zip(gdf["gemeente"], gdf["name"], gdf["highway"], gdf["way_class"])}
    for row in final:
        row["evidence_tier"] = evidence_tier(row)
        h, w = ways.get((row["gemeente"], row["street"]), (None, None))
        row["highway"] = h if isinstance(h, str) else None          # OSM highway type of the street
        row["way_class"] = w if isinstance(w, str) else "street"     # street | path | planned
    return final


def main():
    """Classify every street and write data/enriched/streets_final.json."""
    from collections import Counter

    final = compute_final()
    out_path = config.ENRICHED / "streets_final.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path} ({len(final)} streets)")
    print("Category breakdown:", dict(Counter(row["category"] for row in final)))


if __name__ == "__main__":
    main()
