"""Reviewed street-level corrections, kept as data (data/knowledge/corrections.json) and applied by a rule.

Each entry fixes one street in one gemeente and says why. Fields: gemeente, street, category, subcategory, entity_label,
entity_description, confidence, reason. `"from_osm": true` takes the namesake (label, description, Wikidata link) from the
street's OpenStreetMap etymology record and makes the source `osm_etymology` (tier 1), keeping the kind given here."""
from __future__ import annotations

import json
from functools import lru_cache

from .base import KNOWLEDGE, Context, Override

RULE = "corrections"


@lru_cache(None)
def entries() -> list:
    return json.loads((KNOWLEDGE / "corrections.json").read_text())["corrections"]


def apply(ctx: Context, osm_records: list | None = None) -> list[Override]:
    osm = {(r["gemeente"], r["street"]): r for r in (osm_records or [])}
    out = []
    for e in entries():
        key = (e["gemeente"], e["street"])
        if key not in ctx.rows:
            continue
        label, desc, source, url = e.get("entity_label"), e.get("entity_description"), "claude_knowledge", e.get("source_url")
        if e.get("from_osm") and key in osm:
            item = next((i for i in osm[key]["items"] if i.get("label")), None)
            if item:
                label, desc, source, url = item["label"], item.get("description"), "osm_etymology", f"https://www.wikidata.org/wiki/{item['qid']}"
        out.append(Override(e["gemeente"], e["street"], e["category"], e.get("subcategory"), label, desc, e.get("confidence", 0.5),
                            source=source, source_url=url, notes=f"Reviewed correction: {e['reason']}", rule=RULE))
    return out
