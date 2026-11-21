"""How well do our classifications agree with OpenStreetMap's etymology tags? (OSM is independent of our name matching.)"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osm_etymology import load                              # noqa: E402
from rules.base import Context                               # noqa: E402
from tiers import TIER_NAMES, evidence_tier                  # noqa: E402


def _norm(s):
    return re.sub(r"\W", "", (s or "").lower())


def _tokens(s):
    return {t for t in re.split(r"[^a-zë]+", (s or "").lower()) if len(t) >= 4}


def label_agrees(ours, theirs):
    return bool(ours) and bool(theirs) and (_norm(ours) == _norm(theirs) or bool(_tokens(ours) & _tokens(theirs)))


def classify_pair(row, rec):
    """('agree'|'new'|'conflict'|'unusable', detail) comparing one of our rows with one OSM record."""
    items = [i for i in rec["items"] if i.get("category")]
    if not items:
        return "unusable", "no usable kind"
    cats = {i["category"] for i in items}
    if len(cats) > 1:
        return "unusable", "mixed kinds"
    cat, sub = items[0]["category"], items[0]["subcategory"]
    tier = evidence_tier(row)
    if tier == 3 and row["category"] != cat:
        return "conflict", (cat, sub)          # the name itself already said person/place/thing: do not overrule it silently
    if tier >= 3:
        return "new", (cat, sub)
    if row["category"] != cat:
        return "conflict", (cat, sub)
    return "agree", (cat, sub)


def report():
    ctx = Context.load()
    recs = load()
    by = collections.defaultdict(collections.Counter)
    conflicts = []
    usable = 0
    for rec in recs:
        row = ctx.rows.get((rec["gemeente"], rec["street"]))
        if row is None:
            by["(not in our data)"]["n"] += 1
            continue
        kind, detail = classify_pair(row, rec)
        t = evidence_tier(row)
        by[t][kind] += 1
        if kind == "agree":
            lab = rec["items"][0].get("label")
            by[t]["same specific name"] += label_agrees(row.get("entity_label"), lab)
            by[t]["same subcategory"] += (row.get("subcategory") == detail[1])
        if kind == "conflict":
            conflicts.append((rec, row, detail))
        usable += kind != "unusable"
    print(f"{len(recs)} streets carry OSM etymology evidence; {usable} usable (a recognisable kind)")
    print(f"{'our tier':44}{'streets':>8}{'agree':>7}{'conflict':>9}{'new info':>9}   agreement on category (of comparable)")
    for t in sorted(k for k in by if isinstance(k, int)):
        c = by[t]
        n = sum(c[k] for k in ("agree", "conflict", "new", "unusable"))
        comp = c["agree"] + c["conflict"]
        print(f"{t} {TIER_NAMES[t]:42}{n:>8}{c['agree']:>7}{c['conflict']:>9}{c['new']:>9}   {c['agree'] / comp:6.1%} of {comp}" if comp else f"{t} {TIER_NAMES[t]:42}{n:>8}{c['agree']:>7}{c['conflict']:>9}{c['new']:>9}")
    print("\nsame subcategory / same specific name among the agreeing streets:",
          {t: (by[t]["same subcategory"], by[t]["same specific name"], by[t]["agree"]) for t in sorted(k for k in by if isinstance(k, int)) if by[t]["agree"]})
    print(f"\n{len(conflicts)} conflicts (our tier 1-2 says one kind, OSM another):")
    for rec, row, (cat, sub) in conflicts[:40]:
        it = rec["items"][0]
        print(f"  {rec['gemeente'][:12]:13}{rec['street']:28} ours {row['category']}/{row.get('subcategory')}/{row.get('entity_label')}   OSM {cat}/{sub}/{it.get('label')}")
    return conflicts


if __name__ == "__main__":
    report()
