"""Cross-checks that make the dataset consistent with itself.

Street names repeat across gemeenten, and different gemeenten were classified at different depths,
so the same name can carry different classifications. Same-name agreement is evidence, but a
different reading is legitimate when the street's own buurt supports it (Margrietstraat is a flower
in two flower buurten and a princess elsewhere) -- so each rule checks buurt support first."""
from __future__ import annotations

import collections
import json
import re
from functools import lru_cache

from .base import KNOWLEDGE, Context, Override, broad, local_name, person, is_local, read_lines
from .compound import is_compound, looks_like_person, strip_road, SURNAME_PREFIX
from .evidence import THEME_SOURCES, TRUSTED
from . import species

# ----------------------------------------------------------------------------------------------
# 1. same-name harmonisation
# ----------------------------------------------------------------------------------------------
HARMONISE = "same_name_harmonise"


def _support(ctx: Context, row) -> int:
    kind = (row["category"], row.get("subcategory"))
    return sum(1 for y in ctx.neighbours(row) if (y["category"], y.get("subcategory")) == kind)


def harmonise_same_name(ctx: Context, min_occurrences=4, majority=0.7) -> list[Override]:
    """A name that is clearly one thing in >=70% of its places, but different in a place where the buurt
    gives no support for the different reading, takes the majority classification. Person majorities are
    left alone (the namesake may differ between gemeenten; the buurt must decide, see person_consensus)."""
    out = []
    replaceable = THEME_SOURCES | {"wikidata_thing_match", "wikidata", "claude_knowledge"}
    for name, rows in ctx.by_name.items():
        if len(rows) < min_occurrences:
            continue
        counts = collections.Counter(broad(r["category"], r.get("subcategory")) for r in rows)
        top, k = counts.most_common(1)[0]
        if k == len(rows) or k / len(rows) < majority or top == "person":
            continue
        maj = [r for r in rows if broad(r["category"], r.get("subcategory")) == top and r["source"] in TRUSTED]
        if not maj:
            continue
        kind = collections.Counter((r["category"], r.get("subcategory")) for r in maj).most_common(1)[0][0]
        label = collections.Counter((r.get("entity_label"), r.get("entity_description")) for r in maj if (r["category"], r.get("subcategory")) == kind).most_common(1)[0][0]
        for r in rows:
            if broad(r["category"], r.get("subcategory")) == top or r["source"] not in replaceable or _support(ctx, r) >= 3:
                continue
            if r["source"] == "claude_knowledge" and r["category"] == "person":
                continue
            out.append(Override(r["gemeente"], name, kind[0], kind[1], label[0], label[1], 0.4,
                                notes=f"Harmonised with the same-named street elsewhere ({k}/{len(rows)} agree on '{top}'); the street's own buurt gave no support for a different reading",
                                rule=HARMONISE))
    return out


# ----------------------------------------------------------------------------------------------
# 2. person consensus (the buurt decides which person)
# ----------------------------------------------------------------------------------------------
PERSON = "person_consensus"
NEVER_PERSON = {"Handelsweg", "Pagestraat", "Vendelier", "Gildestraat", "Nonnenpad"}   # ordinary words, not people


@lru_cache(None)
def person_labels() -> dict:
    return json.loads((KNOWLEDGE / "person_labels.json").read_text())


def person_consensus(ctx: Context, majority=0.7) -> list[Override]:
    """An unidentified street takes the person-kind that same-named streets elsewhere have, but only where its own
    buurt has >=2 streets named after the same kind of person. Names shared by many people (Willem, Hendrik...) assert
    only the kind, via the label table; distinctive surnames keep a specific name."""
    informative = collections.defaultdict(list)
    for r in ctx.final:
        if r["source"] in TRUSTED - {"wikidata_surname_only"} and r["category"] == "person" and r.get("entity_label") and r.get("subcategory") not in ("other", "unspecified_individual"):
            informative[r["street"]].append(r)
    out = []
    for r in ctx.final:
        s = r["street"]
        unidentified = (r["source"] == "wikidata_surname_only" and r.get("subcategory") == "unspecified_individual") or \
                       (r["category"] == "place" and r.get("subcategory") == "local_landscape_feature" and "no namesake" in (r.get("notes") or ""))
        if not unidentified or s in NEVER_PERSON or s not in informative:
            continue
        kinds = collections.Counter(y["subcategory"] for y in informative[s])
        sub, n = kinds.most_common(1)[0]
        if n / len(informative[s]) < majority:
            continue
        support = sum(1 for y in ctx.neighbours(r) if y["category"] == "person" and y.get("subcategory") == sub)
        if support >= 2 and s in person_labels():
            out.append(Override(r["gemeente"], s, "person", sub, person_labels()[s][1],
                                f"Chosen because the buurt '{ctx.buurt(r)[1]}' has {support} other streets named after the same kind of person; other gemeenten' same-named streets agree",
                                0.5, notes="Buurt-theme supported classification", rule=PERSON))
    return out


