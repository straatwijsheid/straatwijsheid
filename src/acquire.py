"""Fetch a gemeente's street network (OSM) and buurt boundaries (PDOK/CBS).

Usage: python src/acquire.py [Gemeente]   (default: Eindhoven)

Outputs, per gemeente:
  data/raw/streets_<slug>.geojson   one row per unique street name, merged geometry
  data/raw/buurten_<slug>.geojson   neighborhood polygons
and then the combined files every downstream script reads:
  data/raw/streets.geojson, data/raw/buurten.geojson   (all gemeenten, with a `gemeente` column)
"""
import sys
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

GEMEENTE = "Eindhoven"
PLACE = f"{GEMEENTE}, North Brabant, Netherlands"
PDOK_WFS_URL = "https://service.pdok.nl/cbs/wijkenbuurten/2024/wfs/v1_0"


def fetch_streets() -> gpd.GeoDataFrame:
    print(f"Fetching street network for: {PLACE}")
    graph = ox.graph_from_place(PLACE, network_type="drive", retain_all=False)
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    edges = edges[edges["name"].notna()].copy()
    # name can be a list when a way has alt names; take the first
    edges["name"] = edges["name"].apply(lambda n: n[0] if isinstance(n, list) else n)

    # merge all segments sharing a name into one MultiLineString per street
    merged = (
        edges[["name", "geometry"]]
        .dissolve(by="name")
        .reset_index()
    )
    merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=edges.crs)
    print(f"Found {len(merged)} unique street names ({len(edges)} raw segments)")
    return merged


def _gemeente_filter(gemeente: str) -> str:
    return (
        "<Filter xmlns='http://www.opengis.net/ogc'>"
        "<PropertyIsEqualTo><PropertyName>gemeentenaam</PropertyName>"
        f"<Literal>{gemeente}</Literal></PropertyIsEqualTo></Filter>"
    )


def fetch_buurten() -> gpd.GeoDataFrame:
    print("Fetching buurt (neighborhood) boundaries from PDOK/CBS")
    resp = requests.get(
        PDOK_WFS_URL,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": "wijkenbuurten:buurten",
            "outputFormat": "json",
            "srsName": "EPSG:4326",
            "filter": _gemeente_filter(GEMEENTE),
        },
        timeout=60,
    )
    resp.raise_for_status()
    buurten = gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:4326")

    wijk_resp = requests.get(
        PDOK_WFS_URL,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": "wijkenbuurten:wijken",
            "outputFormat": "json",
            "srsName": "EPSG:4326",
            "filter": _gemeente_filter(GEMEENTE),
        },
        timeout=60,
    )
    wijk_resp.raise_for_status()
    wijk_props = [f["properties"] for f in wijk_resp.json()["features"]]
    wijk_lookup = {w["wijkcode"]: w["wijknaam"] for w in wijk_props}

    buurten = buurten.rename(columns={"buurtnaam": "name"})
    buurten["wijk"] = buurten["wijkcode"].map(wijk_lookup)
    buurten = buurten[["name", "wijk", "geometry"]].reset_index(drop=True)
    buurten["gemeente"] = GEMEENTE
    print(f"Found {len(buurten)} buurt polygons across {buurten['wijk'].nunique()} wijken")
    return buurten


def join_streets_to_buurten(
    streets: gpd.GeoDataFrame, buurten: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    metric_crs = streets.estimate_utm_crs()
    streets_pt = streets.copy()
    streets_pt["centroid"] = streets_pt.geometry.to_crs(metric_crs).centroid.to_crs(streets.crs)
    streets_pt = streets_pt.set_geometry("centroid")

    joined = gpd.sjoin(
        streets_pt, buurten.rename(columns={"name": "buurt"}), how="left", predicate="within"
    )
    # a centroid landing exactly on a shared boundary can match >1 polygon; keep one per street
    joined = joined[~joined.index.duplicated(keep="first")]
    streets = streets.loc[joined.index].copy()
    streets["buurt"] = joined["buurt"].values
    streets["wijk"] = joined["wijk"].values
    return streets


def slug(gemeente: str) -> str:
    return gemeente.lower().replace(" ", "-")


def combine() -> None:
    """Merge every per-gemeente file into the combined files downstream reads."""
    import pandas as pd

    for kind in ("streets", "buurten"):
        parts = [gpd.read_file(p) for p in sorted(RAW_DIR.glob(f"{kind}_*.geojson"))]
        combined = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
        combined.to_file(RAW_DIR / f"{kind}.geojson", driver="GeoJSON")
        print(f"Wrote {kind}.geojson: {len(combined)} rows from {combined['gemeente'].nunique()} gemeente(n)")


def main():
    global GEMEENTE, PLACE
    if len(sys.argv) > 1:
        GEMEENTE = sys.argv[1]
        PLACE = f"{GEMEENTE}, North Brabant, Netherlands"

    streets = fetch_streets()
    streets["gemeente"] = GEMEENTE
    try:
        buurten = fetch_buurten()
    except Exception as e:
        print(f"Buurt fetch failed ({e}); continuing without neighborhood join")
        buurten = gpd.GeoDataFrame(columns=["name", "geometry", "gemeente"])

    if len(buurten):
        streets = join_streets_to_buurten(streets, buurten)
        buurten.to_file(RAW_DIR / f"buurten_{slug(GEMEENTE)}.geojson", driver="GeoJSON")
    else:
        streets["buurt"] = None

    streets.to_file(RAW_DIR / f"streets_{slug(GEMEENTE)}.geojson", driver="GeoJSON")
    combine()


if __name__ == "__main__":
    main()
