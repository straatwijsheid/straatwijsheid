"""Shared building blocks: the Override record, name helpers and the data Context."""
from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import config
from config import GLOBAL, KNOWLEDGE, ROOT

SOURCE = "claude_knowledge"   # provenance value used for every rule/hand-made override

ROAD_SUFFIXES = sorted(
    "straatje straat laan weg plein pad hofje hof dreef singel kade dijk plantsoen steeg erf hoeve park "
    "gaard vallei borch hoek weide plaats wal baan boulevard dam ring stede akker veld kamp".split(),
    key=len, reverse=True)
LOCAL_SUBCATEGORIES = ("local_landscape_feature", "local_landmark")


def core(name: str) -> str:
    """The street name without its leading article and trailing road word ('De Beukenlaan' -> 'Beuken')."""
    name = re.sub(r"^(De|Het|'t|Den)\s+", "", name)
    for suffix in ROAD_SUFFIXES:
        if name.lower().endswith(suffix) and len(name) - len(suffix) >= 3:
            return name[:-len(suffix)].rstrip(" -")
    return name


@dataclass
class Override:
    """One street's classification, in the shape the override layers store."""
    gemeente_code: str          # the CBS code (the key); `record()` adds the display name
    street: str
    category: str
    subcategory: Optional[str] = None
    entity_label: Optional[str] = None
    entity_description: Optional[str] = None
    confidence: float = 0.5
    source: str = SOURCE
    source_url: Optional[str] = None
    notes: Optional[str] = None
    rule: Optional[str] = field(default=None, compare=False)   # which rule produced it (not stored in the file)

    def record(self) -> dict:
        """The entry as a layer stores it: the gemeente's name for display, then its code (the key; overrides.write_layer keeps it out of the file)."""
        import gemeenten
        d = asdict(self)
        d.pop("rule")
        code = d.pop("gemeente_code")
        return {"gemeente": gemeenten.name_of(code), "gemeente_code": code, **d}

    @property
    def key(self):
        return (self.gemeente_code, self.street)

    @property
    def kind(self):
        return (self.category, self.subcategory)


def local_name(g, s, notes="Local field, road or place name; no namesake identified", rule=None):
    return Override(g, s, "place", "local_landscape_feature", None, None, 0.3, notes=notes, rule=rule)


def person(g, s, subcategory="other", label=None, confidence=0.3, notes=None, rule=None):
    if notes is None and not label:
        notes = "Named after a person who could not be identified"
    return Override(g, s, "person", subcategory, label, None, confidence, notes=notes, rule=rule)


def is_local(category, subcategory) -> bool:
    return category == "place" and subcategory in LOCAL_SUBCATEGORIES


def broad(category, subcategory) -> str:
    """person / place / local / thing: the level at which same-named streets should agree."""
    if category == "place":
        return "local" if subcategory in LOCAL_SUBCATEGORIES else "place"
    return category


@dataclass
class Context:
    """Everything the rules need to know about the dataset, loaded once.

    streets  -- list of {gemeente_code, name, buurt, wijk} (from build/raw/streets.geojson)
    final    -- list of streets_final.json records (the current classification)
    """
    streets: list
    final: list
    wikidata: dict = field(default_factory=dict)       # street -> (label, description)
    place_names: set = field(default_factory=set)      # lowercase gemeente/wijk/buurt names

    def __post_init__(self):
        self.buurt_of = {(s["gemeente_code"], s["name"]): s["buurt"] for s in self.streets}
        self.wijk_of = {(s["gemeente_code"], s["name"]): s.get("wijk") for s in self.streets}
        self.rows = {(r["gemeente_code"], r["street"]): r for r in self.final}
        self.by_name = collections.defaultdict(list)
        self.by_buurt = collections.defaultdict(list)
        self.by_wijk = collections.defaultdict(list)
        for r in self.final:
            self.by_name[r["street"]].append(r)
            self.by_buurt[(r["gemeente_code"], self.buurt_of.get((r["gemeente_code"], r["street"])))].append(r)
            self.by_wijk[(r["gemeente_code"], self.wijk_of.get((r["gemeente_code"], r["street"])))].append(r)

    def buurt(self, row):
        return (row["gemeente_code"], self.buurt_of.get((row["gemeente_code"], row["street"])))

    def wijk(self, row):
        return (row["gemeente_code"], self.wijk_of.get((row["gemeente_code"], row["street"])))

    def neighbours(self, row, trusted_only=True):
        """Other streets in the same buurt that carry a specific namesake from a trusted source."""
        from .evidence import TRUSTED
        return [y for y in self.by_buurt[self.buurt(row)]
                if y["street"] != row["street"] and (not trusted_only or (y["source"] in TRUSTED and y.get("entity_label")))]

    @classmethod
    def load(cls, root: Path = ROOT, final: list | None = None):
        """The data the rules look at. `final` replaces streets_final.json with rows computed in memory (the state below a rule's own layer)."""
        import geopandas as gpd
        gdf = gpd.read_file(config.RAW / "streets.geojson")[["gemeente_code", "name", "buurt", "wijk"]]
        streets = gdf.to_dict("records")
        if final is None:
            final = json.loads((config.ENRICHED / "streets_final.json").read_text())
        wd = {}
        for line in (config.ENRICHED / "all_streets_wikidata.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                wd[r["street"]] = (r.get("wikidata_label") or "", r.get("wikidata_description") or "")
        b = gpd.read_file(config.RAW / "buurten.geojson")
        names = {n.lower() for n in b["name"]} | {str(w).lower() for w in b["wijk"]} | {g.lower() for g in b.gemeente.unique()}
        return cls(streets, final, wd, names)


def read_lines(path: Path):
    return [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
