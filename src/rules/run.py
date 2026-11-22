"""Run the rule families against the dataset; each rule owns one override layer (src/overrides.py).

  python src/rules/run.py --list
  python src/rules/run.py --check [RULE ...]     dry run: what each rule proposes, relative to the layers below it
  python src/rules/run.py --apply RULE [...]     regenerate those rules' layers (data/enriched/overrides/<rule>.json) and nothing else
  python src/rules/run.py --apply --cascade RULE regenerate RULE and every enabled rule above it, in precedence order
                                                 (then `pipeline.py rebuild`, or reconcile / analyze / build_map / export_csv)

With no rule named, every enabled rule runs (data/knowledge/rules_status.json lists the disabled ones). A rule computes its proposals from
the hand classifications plus the layers *below* it, never from its own previous layer, so re-applying is repeatable; the printed diff says
what a regeneration changed in its layer. Apply never replaces a tier-1 street (a verified identification) unless --force is given."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import overrides  # noqa: E402

from rules import audits, corrections, directional, labels, osm, place_review, species, surnames, vocabulary    # noqa: E402
from rules.base import Context, Override                                               # noqa: E402
from tiers import evidence_tier                                                               # noqa: E402

STATUS = config.KNOWLEDGE / "rules_status.json"
EXCLUSIONS = config.KNOWLEDGE / "rule_exclusions.json"
STRONG = {1, 2}   # tiers that name a specific namesake
PRECEDENCE = overrides.PRECEDENCE   # later wins on the same street: reviewed corrections and external evidence last


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


def disabled() -> dict:
    return json.loads(STATUS.read_text()).get("disabled", {}) if STATUS.exists() else {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true", help="print what each rule proposes, relative to the layers below it")
    ap.add_argument("--apply", action="store_true", help="regenerate each named rule's override layer (and nothing else)")
    ap.add_argument("--cascade", action="store_true", help="with --apply: also regenerate every enabled rule above the named ones, in order (layers above a rule were computed seeing its old output)")
    ap.add_argument("--force", action="store_true", help="allow replacing tier-1 (externally verified) streets")
    ap.add_argument("rules", nargs="*")
    a = ap.parse_args(argv)
    off = disabled()
    if a.list or not (a.check or a.apply):
        for k, (_, d) in RULES.items():
            print(f"{k:24} {'[disabled] ' if k in off else ''}{d}")
        return 0
    order = lambda names: sorted(names, key=lambda n: PRECEDENCE.index(n))
    unknown = [n for n in a.rules if n not in RULES]
    if unknown:
        sys.exit(f"unknown rule(s): {unknown}; see --list")
    names = order(a.rules or [n for n in RULES if n not in off])
    if a.cascade:
        first = PRECEDENCE.index(names[0])
        names = order(set(names) | {n for n in PRECEDENCE[first:] if n in RULES and n not in off})
    import reconcile
    for n in names:
        # what this rule sees: hand classifications and every rule layer *below* it, never its own layer or anything above
        # (a rule's proposals must not depend on its previous output, or regenerating would lose it)
        ctx = Context.load(final=reconcile.compute_final(upto=n))
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
        layer = {}
        for o in proposals:
            cur = ctx.rows.get(o.key)
            if cur is not None and not a.force and evidence_tier(cur) == 1 and n not in ("wikidata_place_review", "corrections", "osm_etymology"):
                continue
            layer[o.key] = o.record()
        change = overrides.diff(overrides.load_layer(n), list(layer.values()))
        print(f"  layer {n}: {len(layer)} entries; against the layer on disk: {change['added']} added, {change['removed']} removed, {change['changed']} changed, {change['unchanged']} unchanged")
        if a.apply:
            overrides.write_layer(n, list(layer.values()))
            print(f"  wrote {config.rel(overrides.layer_path(n))}")
    if a.apply:
        print("\nnow re-run reconcile.py, analyze.py, build_map.py, export_csv.py (or `pipeline.py rebuild`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
