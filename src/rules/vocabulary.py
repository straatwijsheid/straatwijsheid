"""Vocabulary rules for recurring Dutch street themes (flowers, trees, birds, composers, painters, saints...).

`classify(name)` is a pure function of the street name; the vocabularies are data in
data/knowledge/vocabulary.json. `classify_titles(name)` recognises streets named after an
unidentified person from a title or first-name pattern (Burgemeester X, Pastoor X, Jan X...).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .base import KNOWLEDGE, core, Override, person

RULE = "vocabulary"


@lru_cache(None)
def vocab() -> dict:
    v = json.loads((KNOWLEDGE / "vocabulary.json").read_text())
    for k in ("FLOWER", "HERB", "FOOD", "TREE", "BIRD", "MAMMAL", "FISH", "ASTRO", "FUNGUS", "CURRENCY", "APPLE", "FIRST_NAMES"):
        v[k] = set(v[k])
    return v


def candidates(name: str) -> list[str]:
    """Lowercase stems of a street name with its road word removed, incl. plural/genitive trims."""
    x = core(name).lower()
    c = [x]
    for suffix in ("en", "s", "n", "e"):
        if x.endswith(suffix) and len(x) - len(suffix) >= 3:
            c.append(x[:-len(suffix)])
    c.append(x.replace("-", " "))
    return c


def _layer1(g, name, v):
    cs, full = candidates(name), name.lower()

    def hit(table):
        for k in cs + [full]:
            if k in table:
                return k

    for table, sub, desc, conf in ((v["MUSIC"], "musician_composer", "Composer", 0.6), (v["ART"], "artist_visual", "Painter", 0.6),
                                   (v["WRITER"], "writer_poet", "Writer or poet", 0.55)):
        k = hit(table)
        if k:
            return Override(g, name, "person", sub, table[k], desc, conf, rule=RULE)
    k = hit(v["ROYAL"])
    if k:
        label, conf = v["ROYAL"][k]
        return Override(g, name, "person", "monarch_statesman", label, None, conf, rule=RULE)
    m = re.match(r"^Sint[ -](\w+)", name)
    if m:
        nm = m.group(1).lower()
        return Override(g, name, "person", "religious", v["SAINT"].get(nm) or "Saint " + m.group(1), None, 0.4, rule=RULE)
    for k in cs:
        for table, cat, sub, desc, conf in ((v["FLOWER"], "thing", "flora_flower", "Flower", 0.5), (v["HERB"], "thing", "flora_herb", "Herb", 0.45),
                                            (v["FOOD"], "thing", "flora_food", "Crop or fruit", 0.45), (v["TREE"], "thing", "flora", "Tree or plant", 0.45),
                                            (v["BIRD"], "thing", "fauna", "Bird", 0.5), (v["MAMMAL"], "thing", "fauna_mammal", "Mammal", 0.5),
                                            (v["FISH"], "thing", "fauna_fish", "Fish", 0.5)):
            if k in table:
                return Override(g, name, cat, sub, core(name), desc, conf, rule=RULE)


def _layer2(g, name, v):
    cs, full = candidates(name), name.lower()

    def hit(t):
        for k in cs + [full]:
            if k in t:
                return k

    k = hit(v["SCI"])
    if k:
        return Override(g, name, "person", "scientist", v["SCI"][k], "Scientist or inventor", 0.55, rule=RULE)
    k = hit(v["MYTH"])
    if k:
        return Override(g, name, "person", "mythological_figure", v["MYTH"][k], "Mythological figure or deity", 0.5, rule=RULE)
    k = hit(v["REGION"])
    if k and re.search(r"(straat|laan|plein|hof)$", full) and len(name.split()) == 1:
        label, sub = v["REGION"][k]
        return Override(g, name, "place", sub, label, None, 0.4, rule=RULE)
    if hit(v["ASTRO"]):
        return Override(g, name, "thing", "astronomy", core(name), "Astronomy term", 0.45, rule=RULE)
    if hit(v["FUNGUS"]):
        return Override(g, name, "thing", "fungus", core(name), "Fungus", 0.5, rule=RULE)
    if hit(v["CURRENCY"]) and len(name.split()) <= 2:
        return Override(g, name, "thing", "currency", core(name), "Coin or currency", 0.45, rule=RULE)
    if hit(v["APPLE"]) and len(name.split()) == 1:
        return Override(g, name, "thing", "flora_food", name, "Apple variety", 0.45, rule=RULE)


def classify(gemeente: str, name: str) -> Override | None:
    """The vocabulary classification of one street name, or None. The second (science, myth, region,
    astronomy, fungus, currency, apple) layer wins over the first when both match."""
    v = vocab()
    return _layer2(gemeente, name, v) or _layer1(gemeente, name, v)


_ROAD_END = r"(straat|laan|plein|hof|weg|pad|park|dreef|singel|steeg)$"


def classify_titles(gemeente: str, name: str) -> Override | None:
    """A person who could not be identified, recognised from a title or name pattern."""
    v = vocab()
    church, civic, other = v["CHURCH"], v["CIVIC"], v["OTHER_TITLES"]
    w = name.split()
    if re.match(church + r"[ .]", name) or re.match(r"^Sint[- ]", name) or re.match(r"^St\.", name):
        return person(gemeente, name, "religious", notes="Named after a clergy member or saint who could not be identified", rule=RULE)
    if re.match(r"^(Burgemeester|Burg\.?)[ .]", name):
        return person(gemeente, name, "mayor_local", notes="Named after a former mayor who could not be identified", rule=RULE)
    if re.match(civic + r"[ .]", name) or re.match(other + r"[ .]", name):
        return person(gemeente, name, "other", rule=RULE)
    low = name.lower()
    if len(w) >= 2 and w[0].lower() in v["FIRST_NAMES"] and re.search(_ROAD_END, low) and not re.search(r"(weg|pad)$", low):
        return person(gemeente, name, "other", rule=RULE)
    if re.match(r"^(Van|Ten|Ter|De La|Van de|Van der|Van den|Van 't)[ ]", name) and re.search(r"(straat|laan|plein|hof|erf|dreef)$", low):
        return person(gemeente, name, "other", rule=RULE)
    return None
