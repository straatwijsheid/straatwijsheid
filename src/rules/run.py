"""Run the rule families against the dataset.

  python src/rules/run.py --list
  python src/rules/run.py --check [RULE ...]     dry run: what each rule proposes and how it compares with the current data
  python src/rules/run.py --apply RULE [...]     write the proposals into data/enriched/manual_overrides.json
                                                 (then re-run reconcile.py / analyze.py / build_map.py / export_csv.py)

Apply never replaces a tier-1 street (a verified identification) unless --force is given, and records the producing rule
in each override's `rule` field."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rules import audits, corrections, directional, labels, osm, place_review, species, surnames, vocabulary    # noqa: E402
from rules.base import Context, Override, DATA                                               # noqa: E402
from tiers import evidence_tier                                                               # noqa: E402

OVERRIDES = DATA / "enriched" / "manual_overrides.json"
EXCLUSIONS = DATA / "knowledge" / "rule_exclusions.json"
STRONG = {1, 2}   # tiers that name a specific namesake
# when several rules are applied together, a later one wins on the same street: reviewed corrections and external evidence last
PRECEDENCE = ["label_cleanup", "species", "vocabulary", "titles", "directional_road", "bare_surname", "same_name_harmonise", "person_consensus",
              "theme_forced_name_fit", "wikidata_place_review", "name_resolver", "osm_places", "osm_etymology", "corrections"]


def rule_directional(ctx):
    return [o for r in ctx.final if (o := directional.classify(r["gemeente"], r["street"], ctx.place_names))]


def rule_vocabulary(ctx):
    """Vocabulary matches for streets that do not already name a specific namesake."""
    return [o for r in ctx.final if evidence_tier(r) not in STRONG and (o := vocabulary.classify(r["gemeente"], r["street"]))]


def rule_titles(ctx):
    return [o for r in ctx.final if evidence_tier(r) == 5 and (o := vocabulary.classify_titles(r["gemeente"], r["street"]))]


def rule_species(ctx):
    out = []
    for r in ctx.final:
        if r["category"] != "thing" or not (r.get("subcategory") or "").startswith(("flora", "fauna")) or r["source"] != "claude_knowledge":
            continue
        d = r.get("entity_description") or None
        if d is not None and "Dutch name" in d:
            continue
        hit = species.describe(r["street"])
        if hit and (d in species.GENERIC_DESCRIPTIONS or d is None):
            en, la, stem = hit
            out.append(Override(r["gemeente"], r["street"], r["category"], r["subcategory"], en, species.description(la, stem), r["confidence"], notes=r.get("notes"), rule="species"))
    return out


def rule_name_resolver(ctx):
    from names import candidates as C, propose
    from osm_etymology import load as load_osm
    table = C.build_table(ctx, C.load_wikidata_records(), osm=load_osm())
    return [o for o, _ in propose.evaluate(ctx, table)]


def rule_corrections(ctx):
    from osm_etymology import load
    return corrections.apply(ctx, load())


def rule_osm(ctx):
    from osm_etymology import load
    return osm.propose(ctx, load())


def rule_osm_places(ctx):
    from rules import osm_places
    return osm_places.propose(ctx)


RULES = {
    "osm_places": (rule_osm_places, "street named like a hamlet/neighbourhood/stream/lake/park within 1 km (OSM) -> place / local name, tier 2"),
    "name_resolver": (rule_name_resolver, "name-level resolver: kinds (and backed names) for streets at tiers 3-5, reviewed-safe changes only"),
    "corrections": (rule_corrections, "reviewed street-level corrections from data/knowledge/corrections.json"),
    "label_cleanup": (labels.repair_saint_labels, "saint labels that repeat the road word (Saint Janstraat -> Saint John)"),
    "osm_etymology": (rule_osm, "OpenStreetMap name:etymology(:wikidata) -> the namesake, tier 1 (conflicts with our tier 1-2 are left alone)"),
    "directional_road": (rule_directional, "<Place>se<road> streets -> the place they lead to"),
    "vocabulary": (rule_vocabulary, "flowers, trees, birds, composers, painters, saints, science, myth, regions... by name"),
    "titles": (rule_titles, "Burgemeester/Pastoor/first-name patterns -> an unidentified person"),
    "species": (rule_species, "generic plant/animal description -> the actual species"),
    "bare_surname": (surnames.resolve, "Wikidata family-name-only matches, resolved with the buurt's naming theme"),
    "same_name_harmonise": (audits.harmonise_same_name, "same name, different class, no buurt support -> the majority class"),
    "person_consensus": (audits.person_consensus, "unidentified person streets take the kind of person the buurt supports"),
    "theme_forced_name_fit": (audits.theme_forced, "labels forced by a buurt theme need support from the name itself"),
    "wikidata_place_review": (place_review.review, "accepted Wikidata place matches that are not places, or have a misleading description"),
}


def compare(ctx, proposals):
    same = diff = 0
    examples = []
    for o in proposals:
        cur = ctx.rows.get(o.key)
        if cur is None:
            continue
        if (cur["category"], cur.get("subcategory"), cur.get("entity_label")) == (o.category, o.subcategory, o.entity_label):
            same += 1
        else:
            diff += 1
            if len(examples) < 6:
                examples.append(f"{o.gemeente[:10]:11}{o.street:28} now {cur['category']}/{cur.get('subcategory')}/{cur.get('entity_label')} -> {o.category}/{o.subcategory}/{o.entity_label}")
    return same, diff, examples


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true", help="allow replacing tier-1 (externally verified) streets")
    ap.add_argument("rules", nargs="*")
    a = ap.parse_args(argv)
    if a.list or not (a.check or a.apply):
        for k, (_, d) in RULES.items():
            print(f"{k:24} {d}")
        return 0
    names = sorted(a.rules or list(RULES), key=lambda n: PRECEDENCE.index(n) if n in PRECEDENCE else -1)
    unknown = [n for n in names if n not in RULES]
    if unknown:
        sys.exit(f"unknown rule(s): {unknown}; see --list")
    ctx = Context.load()
    total = 0
    pending = {}
    for n in names:
        proposals = RULES[n][0](ctx)
        excluded = json.loads(EXCLUSIONS.read_text()).get(n, {}) if EXCLUSIONS.exists() else {}
        if excluded:
            dropped = [o for o in proposals if o.street in excluded]
            proposals = [o for o in proposals if o.street not in excluded]
            if dropped:
                print(f"\n[{n}] excluded {len(dropped)} reviewed-and-rejected: {sorted({o.street for o in dropped})}")
        same, diff, examples = compare(ctx, proposals)
        print(f"\n[{n}] proposes {len(proposals)}: {same} already in the data, {diff} would change")
        for e in examples:
            print("   ", e)
        for o in proposals:
            cur = ctx.rows.get(o.key)
            if cur is not None and not a.force and evidence_tier(cur) == 1 and n not in ("wikidata_place_review", "corrections", "osm_etymology"):
                continue
            pending[o.key] = o
    if a.apply:
        data = json.loads(OVERRIDES.read_text())
        existing = {(o["gemeente"], o["street"]): o for o in data["overrides"]}
        for k, o in pending.items():
            rec = o.record()
            rec["rule"] = o.rule
            existing[k] = rec
        data["overrides"] = list(existing.values())
        OVERRIDES.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\nwrote {len(pending)} overrides to {OVERRIDES.relative_to(DATA.parent)}; now re-run reconcile.py, analyze.py, build_map.py, export_csv.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
