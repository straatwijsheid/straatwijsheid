"""Roads named after the place they lead to: <Place>se/sche + weg/dijk/straat/... (Eindhovensedijk).

The namesake is the destination place. A stem counts as a place when it is a gemeente, wijk or buurt
name in the dataset, or is listed in data/knowledge/directional_places.json (nearby places and
destinations that are not in the dataset, e.g. Antwerp, Kleef)."""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .base import KNOWLEDGE, Override

RULE = "directional_road"
PATTERN = re.compile(r"^([A-Z][\w'’-]*?)(se|sche)(weg|dijk|straat|baan|laan|steeg|pad|dreef)$")


@lru_cache(None)
def _places():
    return json.loads((KNOWLEDGE / "directional_places.json").read_text())


def classify(gemeente: str, name: str, place_names: set) -> Override | None:
    m = PATTERN.match(name)
    if not m:
        return None
    stem, data = m.group(1), _places()
    if stem in data["places"]:
        label = data["places"][stem]
    elif stem.lower() in place_names:
        label = stem
    else:
        return None
    sub = "foreign_town" if stem in data["foreign"] else "dutch_town"
    return Override(gemeente, name, "place", sub, label, "Road named after the place it leads to", 0.6,
                    notes="Directional road name (<place>se<road>): named after the place it runs toward", rule=RULE)
