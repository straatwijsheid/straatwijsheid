"""Buurt naming themes derived from the streets' own classifications.

A buurt's theme is what the classified streets in it mostly are ("Mostly composers", "flowers, trees and plants"). The reconcile step uses
themes to settle weak Wikidata matches, so the order for a new gemeente is: reconcile -> themes -> reconcile (the second pass lets the
themes act). The original 394 themes of the earliest gemeenten were written by hand (`source: claude_reasoning`) and are never touched;
every other theme is derived here (`source: derived_from_street_classification`).

  python src/themes.py                 derive themes for every buurt that has none yet (any gemeente), writing buurt_themes_full.json
  python src/themes.py --gemeente X    restrict to gemeente X (repeatable)
  python src/themes.py --rebuild       re-derive ALL derived themes (hand-written ones stay); use after classifications changed a lot
"""
from __future__ import annotations

import config
import gemeenten
import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES = config.ENRICHED / "buurt_themes_full.json"
FINAL = config.ENRICHED / "streets_final.json"
LABELS = json.loads((config.GLOBAL / "theme_labels.json").read_text())
DERIVED, HAND = "derived_from_street_classification", "claude_reasoning"


def derive(buurt: dict, streets: list[str], fin: dict) -> dict:
    gemeente, code = buurt["gemeente"], buurt["gemeente_code"]
    items = [(fin[(code, s)], s) for s in streets if (code, s) in fin]
    cnt = collections.Counter()
    for x, _ in items:
        if x["category"] in ("person", "place", "thing"):
            cnt[(x["category"], x["subcategory"] or "other")] += 1
    n = sum(cnt.values())
    t = {"gemeente": gemeente, "gemeente_code": code, "buurt": buurt["name"], "wijk": buurt.get("wijk"), "source": DERIVED}
    if n < 3:
        t.update(theme="Too few named streets to identify a theme", category="unclear", confidence=0.3, example_streets=streets[:4])
        return t
    top = cnt.most_common(4)
    share = top[0][1] / n

    def examples(c):
        xs = [s for x, s in items if (x["category"], x["subcategory"] or "other") == c]
        named = [s for x, s in items if (x["category"], x["subcategory"] or "other") == c and x.get("entity_label")]
        return (named + [s for s in xs if s not in named])[:2]

    ex = []
    for c, _ in top[:3]:
        ex += examples(c)
    t["example_streets"] = ex[:5]
    label = lambda c: LABELS.get(c[1], c[1])
    if share >= 0.6:
        c = top[0][0]
        t.update(theme=f"Mostly {label(c)}", category=c[0], subcategory=c[1], confidence=round(min(0.85, 0.45 + 0.4 * share), 2))
    else:
        subs = [{"category": c[0], "subcategory": c[1], "share": round(v / n, 2)} for c, v in top]
        names = [label(c) for c, _ in top[:3]]
        t.update(theme=", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0], category="mixed", subthemes=subs,
                 confidence=round(0.4 + 0.3 * share, 2))
    return t


def with_codes(data: dict) -> dict:
    """Theme records written before gemeenten were keyed by code get their `gemeente_code` (by name, which must be unique)."""
    for t in data["buurten"]:
        if "gemeente_code" not in t:
            t["gemeente_code"] = gemeenten.code_of(t["gemeente"])
    return data


def run(only=None, rebuild=False) -> int:
    """`only`: restrict to these gemeenten (names or CBS codes)."""
    import geopandas as gpd
    fin = {(x["gemeente_code"], x["street"]): x for x in json.loads(FINAL.read_text())}
    sg = gpd.read_file(config.RAW / "streets.geojson")
    bg = gpd.read_file(config.RAW / "buurten.geojson")
    only = {gemeenten.code_of(g) for g in only} if only else None
    if only:
        sg, bg = sg[sg.gemeente_code.isin(only)], bg[bg.gemeente_code.isin(only)]
    by = collections.defaultdict(set)
    for g, b, name in zip(sg["gemeente_code"], sg["buurt"], sg["name"]):
        by[(g, b)].add(name)
    data = with_codes(json.loads(THEMES.read_text()))
    if rebuild:
        data["buurten"] = [t for t in data["buurten"] if t.get("source") != DERIVED or (only and t["gemeente_code"] not in only)]
    have = {(t["gemeente_code"], t["buurt"]) for t in data["buurten"]}
    added = collections.Counter()
    for _, b in bg.iterrows():
        if (b.gemeente_code, b["name"]) in have:
            continue
        t = derive({"gemeente": b.gemeente, "gemeente_code": b.gemeente_code, "name": b["name"], "wijk": b.wijk}, sorted(by.get((b.gemeente_code, b["name"]), [])), fin)
        data["buurten"].append(t)
        added[t["category"] if t["category"] in ("unclear", "mixed") else "single"] += 1
    THEMES.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"themes: added {sum(added.values())} ({dict(added)}); total {len(data['buurten'])}")
    return sum(added.values())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gemeente", action="append")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    run(a.gemeente, a.rebuild)
