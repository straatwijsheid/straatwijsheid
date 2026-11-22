"""Local-knowledge review sheet: streets in a gemeente (or set) read as a kind of person but with no namesake, grouped by buurt.

  python src/review_sheet.py Eindhoven > REVIEW_EINDHOVEN.md

Reply with the buurt and a line per street ("Banstraat = Jan Ban, organist" / "wrong: not a composer street"); the answers go into
data/knowledge/corrections.json (street-level, tier 2 or 1 if the user points to Wikidata/OSM) and sharpen the buurt themes."""
from __future__ import annotations

import config
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(gemeenten):
    notes = json.loads((config.KNOWLEDGE / "review_notes.json").read_text())
    rows = json.loads((config.ENRICHED / "streets_final.json").read_text())
    by = collections.defaultdict(list)
    for r in rows:
        if r["gemeente"] in gemeenten and r["category"] == "person" and not r.get("entity_label") and r["evidence_tier"] >= 3:
            by[(r["gemeente"], r["buurt"] or "(no buurt)")].append(r)
    print(f"# Review sheet: {', '.join(gemeenten)}\n")
    print("Streets read as *a person of some kind* but with no namesake identified. Per buurt: the naming theme we detected, then each street "
          "with the kind we assigned. Answer however is quickest, e.g. `Banstraat = Jan Ban, organist` or `Bertelmanstraat: wrong, a plant`. "
          "Skip any you do not know.\n")
    for (g, b), items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        theme = items[0].get("buurt_theme") or "(none)"
        print(f"## {b} ({g}): {len(items)} streets\n*Buurt theme detected:* {theme}\n")
        print("| Street | We read it as | Tier | Our note | Your answer |\n|---|---|---|---|---|")
        for r in sorted(items, key=lambda r: r["street"]):
            print(f"| {r['street']} | {(r.get('subcategory') or 'person').replace('_', ' ')} | {r['evidence_tier']} | {notes['notes'].get(g + '|' + r['street'], '')} | |")
        print()
    extra = [x for x in notes.get("extra", []) if x["gemeente"] in gemeenten]
    if extra:
        print("## Further checks: already labelled, but they look wrong\n\n| Street | Buurt | Question | Your answer |\n|---|---|---|---|")
        for x in extra:
            print(f"| {x['street']} | {x['buurt']} | {x['question']} | |")
        print()


if __name__ == "__main__":
    main(sys.argv[1:] or ["Eindhoven"])
