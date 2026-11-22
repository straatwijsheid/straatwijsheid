"""Build the name-level candidate table.

For every street *name* (keyed by its core: the name without leading article and road word, lowercased) the table lists the
distinct interpretations ("candidates") that have any evidence, as (category, subcategory) kinds, each with:

  occurrences  where the name has already been classified as this kind: (gemeente, street, evidence tier, label)
  rule hits    knowledge rules that say this name denotes this kind (vocabulary, species, famous people, place, ordinary word...)
  wikidata     what Wikidata matched the name to
  labels       the specific namesakes seen for this kind

Evidence is *mass*: an occurrence weighs by its evidence tier, a rule hit or a strong Wikidata match counts as two tier-2
occurrences. A candidate's prior is its share of the name's total mass."""
from __future__ import annotations

import config
import collections
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rules import directional, species, surnames, vocabulary
from rules.base import ROOT, Context, core, is_local, LOCAL_SUBCATEGORIES
from rules.compound import is_compound
from tiers import evidence_tier

Kind = tuple[str, Optional[str]]
LOCAL: Kind = ("place", "local_landscape_feature")
TIER_WEIGHT = {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.25, 5: 0.15}
RULE_MASS = 1.6                    # a rule hit ~ two tier-2 occurrences
OSM_OWN_MASS, OSM_OTHER_MASS = 6.0, 1.0   # OSM etymology for this very street dominates; for the same name elsewhere it is a modest prior
WIKIDATA_MASS = {"strong": 1.6, "weak": 0.3, "surname": 0.5, "thing": 0.3}
PLACE_DESC = re.compile(r"\b(commune|municipality|town|city|province|region|island|country|river|village|capital|department|county|lake|mountain|hamlet|district)\b", re.I)
BIO_DESC = re.compile(r"\b(species|genus|bird|insect|fish|mammal|plant|flower|tree|butterfly|dragonfly|beetle|fungus|shrub|herb)\b", re.I)
PERSON_DESC = re.compile(r"\b(born|painter|writer|poet|composer|politician|statesman|scientist|physician|general|admiral|king|queen|prince|saint|architect|explorer)\b", re.I)


def name_key(street: str) -> str:
    """The identity of a name: lowercase core without article/road word ('De Beukenlaan' and 'Beukenstraat' share 'beuken')."""
    return re.sub(r"[\s\-]+", " ", core(street).lower()).strip()


def kind_of(row) -> Kind | None:
    c = row.get("category")
    if c not in ("person", "place", "thing"):
        return None
    return (c, row.get("subcategory"))


@dataclass
class Candidate:
    kind: Kind
    occurrences: list = field(default_factory=list)     # (gemeente, street, tier, label)
    rules: dict = field(default_factory=dict)            # rule name -> label (or None)
    wikidata: list = field(default_factory=list)         # (strength class, label, description)
    osm: list = field(default_factory=list)              # (gemeente, street, label): OpenStreetMap name:etymology evidence

    def mass(self, exclude=None, gemeente=None, use_wikidata=True, use_osm=True, own=None) -> float:
        m = 0.0
        for g, s, tier, _ in self.occurrences:
            if exclude is not None and (g, s) == exclude:
                continue
            if gemeente is not None and g == gemeente:
                continue
            m += TIER_WEIGHT[tier]
        m += RULE_MASS * len(self.rules)
        if use_wikidata:
            m += sum(WIKIDATA_MASS[k] for k, _, _ in self.wikidata)
        if use_osm:
            for g, s, _ in self.osm:
                if gemeente is not None and g == gemeente and (g, s) != own:
                    continue
                m += OSM_OWN_MASS if (g, s) == own else OSM_OTHER_MASS
        return m

    def labels(self, exclude=None, gemeente=None, own=None) -> collections.Counter:
        c = collections.Counter()
        for g, s, tier, label in self.occurrences:
            if label and tier <= 3 and (exclude is None or (g, s) != exclude) and (gemeente is None or g != gemeente):
                c[label] += TIER_WEIGHT[tier]
        for label in self.rules.values():
            if label:
                c[label] += RULE_MASS
        for g, s, label in self.osm:
            if label and not (gemeente is not None and g == gemeente and (g, s) != own):
                c[label] += OSM_OWN_MASS if (g, s) == own else OSM_OTHER_MASS
        return c


