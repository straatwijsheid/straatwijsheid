"""Accepted Wikidata place matches that are wrong, and their repairs.

Wikidata often matches an ordinary word to an unrelated place of the same name (Brugstraat -> Bruges, Heide -> a German
town, Klarinet -> a settlement in South Africa). data/knowledge/place_match_corrections.json lists the names reviewed by hand:
 not_a_place   name -> [category, subcategory, label, description, note]   (the street is not named after a place)
 named_places  name -> [label, description, subcategory]                    (it is a place, but Wikidata picked an obscure namesake)
Any other accepted place match whose description names an obscure place abroad gets a generic description so the tooltip does
not mislead."""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .base import KNOWLEDGE, Context, Override

RULE = "wikidata_place_review"
OBSCURE = re.compile(r"\b(south africa|austria|germany|france|italy|spain|united states|canada|brazil|poland|czech|switzerland|sweden|norway|denmark|russia|china|india|australia|mexico|argentina|ireland|united kingdom|england|scotland|romania|bulgaria|ukraine|wales|queensland|ontario|maryland|arkansas|yorkshire)\b", re.I)
WELL_KNOWN = re.compile(r"\b(capital|largest city|longest river|country|volcano|mountain in the pennine alps|major river)\b", re.I)


@lru_cache(None)
def corrections() -> dict:
    return json.loads((KNOWLEDGE / "place_match_corrections.json").read_text())


def review(ctx: Context) -> list[Override]:
    nap, named, out = corrections()["not_a_place"], corrections()["named_places"], []
    for r in ctx.final:
        if r["source"] != "wikidata" or r["category"] != "place":
            continue
        g, s = r["gemeente"], r["street"]
        if s in nap:
            cat, sub, label, desc, note = nap[s]
            out.append(Override(g, s, cat, sub, label, desc, 0.4, notes=note, rule=RULE))
        elif s in named:
            label, desc, sub = named[s]
            out.append(Override(g, s, "place", sub, label, desc, 0.6, notes="Named place identified from the street name; Wikidata's namesake was a different, obscure place", rule=RULE))
        elif r.get("subcategory") != "country":
            d = r.get("entity_description") or ""
            if OBSCURE.search(d) and not WELL_KNOWN.search(d):
                sub = r["subcategory"] if r["subcategory"] in ("river", "mountain", "lake") else "foreign_town"
                out.append(Override(g, s, "place", sub, r.get("entity_label"), "Place name; Wikidata's exact namesake (a same-named place) is not determined", 0.5,
                                    notes="Wikidata description named an obscure same-named place abroad, which would mislead; generic description used", rule=RULE))
    return out
