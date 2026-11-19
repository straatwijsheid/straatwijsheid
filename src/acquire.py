"""Fetch a gemeente's street network (OSM) and buurt boundaries (PDOK/CBS).

Usage: python src/acquire.py [Gemeente]   (default: Eindhoven)

Outputs, per gemeente:
  data/raw/streets_<slug>.geojson   one row per unique street name, merged geometry
  data/raw/buurten_<slug>.geojson   neighborhood polygons
and then the combined files every downstream script reads:
  data/raw/streets.geojson, data/raw/buurten.geojson   (all gemeenten, with a `gemeente` column)
"""
import os
import sys
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

# short name used in the data and on the map -> (official CBS/PDOK name, OSM place query)
# for gemeenten whose official name is unwieldy or that Nominatim cannot geocode
ALIASES = {
    "Nuenen": ("Nuenen, Gerwen en Nederwetten", "Nuenen, North Brabant, Netherlands"),
}
# Gemeenten fetched from the outline of their CBS buurten instead of an OSM place polygon:
# either merged away after the CBS boundaries were drawn (the area is the buurten of the
# absorbing gemeente whose code starts with the prefix), or gemeenten whose OSM place
# polygon is only the old core ("'s-Hertogenbosch" misses Rosmalen, Nuland, Vinkel...).
# short name -> (gemeente in PDOK, buurtcode prefix(es), comma-separated; "BU" = all its buurten)
MERGED = {
    "'s-Hertogenbosch": ("'s-Hertogenbosch", "BU"),
    "Weesp": ("Amsterdam", "BU0363S"),  # merged into Amsterdam in 2022
    "Sint-Oedenrode": ("Meierijstad", "BU194803"),  # merged into Meierijstad in 2017
    "Uden": ("Maashorst", "BU199101,BU199102"),  # Uden + Volkel; merged with Landerd into Maashorst in 2022
    "Schijndel": ("Meierijstad", "BU194802"),  # ditto
    "Veghel": ("Meierijstad", "BU194801,BU194804"),  # ditto: Erp/Boerdonk/Keldonk + Veghel (comma = several prefixes)
    "Landerd": ("Maashorst", "BU199103,BU199104,BU199105,BU199106"),  # Odiliapeel, Schaijk, Reek, Zeeland; the rest of Maashorst
}
# Gemeenten fetched from the outline of their own CBS buurten (the OSM place polygon may be stale or
# fail to geocode): short name -> (PDOK name, all buurten)
for _g in ("Waalre", "Sint-Michielsgestel", "Bernheze", "Heeze-Leende", "Someren", "Asten", "Deurne", "Heusden", "Oss",
           "Eersel", "Bladel", "Reusel-De Mierden", "Bergeijk", "Cranendonck", "Hilvarenbeek", "Goirle",
           "Tilburg", "Waalwijk", "Loon op Zand", "Dongen", "Alphen-Chaam", "Baarle-Nassau", "Land van Cuijk", "Altena",
           "Gilze en Rijen", "Oosterhout", "Geertruidenberg", "Drimmelen", "Zundert", "Breda",
           "Etten-Leur", "Rucphen", "Halderberge", "Moerdijk", "Steenbergen", "Roosendaal", "Bergen op Zoom", "Woensdrecht"):
    MERGED[_g] = (_g, "BU")
BUURT_PREFIX = None
AREA = None  # polygon to fetch streets from, when set

GEMEENTE = "Eindhoven"
PDOK_NAME = GEMEENTE
PLACE = f"{GEMEENTE}, North Brabant, Netherlands"
PDOK_WFS_URL = "https://service.pdok.nl/cbs/wijkenbuurten/2024/wfs/v1_0"


def fetch_streets() -> gpd.GeoDataFrame:
    if AREA is not None:
        print(f"Fetching street network for the {GEMEENTE} outline")
        graph = ox.graph_from_polygon(AREA, network_type="drive", retain_all=False)
    else:
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
            "filter": _gemeente_filter(PDOK_NAME),
        },
        timeout=60,
    )
    resp.raise_for_status()
    buurten = gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:4326")
    if BUURT_PREFIX:
        prefixes = tuple(BUURT_PREFIX.split(","))
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
            "filter": _gemeente_filter(PDOK_NAME),
        },
        timeout=60,
    )
    wijk_resp.raise_for_status()
    wijk_props = [f["properties"] for f in wijk_resp.json()["features"]
                  if not BUURT_PREFIX or f["properties"]["wijkcode"].replace("WK", "BU").startswith(tuple(BUURT_PREFIX.split(",")))]
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
    global GEMEENTE, PDOK_NAME, PLACE, BUURT_PREFIX, AREA
    if len(sys.argv) > 1:
        GEMEENTE = sys.argv[1]
        if GEMEENTE in MERGED:
            PDOK_NAME, BUURT_PREFIX = MERGED[GEMEENTE]
            buurten = fetch_buurten()
            AREA = buurten.geometry.union_all()
            streets = fetch_streets()
            streets["gemeente"] = GEMEENTE
            streets = join_streets_to_buurten(streets, buurten)
            buurten.to_file(RAW_DIR / f"buurten_{slug(GEMEENTE)}.geojson", driver="GeoJSON")
            streets.to_file(RAW_DIR / f"streets_{slug(GEMEENTE)}.geojson", driver="GeoJSON")
            combine()
            return
        PDOK_NAME, PLACE = ALIASES.get(
            GEMEENTE, (GEMEENTE, f"{GEMEENTE}, North Brabant, Netherlands")
        )

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
