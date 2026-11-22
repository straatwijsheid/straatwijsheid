"""Plant and animal names: turn a generic 'Plant'/'Bird' description into the actual species.

data/knowledge/species.txt          Dutch stem = English name | Latin name   (matched with suffix stripping)
data/knowledge/species_streets.txt  Street name = English | Latin | Dutch stem (exact, for names the stems miss)
Description format: "<Latin>; Dutch name '<stem>'" (kept stable: other rules and the tooltip depend on it)."""
from __future__ import annotations

import re
from functools import lru_cache

from .base import GLOBAL, core, read_lines

# placeholders / obscure local names that must never get a species from the stem dictionary
SKIP = set("fliere knelisroos kriezel krullevaar lieverman melkster repeltand roskam hennegras leliegras kropaar kwikzeel lichtmot "
           "stippelmot satijnvlinder wapendrager waardjes roomvlek drietand hondsklauw batspade bonkspade mignon zilverdas kuikenvlaas "
           "kattevlaas avondrood aurelia zilveren maan mol".split())   # "mol" would match Molenstraat (mill) as a mole
SUFFIX = ["hol", "rand", "nest", "vlucht", "slag", "ekker", "graaf", "veld", "laantje", "beemden", "beemd", "haag", "hage", "donk", "laar",
          "laan", "lanen", "gang", "wissel", "spoor", "hof", "ven", "dijkje", "dijk", "boom", "bos", "akkers", "akker", "gaarde", "aar",
          "je", "tje", "s", "en", "e", "n"]
EXTRA_SUFFIX = ["horst", "burcht", "kuil", "kamp", "rode", "rijs", "berg", "beek", "singel", "pad", "weg", "plein", "erf", "dreef", "tuin",
                "kwartier", "weide", "weidenstraat", "land", "straat", "steeg", "hoek", "hoeve", "gors", "bult", "wei", "blok", "kolk", "poel",
                "kom", "gracht", "vaart", "lei", "dries", "wal", "kade", "stede", "plantsoen", "park", "veen", "moer", "mussen", "vogel",
                "vlinder", "blauwtje", "page", "spoor", "en", "er"]
GENERIC_DESCRIPTIONS = {None, "Vegetable or crop", "Animal", "Mammal or animal", "Flower", "Bird", "Mammal", "Plant", "Plant or tree",
                        "Tree or plant", "Herb", "Crop or fruit", "Crop", "Fruit", "Wild plant", "Bird or animal", "Fish", "Fish or bird",
                        "Tree or shrub", "Tree", "Wildflower", "Grass or plant", "Wild or water plant", "Tree, shrub or plant", "Butterfly",
                        "Grain crop", "Apple variety", "Herb or spice", "Flowering plant genus", "Flowering shrub genus",
                        "Silver-prefixed plant", "Bird or fish", "Shellfish or crab"}


@lru_cache(None)
def stems() -> dict:
    out = {}
    for line in read_lines(GLOBAL / "species.txt"):
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        en, la = v.split("|", 1)
        if k.lower() in SKIP or en.startswith("Wild plant (") or "moorland name" in en or "(butterfly name)" in en:
            continue
        out[k.lower()] = (en, la)
    return out


@lru_cache(None)
def streets() -> dict:
    out = {}
    for line in read_lines(GLOBAL / "species_streets.txt"):
        if "=" in line:
            s, v = line.split("=", 1)
            en, la, stem = v.split("|")
            out[s] = (en, la, stem)
    return out


def _find(label: str, suffixes) -> str | None:
    seen = set()

    def rec(x, d=0):
        if x in stems():
            return x
        if d > 3 or x in seen:
            return None
        seen.add(x)
        for s in suffixes:
            if x.endswith(s) and len(x) - len(s) >= 3:
                r = rec(x[:-len(s)], d + 1)
                if r:
                    return r
        return None

    return rec(label.lower().strip())


def _strip_article(s):
    return re.sub(r"^(de|het|'t|den|De|Het|Den)\s+", "", s).strip()


def find_stem(street: str) -> str | None:
    """The dictionary stem a street name denotes, or None. Tries the name, then with progressively
    more road/habitat words removed."""
    base = _strip_article(street).lower()
    cands = [base, _strip_article(core(street)).lower()]
    for c in list(cands):
        for s in EXTRA_SUFFIX:
            if c.endswith(s) and len(c) - len(s) >= 3:
                cands.append(c[:-len(s)])
    for c in cands:
        k = _find(c, SUFFIX)
        if k:
            return k
    return None


def describe(street: str) -> tuple[str, str, str] | None:
    """(English name, Latin name, Dutch stem) for a plant/animal street, or None."""
    if street in streets():
        return streets()[street]
    k = find_stem(street)
    if k:
        en, la = stems()[k]
        return en, la, k
    return None


def description(latin: str, stem: str) -> str:
    return f"{latin}; Dutch name '{stem}'"