@dataclass
class NameEntry:
    key: str
    streets: list = field(default_factory=list)          # (gemeente, street)
    candidates: dict = field(default_factory=dict)       # Kind -> Candidate

    def cand(self, kind: Kind) -> Candidate:
        if kind not in self.candidates:
            self.candidates[kind] = Candidate(kind)
        return self.candidates[kind]


def load_wikidata_records(root: Path = ROOT) -> dict:
    out = {}
    for line in (config.ENRICHED / "all_streets_wikidata.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["street"]] = r
    return out


def _wikidata_candidate(rec):
    """(kind, strength class, label, description) for one Wikidata cache record, or None."""
    src, cat, conf = rec.get("source"), rec.get("category"), rec.get("confidence") or 0
    label, desc = rec.get("wikidata_label"), rec.get("wikidata_description") or ""
    if src == "wikidata" and cat in ("person", "place", "thing") and conf >= 0.7:
        return (cat, rec.get("subcategory")), "strong", label, desc
    if src == "wikidata_surname_only":
        return ("person", "unspecified_individual"), "surname", label, desc
    if src == "wikidata_thing_match":
        return ("thing", rec.get("subcategory")), "thing", label, desc
    if re.search(r"^(street|road) in|neighbourhood in", desc, re.I):
        return None
    if PLACE_DESC.search(desc):
        return ("place", None), "weak", label, desc
    if BIO_DESC.search(desc):
        return ("thing", None), "weak", label, desc
    if PERSON_DESC.search(desc):
        return ("person", None), "weak", label, desc
    return None


def build_table(ctx: Context, wikidata: dict | None = None, rules: bool = True, osm: list | None = None) -> dict[str, NameEntry]:
    famous = surnames.famous()
    table: dict[str, NameEntry] = {}
    for row in ctx.final:
        key = name_key(row["street"])
        e = table.setdefault(key, NameEntry(key))
        e.streets.append((row["gemeente"], row["street"]))
        k = kind_of(row)
        if k is not None:
            tier = evidence_tier(row)
            label = row.get("entity_label") or None
            e.cand(LOCAL if is_local(*k) and k[1] == "local_landscape_feature" else k).occurrences.append((row["gemeente"], row["street"], tier, label))
    for key, e in table.items():
        names = sorted({s for _, s in e.streets})
        # --- Wikidata ---
        if wikidata:
            for s in names:
                rec = wikidata.get(s)
                hit = _wikidata_candidate(rec) if rec else None
                if hit:
                    kind, strength, label, desc = hit
                    cand = e.cand(kind)
                    if (strength, label, desc) not in cand.wikidata:
                        cand.wikidata.append((strength, label, desc))
        # --- knowledge rules (a function of the name only) ---
        if rules:
            for s in names:
                v = vocabulary.classify("", s)
                if v:
                    e.cand((v.category, v.subcategory)).rules["vocabulary"] = v.entity_label
                sp = species.describe(s)
                if sp and not v:
                    e.cand(("thing", None)).rules["species"] = sp[0]
                if s in famous:
                    sub, label = famous[s]
                    e.cand(("person", sub)).rules["famous_people"] = label
                d = directional.classify("", s, ctx.place_names)
                if d:
                    e.cand((d.category, d.subcategory)).rules["directional_road"] = d.entity_label
                t = vocabulary.classify_titles("", s)
                if t:
                    e.cand((t.category, t.subcategory)).rules["title_pattern"] = None
            if key in ctx.place_names:
                e.cand(("place", "dutch_town")).rules["place_name"] = key.title()
            if all(is_compound(s) for s in names):
                e.cand(LOCAL).rules["ordinary_compound"] = None
    for rec in osm or []:
        items = [i for i in rec.get("items", []) if i.get("category")]
        if not items or len({i["category"] for i in items}) > 1:
            continue
        e = table.get(name_key(rec["street"]))
        if e is not None:
            e.cand((items[0]["category"], items[0]["subcategory"])).osm.append((rec["gemeente"], rec["street"], items[0].get("label")))
    return table


def table_summary(table) -> dict:
    n = len(table)
    multi = sum(1 for e in table.values() if len(e.candidates) > 1)
    return {"names": n, "streets": sum(len(e.streets) for e in table.values()), "names_with_several_candidates": multi,
            "candidates": sum(len(e.candidates) for e in table.values())}
