"""OpenStreetMap etymology evidence as a rule: streets whose OSM ways carry name:etymology:wikidata (or whose own Wikidata item
says what it is named after) take that namesake, source `osm_etymology`, evidence tier 1.

Only non-conflicting proposals are returned: new information for streets we had not identified (tier 3-5), or an upgrade where
our tier-1/2 kind agrees. Where our own tier-1/2 classification and OSM disagree on the category the street is left alone and
reported (`python src/osm_report.py`) for review."""
from __future__ import annotations

import config
from .base import Context, Override, ROOT
from .evidence import TRUSTED   # noqa: F401  (kept for symmetry with other rules)

RULE = "osm_etymology"


def _norm_label(s):
    import re
    return re.sub(r"\W", "", (s or "").lower())


def _same_label(a, b):
    """Equal after normalising, or one contains the other and the shorter has two or more words ('Rembrandt van Rijn' in 'Rembrandt Harmensz. van Rijn');
    a bare first name ('Frederik' vs 'Frederik Philips') does not count as the same person."""
    import re
    na, nb = _norm_label(a), _norm_label(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = (a, nb) if len(na) <= len(nb) else (b, na)
    return len(re.findall(r"\w+", short or "")) >= 2 and _norm_label(short) in long_


def _wikidata_qids() -> dict:
    """street -> the Wikidata item our own name matching accepted (None when the match was not accepted)."""
    import json
    out = {}
    for line in (config.ENRICHED / "all_streets_wikidata.jsonl").open():
        r = json.loads(line)
        out[r["street"]] = r.get("wikidata_qid")
    return out


def propose(ctx: Context, records: list) -> list[Override]:
    from osm_report import classify_pair
    from tiers import evidence_tier
    wd = _wikidata_qids()
    out = []
    for rec in records:
        row = ctx.rows.get((rec["gemeente_code"], rec["street"]))
        if row is None:
            continue
        kind, detail = classify_pair(row, rec)
        tier = evidence_tier(row)
        items = [i for i in rec["items"] if i.get("category")]
        replaced = False
        label = " / ".join(dict.fromkeys(i["label"] for i in items if i.get("label")))
        if kind not in ("new", "agree") or not label:
            continue
        if kind == "agree" and tier == 1 and row.get("source") == "wikidata" and wd.get(rec["street"]) not in {i["qid"] for i in items} \
                and not _same_label(row.get("entity_label"), label):
            replaced = True                # our own Wikidata name match names a different item than the OSM mappers tagged: the street-level OSM tag wins
        elif kind == "agree" and (tier == 1 or _norm_label(label) == _norm_label(row.get("entity_label"))):
            continue                       # already externally identified, or nothing new
        cat, sub = detail
        if kind == "agree" and not replaced and row.get("subcategory") not in (None, "other", "unspecified_individual"):
            sub = row.get("subcategory")   # same kind already known: OSM supplies the specific namesake, not a re-labelling of the kind
        desc = items[0].get("description")
        out.append(Override(rec["gemeente_code"], rec["street"], cat, sub, label, desc, 0.85, source="osm_etymology",
                            source_url=f"https://www.wikidata.org/wiki/{items[0]['qid']}",
                            notes=f"OpenStreetMap {rec['via']}: {', '.join(i['qid'] for i in items)}", rule=RULE))
    return out
