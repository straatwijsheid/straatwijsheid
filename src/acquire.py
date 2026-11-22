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
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

RAW_DIR = config.RAW
config.ensure_dirs()

CONFIG = json.loads((config.GLOBAL / "gemeenten.json").read_text())
PDOK_WFS_URL = "https://service.pdok.nl/cbs/wijkenbuurten/2024/wfs/v1_0"
PROVINCES_URL = "https://service.pdok.nl/cbs/gebiedsindelingen/2024/wfs/v1_0"


def province_of_buurten(buurten: gpd.GeoDataFrame) -> str:
    """The province a gemeente lies in (every gemeente lies in exactly one): where most of its buurten's representative points fall in the CBS province outlines."""
    import io
    r = requests.get(PROVINCES_URL, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "gebiedsindelingen:provincie_gegeneraliseerd",
                                            "outputFormat": "application/json"}, timeout=120)
    r.raise_for_status()
    prov = gpd.read_file(io.BytesIO(r.content))
    pts = buurten.to_crs(prov.crs).copy()
    pts["geometry"] = pts.geometry.representative_point()
    hit = gpd.sjoin(pts, prov[["statnaam", "geometry"]], how="inner", predicate="within")["statnaam"]
    if not len(hit):
        raise RuntimeError("could not place the gemeente in a province")
    return hit.value_counts().index[0]


def record_province(gemeente: str, buurten: gpd.GeoDataFrame) -> None:
    """Remember the province in the knowledge repository's global/provinces.json (the sharding of the per-gemeente knowledge depends on it)."""
    import knowledge
    path = config.GLOBAL / "provinces.json"
    data = knowledge.read_json(path, {"_comment": "Province of every gemeente (from the CBS/PDOK province outlines; acquire.py adds new gemeenten). Shards the knowledge by province/gemeente.", "provinces": {}})
    if gemeente not in data["provinces"]:
        data["provinces"][gemeente] = province_of_buurten(buurten)
        data["provinces"] = dict(sorted(data["provinces"].items()))
        knowledge.write_json(path, data)


def fetch_streets(area) -> gpd.GeoDataFrame:
    """Every named street-like OSM way with a midpoint inside `area` (see osm_streets.py for what counts)."""
    import osm_streets
    return osm_streets.fetch_streets(area)


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
    record_province(gemeente, buurten)
    streets = fetch_streets(buurten.geometry.union_all())
    streets["gemeente"] = gemeente
    streets = join_streets_to_buurten(streets, buurten)
    buurten.to_file(RAW_DIR / f"buurten_{slug(gemeente)}.geojson", driver="GeoJSON")
    streets.to_file(RAW_DIR / f"streets_{slug(gemeente)}.geojson", driver="GeoJSON")
    _snapshot(gemeente)


def _snapshot(gemeente: str) -> None:
    import snapshots
    snapshots.record("streets/" + slug(gemeente), RAW_DIR / f"streets_{slug(gemeente)}.geojson",
                     "OSM named highway ways (osm_streets.py) joined to CBS buurten", rows=len(gpd.read_file(RAW_DIR / f"streets_{slug(gemeente)}.geojson")), archive=False)


def supplement(gemeente: str) -> None:
    """Add the named streets an earlier (osmnx drive-network) fetch missed, and fill highway/way_class for the streets it had.
    Existing rows keep their geometry; new rows are appended with `origin = supplement`."""
    import pandas as pd

    path = RAW_DIR / f"streets_{slug(gemeente)}.geojson"
    old = gpd.read_file(path)
    buurten = gpd.read_file(RAW_DIR / f"buurten_{slug(gemeente)}.geojson")
    fresh = fetch_streets(buurten.geometry.union_all())
    info = fresh.drop_duplicates("name").set_index("name")[["highway", "highway_all", "way_class"]]
    for col in info.columns:
        old[col] = old["name"].map(info[col])
    if "origin" not in old:
        old["origin"] = "drive_network"
    new = fresh[~fresh["name"].isin(set(old["name"]))].copy()
    if len(new):
        new["gemeente"] = gemeente
        new = join_streets_to_buurten(new, buurten)
        new["origin"] = "supplement"
        old = gpd.GeoDataFrame(pd.concat([old, new], ignore_index=True), crs=old.crs)
    old.to_file(path, driver="GeoJSON")
    _snapshot(gemeente)
    print(f"{gemeente}: +{len(new)} streets ({new['way_class'].value_counts().to_dict() if len(new) else {}}); now {len(old)}")


def gemeente_name(slug_or_name: str) -> str:
    """The display name stored in the data for a slug ('bergen-op-zoom' -> 'Bergen op Zoom'); names pass through."""
    for p in RAW_DIR.glob("streets_*.geojson"):
        if p.stem[len("streets_"):] == slug(slug_or_name):
            return gpd.read_file(p, rows=1)["gemeente"].iloc[0]
    return slug_or_name


def have(gemeente: str) -> bool:
    return (RAW_DIR / f"streets_{slug(gemeente)}.geojson").exists()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gemeenten", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="refetch gemeenten that are already in data/raw")
    ap.add_argument("--supplement", action="store_true", help="add streets an older fetch missed to gemeenten already in data/raw (all of them if none named)")
    ap.add_argument("--retries", type=int, default=4, help="Overpass is often busy: attempts per gemeente")
    a = ap.parse_args(argv)
    if a.supplement:
        todo = a.gemeenten or [p.stem[len("streets_"):] for p in sorted(RAW_DIR.glob("streets_*.geojson"))]
        names = {slug(g): g for g in todo}
        failed = []
        for sl in sorted({slug(g) for g in todo}):
            g = next((x for x in todo if slug(x) == sl), sl)
            for attempt in range(1, a.retries + 1):
                try:
                    supplement(gemeente_name(sl))
                    break
                except Exception as e:                                 # noqa: BLE001
                    print(f"{sl}: attempt {attempt}/{a.retries} failed: {str(e)[:120]}")
                    time.sleep(10 * attempt)
            else:
                failed.append(sl)
        combine()
        if failed:
            sys.exit(f"failed: {failed}")
        return
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
