"""Which streets touch which: the street-level neighbourhood.

Kooloos (2013, on street naming in Holland and Noord-Brabant 1859-1939) defines a naming *theme* as "minimal four streets which
interconnect to each other and all relate to the same specific subject". A CBS buurt is an administrative unit, not a naming unit:
Dongen's Hoge Akker holds three themes (writers, architects, WWII Allied leaders). The streets a street actually touches are a
sharper context than its buurt, so the resolver can use them as well.

Two streets are adjacent when their geometries come within ADJACENT_M metres (same gemeente). Cached in build/names/adjacency.json."""
from __future__ import annotations

import config
import collections
import json

import geopandas as gpd

from rules.base import ROOT

ADJACENT_M = 8.0
CACHE = config.NAMES / "adjacency.json"


def build(root=ROOT, distance=ADJACENT_M) -> dict:
    """{(gemeente, street): [adjacent street names]}"""
    streets = gpd.read_file(config.RAW / "streets.geojson")[["gemeente", "name", "geometry"]]
    adj = collections.defaultdict(set)
    for g, d in streets.groupby("gemeente"):
        d = d.reset_index(drop=True).to_crs(d.estimate_utm_crs())
        left = d.assign(geometry=d.geometry.buffer(distance))
        sj = gpd.sjoin(left, d[["name", "geometry"]].rename(columns={"name": "nb"}), predicate="intersects")
        for a, b in zip(sj["name"], sj["nb"]):
            if a != b:
                adj[(g, a)].add(b)
    return {k: sorted(v) for k, v in adj.items()}


def load(rebuild=False) -> dict:
    if CACHE.exists() and not rebuild:
        raw = json.loads(CACHE.read_text())
        return {tuple(k.split("\t")): v for k, v in raw.items()}
    adj = build()
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({"\t".join(k): v for k, v in adj.items()}, ensure_ascii=False))
    return adj


def themes(adj: dict, kinds: dict, min_size=4):
    """Connected clusters of same-kind streets (Kooloos's themes). kinds: {(gemeente, street): kind or None}."""
    seen, out = set(), []
    for key, k in kinds.items():
        if k is None or key in seen:
            continue
        stack, comp = [key], []
        seen.add(key)
        while stack:
            a = stack.pop()
            comp.append(a)
            for nb in adj.get(a, ()):
                nk = (a[0], nb)
                if nk not in seen and kinds.get(nk) == k:
                    seen.add(nk)
                    stack.append(nk)
        if len(comp) >= min_size:
            out.append((k, comp))
    return out
