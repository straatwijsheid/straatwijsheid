"""The data dictionary, generated: every field of the data files and the meaning of the values, written to docs/data-dictionary.md.

The meanings live here, next to the code that produces the data, and everything that code already knows (the evidence tiers, the subcategory groups, the
CSV columns, the override layers and the rules, the colours) is read from it, so the document cannot drift from the code. `verify` checks the other
direction: it reads real records and reports any field, source or subcategory that is not documented here.

  python src/dictionary.py              print the dictionary
  python src/dictionary.py --write      write docs/data-dictionary.md
  python src/dictionary.py --check      fail if docs/data-dictionary.md is out of date (also run by the tests)
  python src/dictionary.py --verify     check the current build (build/enriched, build/output) and the knowledge checkout against the dictionary
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import config

DOC = config.ROOT / "docs" / "data-dictionary.md"

# --- the files and their fields: name -> (type, meaning) ---------------------------------------------------------------------------------------------

STREET_FIELDS = {
    "street": ("text", "The street's name as in OpenStreetMap (one row per distinct name per gemeente)."),
    "gemeente": ("text", "The gemeente's display name. Not unique: use `gemeente_code`."),
    "gemeente_code": ("text", "The CBS gemeentecode (`GM0772`): the key of a gemeente everywhere. A street is identified by `(gemeente_code, street)`."),
    "buurt": ("text", "The CBS buurt (neighbourhood) containing the middle (centroid) of the street's geometry."),
    "wijk": ("text", "The CBS wijk (district) of the buurt."),
    "category": ("enum", "What kind of thing the street is named after: see [category](#category)."),
    "subcategory": ("enum or null", "The finer kind: see [subcategory](#subcategory). Null when only the category is known."),
    "entity_label": ("text or null", "The specific namesake (\"Frits Philips\", \"Saint John\"), only where a source identifies one. Null for kind-only and unidentified streets."),
    "entity_description": ("text or null", "A short description of the namesake: a Wikidata description, or ours. For species, `<Latin name>; Dutch name '<stem>'`. A description saying \"only the kind of namesake is asserted\" marks a kind-only label."),
    "confidence": ("number 0 to 1", "The source's own score for this classification. Not a probability and not comparable across sources; the map words it as high (0.75 or more), medium (0.5 or more) or low. See [confidence](#confidence)."),
    "source": ("enum", "How the classification was reached: see [source](#source)."),
    "source_url": ("URL or null", "Where the evidence is, usually the namesake's Wikidata page. Present only for some rows."),
    "buurt_theme": ("text or null", "The naming theme of the street's buurt (\"Golden Age painters\"), whatever this street's own label."),
    "notes": ("text", "How the result was reached, in words (for example why a Wikidata match was overridden). Free text for readers, not for parsing."),
    "evidence_tier": ("integer 1 to 5", "How well-founded the label is, derived from the other fields by `src/tiers.py`: see [evidence tier](#evidence-tier)."),
    "evidence_tier_name": ("text", "The tier's name (CSV only)."),
    "highway": ("text", "The most street-like OpenStreetMap `highway` type among the street's ways (`residential`, `service`, `footway`...)."),
    "way_class": ("enum", "`street`, `path` or `planned`: see [way class](#way-class)."),
}

THEME_FIELDS = {
    "gemeente": STREET_FIELDS["gemeente"],
    "gemeente_code": STREET_FIELDS["gemeente_code"],
    "buurt": STREET_FIELDS["buurt"],
    "wijk": STREET_FIELDS["wijk"],
    "theme": ("text", "The theme in words (\"flowers, trees and plants\")."),
    "category": ("enum", "The theme's category: person, place or thing, `mixed` (several kinds; see `subthemes`) or `unclear`."),
    "subcategory": ("enum or null", "The theme's subcategory when it is a single kind."),
    "subthemes": ("list or absent", "For a `mixed` theme: `[{category, subcategory, share}]`, the shares of its parts (sum about 1)."),
    "confidence": ("number 0 to 1", "How strongly the buurt follows the theme. The reconcile step trusts a theme at 0.8 or more to override a weak match, and at 0.6 or more to fill in a missing one."),
    "source": ("enum", "`claude_reasoning`: written by hand from reading the buurt's street list (the first 394 themes, never regenerated); `derived_from_street_classification`: derived by `src/themes.py` from the buurt's classified streets."),
    "example_streets": ("list of text", "Streets in the buurt that show the theme."),
}

LAYER_FIELDS = {
    "gemeente": STREET_FIELDS["gemeente"],
    "street": STREET_FIELDS["street"],
    "category": STREET_FIELDS["category"],
    "subcategory": STREET_FIELDS["subcategory"],
    "entity_label": STREET_FIELDS["entity_label"],
    "entity_description": STREET_FIELDS["entity_description"],
    "confidence": STREET_FIELDS["confidence"],
    "source": ("enum", "As in `streets_final.json`; `claude_knowledge` is the default for rule and hand-made entries."),
    "source_url": STREET_FIELDS["source_url"],
    "notes": STREET_FIELDS["notes"],
}

CORRECTION_FIELDS = {
    "gemeente": STREET_FIELDS["gemeente"],
    "street": STREET_FIELDS["street"],
    "category": STREET_FIELDS["category"],
    "subcategory": STREET_FIELDS["subcategory"],
    "entity_label": STREET_FIELDS["entity_label"],
    "entity_description": STREET_FIELDS["entity_description"],
    "confidence": STREET_FIELDS["confidence"],
    "reason": ("text", "Why. Required: a correction without a reason is not accepted."),
    "from_osm": ("true or absent", "Take the namesake (label, description, Wikidata link) from the street's OpenStreetMap etymology record, keeping the kind given here; the source becomes `osm_etymology` (tier 1)."),
}

RAW_FIELDS = {
    "name": ("text", "The street name (`streets_gm####.geojson`) or buurt name (`buurten_gm####.geojson`)."),
    "buurt": STREET_FIELDS["buurt"],
    "wijk": STREET_FIELDS["wijk"],
    "gemeente": STREET_FIELDS["gemeente"],
    "gemeente_code": STREET_FIELDS["gemeente_code"],
    "highway": STREET_FIELDS["highway"],
    "highway_all": ("text", "Every `highway` type seen among the street's ways, separated by `;`."),
    "way_class": STREET_FIELDS["way_class"],
    "origin": ("text", "How the street entered the data: `drive_network` (the first fetch) or `supplement` (streets the first fetch missed, added later)."),
    "geometry": ("geometry", "The street's merged line geometry, or the buurt's polygon (WGS84)."),
}

CSV_STREETS = ["gemeente", "gemeente_code", "street", "wijk", "buurt", "category", "subcategory", "entity_label", "entity_description", "evidence_tier",
               "evidence_tier_name", "highway", "way_class", "confidence", "source", "source_url", "buurt_theme", "notes"]
CSV_THEMES = ["gemeente", "gemeente_code", "buurt", "wijk", "theme", "category", "subcategory", "confidence", "source", "example_streets"]

FILES = [
    ("`enriched/streets_final.json`", "The classification of every street: a JSON list, one record per `(gemeente_code, street)`, written by `src/reconcile.py` (Wikidata + themes + override layers).", STREET_FIELDS,
     {"wijk", "evidence_tier_name"}),
    ("`output/streets_classified.csv`", "The same, flat, for spreadsheets (`src/export_csv.py`); adds `wijk` and `evidence_tier_name`.", STREET_FIELDS, set()),
    ("`enriched/buurt_themes_full.json`", "`{\"buurten\": [...]}`: the naming theme of each buurt (`src/themes.py`, plus the hand-written first themes).", THEME_FIELDS, set()),
    ("`output/buurt_themes.csv`", "The themes, flat (`src/export_csv.py`); `subthemes` is not exported.", THEME_FIELDS, {"subthemes"}),
    ("override layers: `knowledge/gemeenten/<province>/<gemeente>/overrides/<layer>.json`",
     "`{\"layer\": name, \"overrides\": [entry, ...]}`, one file per layer per gemeente. A later layer wins on the same street. The gemeente is identified by the folder, so entries do not store `gemeente_code`.",
     LAYER_FIELDS, set()),
    ("`knowledge/gemeenten/<province>/<gemeente>/corrections.json`", "`{\"corrections\": [entry, ...]}`: reviewed street-level decisions; applied as the last override layer.", CORRECTION_FIELDS, set()),
    ("`raw/streets_gm####.geojson`, `raw/buurten_gm####.geojson` (and the combined `streets.geojson`, `buurten.geojson`)", "What acquire fetched: one feature per street name, or per buurt. Streets only carry `highway`, `highway_all`, `way_class` and `origin`; buurten only `name`, `wijk`, `gemeente`, `gemeente_code`.",
     RAW_FIELDS, set()),
]

# --- the values ---------------------------------------------------------------------------------------------------------------------------------

CATEGORIES = {
    "person": "Named after a person, or a kind of person (a mayor, a saint, a composer).",
    "place": "Named after a place: a town, region, castle, river, or a local field, road or landmark.",
    "thing": "Named after a thing or concept: a plant, an animal, a trade, an instrument, an idea.",
    "mixed": "(buurt themes) several kinds; see `subthemes`.",
    "unclear": "The kind could not be decided.",
    "unresolved": "Nothing known: no match and no theme to read it by.",
}

WAY_CLASSES = {
    "street": "Roads and pedestrian streets, and everything not listed below (including service roads).",
    "path": "Footway, cycleway, track, path, bridleway, steps: shown on the map under *Paths*.",
    "planned": "Roads under construction (`highway=construction`): shown under *Roads under construction*.",
}

SOURCES = {
    "wikidata": "A confident Wikidata match for the street name, consistent with its buurt (tier 1).",
    "wikidata_surname_only": "Matched only to a Wikidata *family name* item: the surname exists, but not whom the street honours. No namesake is asserted.",
    "wikidata_weak_match": "A Wikidata match too weak to trust; the street stays unresolved unless a theme or a rule decides otherwise.",
    "wikidata_low_similarity": "A Wikidata match whose label barely resembles the street name.",
    "wikidata_no_match": "Nothing found on Wikidata.",
    "wikidata_thing_match": "Matched to a Wikidata item that is a thing, not a person or place: a weak, kind-only reading (tier 4).",
    "surname_unsupported": "A Wikidata surname match rejected: no title or person-naming buurt corroborates it, and the name is probably an ordinary word.",
    "buurt_theme_override": "The buurt's strong theme overrode a weaker or conflicting individual match (tier 4).",
    "buurt_theme_fallback": "No confident individual match; the kind is inferred from the buurt's theme (tier 4).",
    "title_heuristic": "The name starts with a person title (Burgemeester, Pastoor...): a person, not identified (tier 3).",
    "claude_knowledge": "A classification from general knowledge: the first-wave hand and language-model classifications, and the rules' own output (tier 2 when it names a specific namesake, tier 3 or 4 for kinds).",
    "web_search": "Individually researched with a web source (tier 1).",
    "osm_etymology": "OpenStreetMap's `name:etymology:wikidata` (or the street's own Wikidata item) names the namesake (tier 1).",
    "osm_place": "Named like a hamlet, neighbourhood, stream, lake or park within 1 km (OpenStreetMap): a local name; the feature shows the place exists, not that the street is named for it.",
}

CONFIDENCE = ("`confidence` is the score of whatever produced the classification (a Wikidata match score, the theme's confidence discounted by 0.9 or 0.8 for theme-based labels, a fixed value for rules and hand-made entries). "
              "Within one source it orders results; across sources it does not. Use `evidence_tier` to compare how well-founded labels are.")

SUBCATEGORIES = {
    # person
    "artist_visual": "painter or other visual artist", "artist_visual_sculptor": "sculptor", "musician_composer": "composer or musician",
    "writer_poet": "writer or poet", "mythological_figure": "figure from mythology or legend (also a group, such as the Argonauts)", "literary_mythical_figure": "figure from literature or myth",
    "scientist": "scientist", "scientist_physician": "scientist who was also a physician", "scientist_engineer": "scientist who was also an engineer", "engineer": "engineer",
    "physician_medical": "physician or medical figure", "legal_scholar": "jurist or legal scholar", "cartographer": "mapmaker", "aviation_pioneer": "aviation pioneer",
    "architect_or_historian": "architect or historian", "monarch_statesman": "monarch, royal house or statesman", "politician_statesman": "politician or statesman",
    "military": "soldier or military figure", "military_naval_or_politician": "military, naval or political figure", "mayor_local": "a local mayor",
    "boer_war_figure": "figure of the Boer wars", "statesman_liberator": "statesman or liberator", "industrialist_philips": "Philips industrialist", "philips_engineer": "Philips engineer",
    "explorer": "explorer", "activist": "activist", "human_rights_activist": "human rights activist", "religious": "saint, priest, bishop or other religious figure",
    "religious_order": "a religious order", "athlete": "sportsperson", "organization": "an organisation", "other": "a person of another kind", "unspecified_individual": "a person who could not be identified",
    # place
    "foreign_town": "town or city abroad", "foreign_town_wwii": "town abroad tied to the Second World War", "dutch_region": "Dutch region", "dutch_town": "Dutch town or city",
    "village": "village", "city": "city", "town": "town", "country": "country", "human settlement": "a human settlement (Wikidata's generic type)", "region": "region",
    "south_africa": "place in South Africa", "dutch_east_indies": "place in the former Dutch East Indies", "alpine_geography": "alpine place or feature",
    "castle_estate": "castle or country estate", "estate_feature": "part of an estate", "river": "river or stream", "mountain": "mountain", "lake": "lake",
    "local_landscape_feature": "a local field, road, hamlet or landscape name; no namesake identified", "biblical": "biblical place", "mythological": "mythological place",
    "local_landmark": "a local landmark, building or institution",
    # thing
    "flora": "tree or plant", "flora_flower": "flower", "flora_herb": "herb", "flora_food": "food plant", "wood_type": "kind of wood", "fungus": "fungus",
    "fauna": "animal", "fauna_butterfly": "butterfly", "fauna_mammal": "mammal", "fauna_fish": "fish", "fauna_and_flora": "animals and plants together",
    "instrument": "musical instrument", "occupation_guild": "trade or guild", "occupation_guild_textile": "textile trade", "fiction_title_or_motif": "title or motif from fiction",
    "sport": "sport", "currency": "currency", "dynasty": "dynasty (as a concept)", "architecture_term": "architectural term", "archaeology_term": "archaeological term",
    "astronomy": "astronomy: a planet, star or constellation", "technology_term": "technology term", "mineral": "mineral or gemstone", "industrial_philips_term": "Philips industrial term",
    "infrastructure": "infrastructure", "vessel_type": "type of ship or vessel", "development_concept": "a concept from the development of the neighbourhood",
    "local_feature": "(buurt themes) a local feature",
}

TIER_MEANING = {
    1: "A specific namesake backed by Wikidata, OpenStreetMap's etymology tags or a web source.",
    2: "A specific namesake from general knowledge, not verified.",
    3: "No individual, but the name itself shows the kind: a title or first-name pattern, a species word, a trade term, a surname match, a kind-only label.",
    4: "The kind rests on the buurt's naming theme, or on a weak match to a thing, not on the name.",
    5: "No namesake and no kind: generic or local names, anything unresolved.",
}

KNOWLEDGE_FILES = {
    "vocabulary.json": "Named lists per theme that the `vocabulary` rule reads (flowers, trees, birds, composers, painters, saints...).",
    "famous_people.txt": "`Street|kind|Person name` per line: streets named after a well-known person.",
    "person_labels.json": "Street name to `[subcategory, person name]`.",
    "species.txt": "`dutch stem=English name|Latin name`: plant and animal names.",
    "species_streets.txt": "`Street=English|Latin|stem`: street names the stems miss, exact.",
    "directional_places.json": "Places that directional roads lead to: `places` (stem to place), `foreign` (places abroad), `also_directional`.",
    "place_match_corrections.json": "Reviewed Wikidata place matches: `not_a_place` and `named_places`.",
    "common_words.txt": "Ordinary words and names, one per line, that are not namesakes.",
    "common_stems.txt": "Dutch words street names are built from (akker, bos, weg...): a name made only of these is an ordinary compound.",
    "common_compounds.txt": "Street names that are ordinary compounds, one per line.",
    "rule_exclusions.json": "Rule proposals reviewed and rejected: rule to `{street: reason}`.",
    "rules_status.json": "`disabled`: rule to a dated reason; a disabled rule is left out of runs that name no rule.",
    "theme_labels.json": "Plain-language names of street kinds, used to word derived buurt themes.",
    "osm_entity_kinds.json": "Reviewed `[category, subcategory, description]` for Wikidata items that OpenStreetMap etymology tags point to.",
    "osm_suggestions.json": "Streets whose OpenStreetMap ways lack the etymology tag but whose namesake we are confident of (the basis for tags worth adding in OSM).",
    "gemeenten.json": "Acquisition exceptions: `aliases` (PDOK name differs), `merged` (area of a merged gemeente: `pdok`, `buurt_prefix`), `early_place_polygon` (a note).",
    "gemeenten_index.json": "The gemeente registry: CBS code to `{name, province, historic?}`.",
}


def _tier_rows():
    import tiers
    return tiers.TIER_NAMES


def _subcategory_groups():
    import build_map
    return build_map.SUBGROUPS


def _rules():
    from rules import run
    import overrides
    return overrides.LAYER_ORDER, run.RULES


def _table(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def render() -> str:
    L: list[str] = []
    a = L.append
    a("# Data dictionary\n")
    a("*Generated by `python src/dictionary.py --write` from the code; do not edit by hand. Field meanings are in `src/dictionary.py`; tiers, subcategory groups, layers, rules and CSV columns are read from the code that uses them, and the tests fail if this file is out of date or "
      "the data contains a field, source or subcategory that is not described.*\n")
    a("Paths are relative to the build directory (`build/`) unless they start with `knowledge/`. A street is identified by `(gemeente_code, street)`; see [method.md](method.md) for what the values mean in the method and [pipeline.md](pipeline.md) for which step writes what.\n")
    a("## Files\n")
    for title, desc, fields, skip in FILES:
        a(f"### {title}\n")
        a(desc + "\n")
        a(_table([(f"`{k}`", t, m) for k, (t, m) in fields.items() if k not in skip], ["Field", "Type", "Meaning"]) + "\n")
    a("## Values\n")
    a("### category\n")
    a(_table([(f"`{k}`", v) for k, v in CATEGORIES.items()], ["Value", "Meaning"]) + "\n")
    a("### subcategory\n")
    a("The finer kind. The groups are the ones the map's legend shows (`SUBGROUPS` in `src/build_map.py`); a subcategory that is in no group falls under *Other / unspecified* on the map.\n")
    groups = _subcategory_groups()
    rows, seen = [], set()
    for cat, gs in groups.items():
        for label, _color, members in gs:
            for m in sorted(x for x in members if x):
                rows.append((cat, label, f"`{m}`", SUBCATEGORIES.get(m, "")))
                seen.add(m)
    for m in sorted(set(SUBCATEGORIES) - seen):
        rows.append(("(none)", "Other / unspecified", f"`{m}`", SUBCATEGORIES[m]))
    a(_table(rows, ["Category", "Map group", "Subcategory", "Meaning"]) + "\n")
    a("### source\n")
    a("How a classification was reached, in `streets_final.json` and the override layers.\n")
    a(_table([(f"`{k}`", v) for k, v in SOURCES.items()], ["Value", "Meaning"]) + "\n")
    a("### evidence tier\n")
    a("Derived from a street's other fields by `src/tiers.py`; lower is stronger, and refinement only ever moves a street toward 1.\n")
    a(_table([(k, v, TIER_MEANING[k]) for k, v in _tier_rows().items()], ["Tier", "Name", "Meaning"]) + "\n")
    a("### confidence\n")
    a(CONFIDENCE + "\n")
    a("### way class\n")
    a(_table([(f"`{k}`", v) for k, v in WAY_CLASSES.items()], ["Value", "Meaning"]) + "\n")
    a("### override layers and rules\n")
    a("Layers are applied in this order; a later one wins on the same street. `legacy_hand` is the frozen first-wave classifications; each of the others is regenerated by its rule; `corrections` comes from `corrections.json`.\n")
    order, rules = _rules()
    rows = []
    for i, name in enumerate(order, 1):
        desc = "Frozen first-wave hand and language-model classifications; no rule regenerates it." if name == "legacy_hand" else (rules[name][1] if name in rules else "")
        rows.append((i, f"`{name}`", desc))
    a(_table(rows, ["#", "Layer", "What it holds"]) + "\n")
    a("## Knowledge files\n")
    a("`knowledge/global/`: the curated lists. Per-gemeente files are described above (`corrections.json`, the override layers) plus `review_notes.json` (`{\"notes\": {street: note}}` shown in the review sheet) and `REVIEW.md` (the generated review sheet).\n")
    a(_table([(f"`{k}`", v) for k, v in KNOWLEDGE_FILES.items()], ["File", "Holds"]) + "\n")
    return "\n".join(L).rstrip() + "\n"


# --- verification against real data -------------------------------------------------------------------------------------------------------------

def verify_records(records: list[dict]) -> list[str]:
    """Problems with a list of streets_final records: a field, category, subcategory, source or way class the dictionary does not describe."""
    import collections
    problems = []
    keys = collections.Counter(k for r in records for k in r)
    problems += [f"streets_final field not documented: {k}" for k in keys if k not in STREET_FIELDS]
    for field, known in (("category", CATEGORIES), ("source", SOURCES), ("way_class", WAY_CLASSES), ("subcategory", SUBCATEGORIES)):
        seen = {r.get(field) for r in records if r.get(field) is not None}
        problems += [f"{field} value not documented: {v!r}" for v in sorted(seen - set(known), key=str)]
    return problems


def verify_themes(themes: list[dict]) -> list[str]:
    keys = {k for t in themes for k in t}
    problems = [f"theme field not documented: {k}" for k in sorted(keys - set(THEME_FIELDS))]
    problems += [f"theme category not documented: {v!r}" for v in sorted({t["category"] for t in themes} - set(CATEGORIES), key=str)]
    return problems


def verify_code() -> list[str]:
    """The dictionary against the code: CSV columns, override fields, the sources the map labels, every layer and every knowledge file."""
    import export_csv
    import overrides
    import build_map
    problems = []
    if list(export_csv.COLS) != CSV_STREETS:
        problems.append(f"export_csv.COLS differs from the documented CSV columns: {export_csv.COLS} vs {CSV_STREETS}")
    problems += [f"override field not documented: {f}" for f in overrides.FIELDS if f not in LAYER_FIELDS]
    problems += [f"build_map.SOURCE_LABELS has a source not documented: {s}" for s in build_map.SOURCE_LABELS if s not in SOURCES]
    problems += [f"build_map.SUBGROUPS has a subcategory not documented: {m}" for gs in build_map.SUBGROUPS.values() for _, _, ms in gs for m in ms if m and m not in SUBCATEGORIES]
    order, rules = _rules()
    problems += [f"rule without a layer slot: {r}" for r in rules if r not in order]
    import tiers
    if set(tiers.TIER_NAMES) != set(TIER_MEANING):
        problems.append("tiers.TIER_NAMES and dictionary.TIER_MEANING list different tiers")
    g = config.GLOBAL
    if g.exists():
        problems += [f"knowledge/global file not documented: {p.name}" for p in sorted(g.iterdir()) if p.is_file() and p.name not in KNOWLEDGE_FILES]
        problems += [f"documented knowledge file missing: {k}" for k in KNOWLEDGE_FILES if not (g / k).exists()]
    return problems


def verify_build() -> list[str]:
    problems = verify_code()
    final = config.ENRICHED / "streets_final.json"
    if final.exists():
        problems += verify_records(json.loads(final.read_text()))
    themes = config.ENRICHED / "buurt_themes_full.json"
    if themes.exists():
        problems += verify_themes(json.loads(themes.read_text())["buurten"])
    return problems


def check_doc() -> bool:
    return DOC.exists() and DOC.read_text() == render()


if __name__ == "__main__":
    if "--write" in sys.argv:
        DOC.write_text(render())
        print(f"wrote {DOC.relative_to(config.ROOT)}")
    elif "--check" in sys.argv:
        ok = check_doc()
        print("ok" if ok else "docs/data-dictionary.md is out of date: run python src/dictionary.py --write")
        sys.exit(0 if ok else 1)
    elif "--verify" in sys.argv:
        p = verify_build()
        print("\n".join(p) if p else "ok: the data matches the dictionary")
        sys.exit(1 if p else 0)
    else:
        print(render())
