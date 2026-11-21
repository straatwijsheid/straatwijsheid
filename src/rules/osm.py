"""OpenStreetMap etymology evidence as a rule: streets whose OSM ways carry name:etymology:wikidata (or whose own Wikidata item
says what it is named after) take that namesake, source `osm_etymology`, evidence tier 1.

Only non-conflicting proposals are returned: new information for streets we had not identified (tier 3-5), or an upgrade where
our tier-1/2 kind agrees. Where our own tier-1/2 classification and OSM disagree on the category the street is left alone and
reported (`python src/osm_report.py`) for review."""
from __future__ import annotations

from .base import Context, Override
from .evidence import TRUSTED   # noqa: F401  (kept for symmetry with other rules)

RULE = "osm_etymology"


def _norm_label(s):
    import re
    return re.sub(r"\W", "", (s or "").lower())


def propose(ctx: Context, records: list) -> list[Override]:
    from osm_report import classify_pair
    from tiers import evidence_tier
    out = []
    for rec in records:
        row = ctx.rows.get((rec["gemeente"], rec["street"]))
        if row is None:
            continue
        kind, detail = classify_pair(row, rec)
        tier = evidence_tier(row)
        items = [i for i in rec["items"] if i.get("category")]
        label = " / ".join(dict.fromkeys(i["label"] for i in items if i.get("label")))
        if kind not in ("new", "agree") or not label:
            continue
        if kind == "agree" and (tier == 1 or _norm_label(label) == _norm_label(row.get("entity_label"))):
            continue                       # already externally identified, or nothing new
        cat, sub = detail
        if kind == "agree" and row.get("subcategory") not in (None, "other", "unspecified_individual"):
            sub = row.get("subcategory")   # same kind already known: OSM supplies the specific namesake, not a re-labelling of the kind
        desc = items[0].get("description")
        out.append(Override(rec["gemeente"], rec["street"], cat, sub, label, desc, 0.85, source="osm_etymology",
                            source_url=f"https://www.wikidata.org/wiki/{items[0]['qid']}",
                            notes=f"OpenStreetMap {rec['via']}: {', '.join(i['qid'] for i in items)}", rule=RULE))
    return out
