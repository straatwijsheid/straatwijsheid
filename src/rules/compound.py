"""Is a street name just an ordinary Dutch compound (akker + weg, kerk + straat...)?

Such a name carries no namesake, so a theme or surname guess attached to it is almost always wrong.
The vocabulary is knowledge/global/common_stems.txt."""
from __future__ import annotations

import re
from functools import lru_cache

from .base import GLOBAL, read_lines

ROAD = re.compile(r"(straat|laan|plein|weg|hof|pad|singel|kade|park|erf|dreef|steeg|plantsoen|baan)$")


@lru_cache(None)
def stems() -> frozenset:
    return frozenset(read_lines(GLOBAL / "common_stems.txt"))


def strip_road(name: str) -> str:
    n = ROAD.sub("", name.lower())
    return re.sub(r"[^a-zë']", "", n)


@lru_cache(None)
def _seg(word: str) -> bool:
    if not word:
        return True
    s = stems()
    return any(word[:i] in s and _seg(word[i:]) for i in range(len(word), 0, -1))


def is_compound(name: str) -> bool:
    return _seg(strip_road(name))


SURNAME_PREFIX = re.compile(r"^(van|von|de la|ten|ter|te)\b", re.I)
TITLES = re.compile(r"^(Burgemeester|Pastoor|Deken|Kapelaan|Monseigneur|Mgr\.?|Rector|Pater|Broeder|Dokter|Doctor|Dr\.|Meester|Mr\.|Prof\.?|"
                    r"Professor|Notaris|Minister|Generaal|Kolonel|Majoor|Luitenant|Kardinaal|Bisschop|Zuster|Wethouder|Commissaris|Ir\.|"
                    r"Ingenieur|Dominee|Ds\.|Schout|Schepen|Baron|Baronesse|Barones|Jonkheer|Jonkvrouw|Gebroeders|Gebr\.|Mater|Sint|St\.)\b")


def looks_like_person(name: str, first_names: set) -> bool:
    """A title, a first name + surname, or initials: the name itself says 'person'."""
    if TITLES.match(name):
        return True
    t = name.split()
    return len(t) >= 2 and (t[0] in first_names or bool(re.match(r"^([A-Z]\.){1,3}$", t[0])) or bool(re.match(r"^([A-Z]\.\s?){1,3}[A-Z]", name)))
