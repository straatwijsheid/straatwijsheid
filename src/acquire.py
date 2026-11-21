"""Fetch gemeenten's street networks (OSM) and buurt boundaries (PDOK/CBS), for any gemeente in the Netherlands.

  python src/acquire.py Tilburg Breda        fetch one or more gemeenten (skips those already fetched; --force refetches)
  python src/acquire.py --list               gemeenten already in data/raw

Default for a gemeente: the street network is taken from the outline of its own CBS buurten (robust: no geocoding, no stale OSM polygon),
and the buurten are fetched under the same name. Exceptions (merged gemeenten, long official names) live in data/knowledge/gemeenten.json.

Outputs, per gemeente:
  data/raw/streets_<slug>.geojson   one row per unique street name, merged geometry, with its buurt and wijk
  data/raw/buurten_<slug>.geojson   neighborhood polygons
and then the combined files every downstream script reads:
  data/raw/streets.geojson, data/raw/buurten.geojson   (all gemeenten, with a `gemeente` column)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import requests

# osmnx pins every Overpass request to ONE IPv4 address (socket.gethostbyname) so its
# slot-availability check and the query hit the same machine. If that machine is down
# the whole fetch fails even though the host has other working addresses. Skipping the
# pin lets requests/urllib3 fall back across addresses; the cost is that the status
# check and the query may hit different servers, which is harmless for a one-off fetch.
import osmnx._http as _ox_http  # noqa: E402

_ox_http._config_dns = lambda url: None
if os.environ.get("OVERPASS_URL"):
    ox.settings.overpass_url = os.environ["OVERPASS_URL"]

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = json.loads((RAW_DIR.parent / "knowledge" / "gemeenten.json").read_text())
PDOK_WFS_URL = "https://service.pdok.nl/cbs/wijkenbuurten/2024/wfs/v1_0"


def fetch_streets(gemeente: str, area=None, place=None) -> gpd.GeoDataFrame:
    """Street network inside `area` (a polygon) or, failing that, the OSM place `place`."""
    if area is not None:
        print(f"Fetching street network for the {gemeente} outline")
        graph = ox.graph_from_polygon(area, network_type="drive", retain_all=False)
    else:
        print(f"Fetching street network for: {place}")
        graph = ox.graph_from_place(place, network_type="drive", retain_all=False)
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


def fetch_buurten(gemeente: str, pdok_name: str, prefix: str | None = None) -> gpd.GeoDataFrame:
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
            "filter": _gemeente_filter(pdok_name),
        },
        timeout=60,
    )
    resp.raise_for_status()
    buurten = gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:4326")
    if prefix and prefix != "BU":
        prefixes = tuple(prefix.split(","))
        buurten = buurten[buurten["buurtcode"].str.startswith(prefixes)]

    wijk_resp = requests.get(
        PDOK_WFS_URL,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": "wijkenbuurten:wijken",
            "outputFormat": "json",
            "srsName": "EPSG:4326",
            "filter": _gemeente_filter(pdok_name),
        },
        timeout=60,
    )
    wijk_resp.raise_for_status()
    wijk_props = [f["properties"] for f in wijk_resp.json()["features"]
                  if not prefix or prefix == "BU" or f["properties"]["wijkcode"].replace("WK", "BU").startswith(tuple(prefix.split(",")))]
    wijk_lookup = {w["wijkcode"]: w["wijknaam"] for w in wijk_props}

    buurten = buurten.rename(columns={"buurtnaam": "name"})
    buurten["wijk"] = buurten["wijkcode"].map(wijk_lookup)
    buurten = buurten[["name", "wijk", "geometry"]].reset_index(drop=True)
    buurten["gemeente"] = gemeente
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


def acquire(gemeente: str) -> None:
    """Fetch one gemeente: buurten from PDOK, streets from the buurten outline, joined and written; then rebuild the combined files."""
    cfg = CONFIG.get("merged", {}).get(gemeente) or CONFIG.get("aliases", {}).get(gemeente) or {}
    pdok = cfg.get("pdok", gemeente)
    buurten = fetch_buurten(gemeente, pdok, cfg.get("buurt_prefix"))
    if not len(buurten):
        raise RuntimeError(f"PDOK has no buurten for '{pdok}': add an entry to data/knowledge/gemeenten.json")
    streets = fetch_streets(gemeente, area=buurten.geometry.union_all())
    streets["gemeente"] = gemeente
    streets = join_streets_to_buurten(streets, buurten)
    buurten.to_file(RAW_DIR / f"buurten_{slug(gemeente)}.geojson", driver="GeoJSON")
    streets.to_file(RAW_DIR / f"streets_{slug(gemeente)}.geojson", driver="GeoJSON")


def have(gemeente: str) -> bool:
    return (RAW_DIR / f"streets_{slug(gemeente)}.geojson").exists()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gemeenten", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="refetch gemeenten that are already in data/raw")
    ap.add_argument("--retries", type=int, default=4, help="Overpass is often busy: attempts per gemeente")
    a = ap.parse_args(argv)
    if a.list or not a.gemeenten:
        done = sorted(p.stem[len("streets_"):] for p in RAW_DIR.glob("streets_*.geojson"))
        print(f"{len(done)} gemeenten in data/raw: {', '.join(done)}")
        return
    failed = []
    for g in a.gemeenten:
        if have(g) and not a.force:
            print(f"{g}: already fetched (use --force to refetch)")
            continue
        for attempt in range(1, a.retries + 1):
            try:
                acquire(g)
                break
            except Exception as e:                                     # noqa: BLE001  (network errors vary: Overpass 429/502/timeouts)
                print(f"{g}: attempt {attempt}/{a.retries} failed: {str(e)[:120]}")
                time.sleep(10 * attempt)
        else:
            failed.append(g)
    combine()
    if failed:
        sys.exit(f"failed: {failed}")


if __name__ == "__main__":
    main()