# ----------------------------------------------------------------------------------------------
# 3. labels forced onto a street by its buurt's theme
# ----------------------------------------------------------------------------------------------
THEME = "theme_forced_name_fit"
PLACE_RE = re.compile(r"\b(commune|municipality|town|city|province|region|island|country|river|village|capital|department|county|canton|state of|lake|mountain|peninsula|abbey|castle|estate|manor|hamlet|district)\b", re.I)
BIO_RE = re.compile(r"\b(species|genus|family of|bird|insect|fish|mammal|plant|flower|tree|butterfly|dragonfly|beetle|moth|fungus|shrub|herb|animal|crop|cereal|fruit|vegetable)\b", re.I)
FIC_RE = re.compile(r"\b(opera|novel|film|character|play|poem|fairy|legend|fictional|musical|comic|story|epic|romance|tale|operetta)\b", re.I)
KIND_RE = {"vessel_type": re.compile(r"\b(ship|vessel|boat|sailing)\b", re.I), "instrument": re.compile(r"instrument", re.I),
           "astronomy": re.compile(r"\b(star|constellation|planet|galaxy|comet|asteroid|moon)\b", re.I), "mineral": re.compile(r"\b(mineral|gemstone|rock|metal|ore)\b", re.I),
           "currency": re.compile(r"\b(coin|currency)\b", re.I)}
ANIMAL_WORD = re.compile(r"vlinder|vogel|bloem|vleermuis|spreeuw|mees|fazant|kuifeend|reiger|libel|kever|mot$|bij$|wesp|mug|vlieg|spin$|worm|slak|kikker|pad$|salamander|eekhoorn|egel|muis|marter|hagedis|slang", re.I)
PLACE_KINDS = ("foreign_town", "dutch_town", "dutch_region", "country", "castle_estate", "river", "lake", "alpine_geography", "biblical", "estate_feature")
STREET_DESC = re.compile(r"^street in|^road in|neighbourhood in|^neighborhood", re.I)
FIRST_NAME_PREFIX = "Gebroeders"


BASE_FIRST_NAMES = set("""Jan Piet Pieter Willem Hendrik Hendrikus Johan Johannes Cornelis Gerard Gerardus Anton Antoon Frans Karel Jozef Josef Jacobus
Jacob Dirk Adriaan Adrianus Martinus Marinus Theodorus Theo Peter Paulus Petrus Joannes Louis Lambertus Nicolaas Antonius Wilhelmus Franciscus
Henri Henricus Hubertus Albertus Arnold Bernard Bernardus Gijsbert Harry Hans Kees Cor Wim Toon Ton Sjef Sjeng Maria Anna Johanna Catharina
Elisabeth Margaretha Wilhelmina Geertruida Hendrika Cornelia Marius Milla Hugo Erik Ed Rob Ruud Marcel Jef Jos Leo Max Wout Joris Floris Bart
Bas Gijs Ger Rien Tinus Nel Mien Door Truus Riet Ans Mia Lies Tine Greet""".split())
NOT_A_FIRST_NAME = {"De", "Het", "Den", "Van", "Von", "Ten", "Ter", "Te", "Sint", "St.", "Oude", "Nieuwe", "Kleine", "Groote", "Grote", "Lange", "Korte", "Hoge"}


def _first_names(ctx: Context, learned: bool) -> set:
    """First names for recognising 'Jan X' streets as persons. `learned` adds first tokens seen >=2 times in already identified
    person streets (safe for deciding whether to KEEP a person label, too loose for CONVERTING a label to a person)."""
    from .vocabulary import vocab
    fn = BASE_FIRST_NAMES | {n.capitalize() for n in vocab()["FIRST_NAMES"]}
    if learned:
        counts = collections.Counter(r["street"].split()[0] for r in ctx.final if r["category"] == "person" and r["source"] in ("wikidata", "claude_knowledge", "title_heuristic")
                                     and len(r["street"].split()) >= 2 and r["street"].split()[0][:1].isupper())
        fn |= {k for k, v in counts.items() if v >= 2}
    return fn - NOT_A_FIRST_NAME


