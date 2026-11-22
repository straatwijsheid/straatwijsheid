"""Every named street-like way in OpenStreetMap inside an outline, as one row per street name.

Replaces the osmnx "drive network" fetch, which silently dropped parking aisles and driveways, pedestrian streets, footways/cycleways/tracks,
and short disconnected streets (15% of the named OSM ways in Noord-Brabant; see TODO.md). Here every `highway=*` way with a `name` counts, except
types that are not streets (see EXCLUDED); each street keeps its `highway` type(s) so later steps can filter or style by them.

  highway      the most street-like type among the street's ways (see RANK)
  highway_all  every type seen, ';'-separated
  way_class    street | path | planned   (street = roads and pedestrian streets; path = footway/cycleway/track/path/bridleway; planned = under construction)
"""
from __future__ import annotations

import config
import time

import geopandas as gpd
import requests
from shapely.geometry import LineString

OVERPASS = config.OVERPASS_URL
UA = {"User-Agent": "street-etymology-research/0.1 (open-data research script)"}   # generic: no personal details
EXCLUDED = {"proposed", "platform", "bus_stop", "services", "rest_area", "raceway", "corridor", "busway", "elevator", "emergency_bay", "give_way", "crossing"}
RANK = ["residential", "living_street", "unclassified", "tertiary", "secondary", "primary", "trunk", "motorway", "pedestrian", "service", "road",
        "tertiary_link", "secondary_link", "primary_link", "trunk_link", "motorway_link", "track", "cycleway", "footway", "path", "bridleway", "steps", "construction"]
PATHS = {"track", "cycleway", "footway", "path", "bridleway", "steps"}


def way_class(highway: str) -> str:
    return "planned" if highway == "construction" else "path" if highway in PATHS else "street"


def fetch_ways(bbox, retries=6) -> list[dict]:
    """Named highway ways with geometry inside a (south, west, north, east) box. Overpass is often busy: retries with growing pauses."""
    s, w, n, e = bbox
    # (area.nl): only ways inside the Netherlands. CBS outlines of Baarle-Nassau contain the Belgian Baarle-Hertog enclaves, and border gemeenten
    # reach into Belgium/Germany in the bbox; without this filter those streets would be counted as Dutch.
    q = f'[out:json][timeout:300];area["ISO3166-1"="NL"]->.nl;way["highway"]["name"]({s},{w},{n},{e})(area.nl);out tags geom;'
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(OVERPASS, data={"data": q}, headers=UA, timeout=360)
            if r.status_code == 200:
                return r.json()["elements"]
            err = f"HTTP {r.status_code}"
        except requests.RequestException as ex:
            err = str(ex)[:80]
        print(f"  overpass attempt {attempt}/{retries} failed ({err})")
        time.sleep(15 * attempt)
    raise RuntimeError("Overpass unavailable")


def streets_from_ways(ways: list[dict], area) -> gpd.GeoDataFrame:
    """One row per street name: the merged geometry of the ways whose midpoint lies inside `area`, plus highway/way_class."""
    rows = {}
    for w in ways:
        tags = w.get("tags", {})
        hw, name = tags.get("highway"), tags.get("name")
        if not name or hw in EXCLUDED or len(w.get("geometry", [])) < 2:
            continue
        line = LineString([(p["lon"], p["lat"]) for p in w["geometry"]])
        if not area.contains(line.interpolate(0.5, normalized=True)):
            continue
        r = rows.setdefault(name, {"lines": [], "types": []})
        r["lines"].append(line)
        r["types"].append(hw)
    out = []
    from shapely.ops import unary_union
    for name, r in rows.items():
        types = sorted(set(r["types"]), key=lambda t: RANK.index(t) if t in RANK else len(RANK))
        geom = unary_union(r["lines"])
        out.append({"name": name, "highway": types[0], "highway_all": ";".join(types), "way_class": way_class(types[0]), "geometry": geom})
    return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")


def fetch_streets(area) -> gpd.GeoDataFrame:
    """All named streets with a midpoint in `area` (a shapely polygon in EPSG:4326)."""
    ways = fetch_ways((area.bounds[1], area.bounds[0], area.bounds[3], area.bounds[2]))
    gdf = streets_from_ways(ways, area)
    print(f"Found {len(gdf)} named streets ({len(ways)} OSM ways)")
    return gdf
