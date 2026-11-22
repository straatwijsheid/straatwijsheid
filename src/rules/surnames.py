"""Streets matched only to a Wikidata 'family name' entry (person / unspecified_individual).

Wikidata has family-name entries for ordinary words (Molen, Park, Heuvel), so that match alone is
no evidence of a person. Each such street is resolved by: is it an ordinary word (-> local name);
is it a recognised famous surname whose street's buurt backs that kind of person (-> named person);
otherwise does the buurt's person-ness decide (-> kind of person / local name / left alone)."""
from __future__ import annotations

import collections
import re

from .base import GLOBAL, Context, Override, local_name, person, read_lines
from .compound import is_compound, SURNAME_PREFIX
from .evidence import TRUSTED

RULE = "bare_surname"
KIND = {"mus": "musician_composer", "wri": "writer_poet", "art": "artist_visual", "pol": "politician_statesman", "mon": "monarch_statesman",
        "nav": "military_naval_or_politician", "mil": "military", "sci": "scientist", "exp": "explorer", "avi": "aviation_pioneer",
        "arc": "architect_or_historian", "law": "legal_scholar", "rel": "religious"}
# politicians, soldiers and admirals share a naming theme (war leaders, statesmen): support is counted across the group
GROUP = {"politician_statesman": "leaders", "military": "leaders", "military_naval_or_politician": "leaders"}
NOT_COMMON = {"Bosboomstraat", "Dijksterhuisstraat", "Kesselsstraat", "Koebergstraat", "Ringersweg", "Poelsstraat", "Sester", "Heiberg", "Velder",
              "Noordenbos", "Geerde", "Heikestraat", "Stulp", "Spadestraat"}   # look like compounds but are surnames
SPURIOUS = "Ordinary Dutch word, not a surname (the Wikidata 'family name' match was spurious); no namesake identified"


def _grp(sub):
    return GROUP.get(sub, sub)


def famous() -> dict:
    out = {}
    for line in read_lines(GLOBAL / "famous_people.txt"):
        s, code, label = line.split("|")
        out[s] = (KIND[code], label)
    return out


def common_words() -> set:
    return set(read_lines(GLOBAL / "common_words.txt")) | (set(read_lines(GLOBAL / "common_compounds.txt")) - NOT_COMMON)


def is_target(row) -> bool:
    return row["source"] == "wikidata_surname_only" and row.get("subcategory") == "unspecified_individual"


def _context(ctx: Context, row):
    nb = [y for y in ctx.neighbours(row) if y["source"] != "wikidata_surname_only"]
    n = len(nb)
    p = sum(1 for y in nb if y["category"] == "person")
    kinds = collections.Counter(y["subcategory"] for y in nb if y["category"] == "person" and y.get("subcategory") not in ("other", "unspecified_individual"))
    return n, (p / n if n else None), kinds


def resolve(ctx: Context) -> list[Override]:
    fam, common = famous(), common_words() - set(famous())
    targets = [r for r in ctx.final if is_target(r)]
    # recognised surnames in one buurt back each other (Dongen's Hoge Akker: Aalto, Berlage, Gropius, Horta... all architects)
    mutual = collections.Counter((ctx.buurt(r), _grp(fam[r["street"]][0])) for r in targets if r["street"] in fam)
    out = []
    for r in targets:
        g, s = r["gemeente_code"], r["street"]
        if (s in common or (is_compound(s) and s not in NOT_COMMON and not SURNAME_PREFIX.match(s))) and s not in fam:
            out.append(local_name(g, s, SPURIOUS, RULE))
            continue
        n, share, kinds = _context(ctx, r)
        buurt = ctx.buurt(r)
        if s in fam:
            sub, label = fam[s]
            support = sum(v for k, v in kinds.items() if _grp(k) == _grp(sub)) + mutual[(buurt, _grp(sub))] - 1
            if support >= 2:
                out.append(Override(g, s, "person", sub, label, f"Identified from the name; the buurt '{buurt[1]}' has {support} other streets named after the same kind of person",
                                    0.5, notes="Buurt-theme supported classification", rule=RULE))
            continue
        if n >= 4 and share is not None and share >= 0.6 and kinds and kinds.most_common(1)[0][1] >= 2:
            sub = kinds.most_common(1)[0][0]
            out.append(Override(g, s, "person", sub, None, f"Probably named after a person; kind inferred from the buurt '{buurt[1]}', where {kinds[sub]} other streets are named after the same kind of person",
                                0.3, notes="Kind of person inferred from buurt theme; individual not identified", rule=RULE))
        elif n >= 4 and share is not None and share < 0.3 and not re.match(r"^(van|von|de la|ten|ter|te|de)\b", s, re.I):
            out.append(local_name(g, s, "Single word in a buurt where few streets are named after people; likely a place/field name rather than a surname; no namesake identified", RULE))
    return out