def _generic_words(ctx: Context) -> set:
    """Stripped names that occur in >=3 gemeenten, mostly as local names: ordinary words, not namesakes."""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in ctx.final:
        by[strip_road(r["street"])][r["gemeente"]].append(r)
    voc = set()
    for w, gm in by.items():
        if len(gm) >= 3:
            locs = sum(1 for g, L in gm.items() if any(is_local(y["category"], y.get("subcategory")) for y in L if y["source"] not in THEME_SOURCES))
            if locs >= len(gm) / 2:
                voc.add(w)
    return voc


def theme_forced(ctx: Context) -> list[Override]:
    """A label whose only basis is the buurt's naming theme must also be backed by the name itself. Person labels need a
    title/first-name/initials pattern or a name that is not an ordinary word; plant/animal labels need a species word; place labels need
    a Wikidata place description, a same-named place elsewhere, or >=3 same-kind neighbours; other kinds need same-name support or a
    fitting Wikidata description. Labels failing this become local names; names that are clearly persons become persons."""
    fn_base, fn_learned, generic, out = _first_names(ctx, False), _first_names(ctx, True), _generic_words(ctx), []
    for x in ctx.final:
        if x["source"] not in THEME_SOURCES or is_local(x["category"], x.get("subcategory")):
            continue
        n, g, c, sub = x["street"], x["gemeente"], x["category"], x.get("subcategory") or ""
        others = [y for y in ctx.by_name[n] if y is not x and (y["source"] in TRUSTED)]
        same = [y for y in others if (y["category"], y.get("subcategory")) == (c, x.get("subcategory"))]
        majority_local = len(others) >= 2 and sum(1 for y in others if broad(y["category"], y.get("subcategory")) == "local") > len(others) / 2
        label, desc = ctx.wikidata.get(n, ("", ""))
        street_desc = bool(STREET_DESC.search(desc))
        compound = is_compound(n)
        if c != "person" and looks_like_person(n, fn_base):
            sub2 = "mayor_local" if n.startswith("Burgemeester") else "religious" if re.match(r"^(Pastoor|Deken|Kapelaan|Monseigneur|Mgr|Rector|Pater|Broeder|Kardinaal|Bisschop|Zuster|Mater|Sint|St)", n) else "other"
            out.append(person(g, n, sub2, notes=f"Name has a title/first-name pattern, so it is a person; the buurt theme had forced '{c}/{x.get('subcategory')}'; individual not identified", rule=THEME))
            continue
        if c == "person":
            ok = looks_like_person(n, fn_learned) or bool(SURNAME_PREFIX.match(n)) or (not compound and not majority_local)
        elif sub.startswith(("flora", "fauna")):
            ok = bool(species.describe(n)) or bool(ANIMAL_WORD.search(n)) or bool(same) or (bool(BIO_RE.search(desc)) and not street_desc)
        elif c == "place":
            ok = bool(same) or (bool(PLACE_RE.search(desc)) and not street_desc and sub in PLACE_KINDS) or strip_road(n) in ctx.place_names or n.lower() in ctx.place_names \
                 or bool(re.search(r"(se|sche)(weg|straat|dijk|laan|baan)$", n))
        else:
            ok = (bool(same) and not majority_local) or (sub == "fiction_title_or_motif" and bool(FIC_RE.search(desc)) and not street_desc) \
                 or (sub in KIND_RE and bool(KIND_RE[sub].search(desc)) and not street_desc)
        if not ok and c in ("place", "thing") and (sub.startswith(("flora", "fauna")) or sub in PLACE_KINDS):
            neighbours_same = sum(1 for y in ctx.neighbours(x) if (y["category"], y.get("subcategory")) == (c, x.get("subcategory")))
            if neighbours_same >= 3 and not compound and strip_road(n) not in generic and not majority_local and not street_desc:
                ok = True
        if not ok:
            out.append(local_name(g, n, f"Standardised rule: the label '{c}/{x.get('subcategory')}' came from the buurt theme alone and the street name itself does not indicate it; no namesake identified", THEME))
    return out
