"""Turn resolver decisions into reviewed-safe override proposals.

The resolver (`resolve.py`) accepts about 4.7k streets at tiers 3-5, but a sample showed many of the *changes* are weak: Wikidata-only place
readings of ordinary words, buurt names matched as towns, vague kinds, shuffles between near-synonyms, labels for names that many
different people share. This module keeps only the changes that sample showed to be reliable:

  * never overrides a street whose current classification was deliberately reviewed (notes say Wikidata mismatch, corrections, audits...)
  * never proposes a vaguer kind than the street has (other / unspecified / no subcategory), nor a shuffle between local kinds,
    nor moves a technology/architecture term to a local name
  * places: only directional roads (<Place>se<road>), OSM evidence, or a river/lake that already is one (adds the name); not
    'village'/'town'/'mountain' guesses, and nothing resting only on Wikidata or on a buurt/wijk name
  * persons: the kind only, plus a specific name only when OSM or a vocabulary/famous-people rule backs it (a bare first name
    like Hendrik is shared by many people)
  * nothing that rests only on Wikidata evidence
  * score >= MIN_SCORE and margin >= MIN_MARGIN"""
from __future__ import annotations

import re

from rules.base import Context, Override
from tiers import evidence_tier
from . import candidates as C, resolve as R

RULE = "name_resolver"
MIN_SCORE, MIN_MARGIN = 0.45, 0.20
REVIEWED = ("Wikidata", "Reviewed correction", "Standardised rule", "Ordinary Dutch word", "Theme-audit", "Harmonised", "Classified by consensus",
            "Buurt-theme supported", "Named place identified", "Mythological", "Given name", "Not a place", "Single word in a buurt")
VAGUE = {None, "other", "unspecified_individual"}
LOCAL = ("local_landscape_feature", "local_landmark")
PLACE_GUESSES = {"village", "town", "city", "human settlement", "mountain", "lake", "dutch_town", "foreign_town", "country", "dutch_region", "castle_estate"}
DIRECTIONAL = re.compile(r"(se|sche)(weg|straat|dijk|laan|baan|steeg|pad|dreef)$")
LABEL_RULES = {"vocabulary", "famous_people", "species"}


def _spec(sub):
    return 0 if sub is None else 1 if sub in VAGUE else 2


def evaluate(ctx: Context, table: dict, idx: R.ContextIndex | None = None, min_score=MIN_SCORE, min_margin=MIN_MARGIN,
             declined: list | None = None) -> list[tuple[Override, dict]]:
    """`declined`, if given, collects (row, reason, resolver result) for accepted resolver changes this filter drops."""
    idx = idx or R.ContextIndex(ctx)
    out = []

    def no(row, reason, res, cur=None, new=None):
        if declined is not None:
            declined.append({"row": row, "reason": reason, "res": res, "cur": cur, "new": new})
    for row in ctx.final:
        tier = evidence_tier(row)
        if tier < 3 or any(k in (row.get("notes") or "") for k in REVIEWED):
            continue
        entry = table[C.name_key(row["street"])]
        res = R.resolve_street(entry, *idx.counters(row), street=(row["gemeente"], row["street"]))
        if res.decision != "accept" or res.score < min_score or res.margin < min_margin:
            continue
        cur, new = R.norm_kind(row) or (None, None), res.kind
        if new == cur and (res.label is None or res.label == row.get("entity_label")):
            continue
        cand = entry.candidates[new]
        own = (row["gemeente"], row["street"])
        osm_own = any((g, s) == own for g, s, _ in cand.osm)
        osm_any = bool(cand.osm)
        rules = set(cand.rules)
        observed = sum(1 for g, s, t, _ in cand.occurrences if (g, s) != own and t <= 3)
        # --- vague / synonym / downgrade ---
        if new[1] in VAGUE and not (cur[1] in VAGUE and res.label):
            no(row, "vague kind", res, cur, new); continue
        if cur[0] == "place" and new[0] == "place" and cur[1] in LOCAL and new[1] in LOCAL:
            no(row, "local shuffle", res, cur, new); continue
        if _spec(new[1]) < _spec(cur[1]) or (cur[0] == "thing" and cur[1] in ("technology_term", "architecture_term") and new[0] == "place"):
            no(row, "downgrade", res, cur, new); continue
        # --- evidence must not be Wikidata alone ---
        if not (osm_any or rules - {"place_name"} or observed >= 2):
            no(row, "wikidata only", res, cur, new); continue
        # --- places ---
        label = res.label
        if new[0] == "place" and new[1] != LOCAL[0]:
            directional = bool(DIRECTIONAL.search(row["street"])) or "directional_road" in rules
            already = cur == new                                   # a river that is a river: adds the name
            if new[1] in PLACE_GUESSES and not (directional or osm_own or already):
                no(row, "place guess", res, cur, new); continue
            if new[1] == "river" and not (already or osm_own or directional):
                no(row, "river guess", res, cur, new); continue
            if rules == {"place_name"}:
                no(row, "place name only", res, cur, new); continue
        # --- persons: kind only unless a name is backed ---
        if new[0] == "person" and not (osm_own or (rules & LABEL_RULES)):
            label = None
        if cur == new and label is None:
            continue
        why = f"{observed} classified streets elsewhere" + (f", rules {sorted(rules)}" if rules else "") + (", OSM" if osm_any else "")
        out.append((Override(row["gemeente"], row["street"], new[0], new[1], label, None, round(min(0.6, 0.3 + res.score / 2), 2),
                             notes=f"Name-level resolver: kind '{new[1]}' backed by {why}; neighbours in the buurt/wijk fit it (score {res.score}, margin {res.margin})", rule=RULE),
                    {"cur": cur, "tier": tier, "score": res.score, "margin": res.margin, "why": why}))
    return out
