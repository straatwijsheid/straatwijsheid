"""What changed in OpenStreetMap's etymology-related tags between two fetches.

Compares the previous archived snapshot of `osm_etymology_ways` with the newly fetched one, per OSM way, on the tags that carry a namesake, and writes
  output/OSM_CHANGES.md          the changes grouped by gemeente and street (newest fetch only)
  enriched/osm_changes.jsonl     one line per changed way, appended on every refresh (fetched_at, way, old/new tags)
so edits made in OSM (yours or anyone's) show up instead of being found by accident.
"""
from __future__ import annotations

import collections
import json

import config

TAGS = ("name", "name:etymology:wikidata", "name:etymology", "name:etymology:wikipedia", "wikidata", "subject:wikidata", "highway")


def relevant(tags: dict) -> dict:
    return {k: tags[k] for k in TAGS if k in tags}


def diff_ways(old: list[dict], new: list[dict]) -> list[dict]:
    """Per-way changes: added (a way that carries etymology-related tags that the old snapshot lacked), removed, changed."""
    o = {e["id"]: e for e in old}
    n = {e["id"]: e for e in new}
    out = []
    for i, e in n.items():
        new_t = relevant(e.get("tags", {}))
        if i not in o:
            out.append({"way": i, "change": "added", "name": new_t.get("name"), "old": {}, "new": new_t, "center": e.get("center")})
        else:
            old_t = relevant(o[i].get("tags", {}))
            if old_t != new_t:
                out.append({"way": i, "change": "changed", "name": new_t.get("name") or old_t.get("name"), "old": old_t, "new": new_t, "center": e.get("center")})
    for i, e in o.items():
        if i not in n:
            old_t = relevant(e.get("tags", {}))
            out.append({"way": i, "change": "removed", "name": old_t.get("name"), "old": old_t, "new": {}, "center": e.get("center")})
    return out


def _gemeente(changes: list[dict]) -> None:
    import geopandas as gpd
    from shapely.geometry import Point
    pts = [(i, c["center"]) for i, c in enumerate(changes) if c.get("center")]
    if not pts:
        return
    b = gpd.read_file(config.RAW / "buurten.geojson")
    area = b.dissolve(by="gemeente").reset_index()[["gemeente", "geometry"]].to_crs("EPSG:4326")
    g = gpd.GeoDataFrame({"i": [i for i, _ in pts]}, geometry=[Point(c["lon"], c["lat"]) for _, c in pts], crs="EPSG:4326")
    j = gpd.sjoin(g, area, how="left", predicate="within")
    j = j[~j.index.duplicated()]
    for i, gem in zip(j["i"], j["gemeente"]):
        changes[i]["gemeente"] = gem if isinstance(gem, str) else None


def write_report(changes: list[dict], fetched_at: str, previous_at: str | None) -> None:
    _gemeente(changes)
    for c in changes:
        c.setdefault("gemeente", None)
    config.ENRICHED.mkdir(parents=True, exist_ok=True)
    with (config.ENRICHED / "osm_changes.jsonl").open("a") as f:
        for c in changes:
            f.write(json.dumps({"fetched_at": fetched_at, "previous": previous_at, **c}, ensure_ascii=False) + "\n")
    tag = lambda t: t.get("name:etymology:wikidata") or t.get("wikidata") or t.get("name:etymology") or "-"
    by = collections.defaultdict(list)
    for c in changes:
        by[(c["gemeente"] or "(outside our gemeenten)", c["name"] or "(unnamed)")].append(c)
    counts = collections.Counter(c["change"] for c in changes)
    lines = [f"# OSM etymology changes", "", f"Fetched {fetched_at}; compared with the snapshot of {previous_at or 'none (first snapshot)'}.", "",
             f"{len(changes)} way changes in {len(by)} streets: " + ", ".join(f"{v} {k}" for k, v in counts.items()), ""]
    for (gem, name), cs in sorted(by.items()):
        k = collections.Counter(c["change"] for c in cs)
        olds = sorted({tag(c["old"]) for c in cs} - {"-"})
        news = sorted({tag(c["new"]) for c in cs} - {"-"})
        lines.append(f"- **{name}** ({gem}): {', '.join(f'{v} {x}' for x, v in k.items())}; etymology/wikidata {', '.join(olds) or '-'} -> {', '.join(news) or '-'}; "
                     f"ways {', '.join(str(c['way']) for c in cs[:6])}{' ...' if len(cs) > 6 else ''}")
    config.OUTPUT.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT / "OSM_CHANGES.md").write_text("\n".join(lines) + "\n")
    print(f"{len(changes)} way changes in {len(by)} streets ({dict(counts)}) -> {config.rel(config.OUTPUT / 'OSM_CHANGES.md')}")
