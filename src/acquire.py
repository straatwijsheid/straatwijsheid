"""Fetch gemeenten's street networks (OSM) and buurt boundaries (PDOK/CBS), for any gemeente in the Netherlands.

  python src/acquire.py Tilburg Breda        fetch one or more gemeenten (skips those already fetched; --force refetches)
  python src/acquire.py --list               gemeenten already in build/raw

Default for a gemeente: the street network is taken from the outline of its own CBS buurten (robust: no geocoding, no stale OSM polygon),
and the buurten are fetched under the same name. Exceptions (merged gemeenten, long official names) live in knowledge/global/gemeenten.json; the identity of every gemeente (CBS code GM####, name, province) in knowledge/global/gemeenten_index.json (see gemeenten.py).

Outputs, per gemeente:
  build/raw/streets_<slug>.geojson   one row per unique street name, merged geometry, with its buurt and wijk
  build/raw/buurten_<slug>.geojson   neighborhood polygons
and then the combined files every downstream script reads:
  build/raw/streets.geojson, build/raw/buurten.geojson   (all gemeenten, with a `gemeente` column)
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


def record_gemeente(code: str, name: str, buurten: gpd.GeoDataFrame, historic: bool = False) -> None:
    """Register a new gemeente (code, name, province from the CBS province outlines) in the knowledge repository's global/gemeenten_index.json."""
    import gemeenten
    if code not in gemeenten.index():
        gemeenten.register(code, name, province_of_buurten(buurten), historic)


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
    cbs_codes = sorted(buurten["gemeentecode"].unique())          # the gemeente PDOK files these buurten under (today's, not a merged-away one's)
    buurten = buurten[["name", "wijk", "geometry"]].reset_index(drop=True)
    buurten["gemeente"] = gemeente
    buurten.attrs["cbs_codes"] = cbs_codes
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


def file_key(code: str) -> str:
    """Per-gemeente raw files are named by CBS code: streets_gm0772.geojson (a name is not unique, a code is)."""
    return code.lower()


def _legacy_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def cbs_gemeenten() -> dict[str, str]:
    """{code: official CBS name} for every current gemeente (PDOK/CBS gebiedsindelingen); official names are unique ('Bergen (NH.)', 'Bergen (L.)')."""
    r = requests.get(PROVINCES_URL, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                                            "typeNames": "gebiedsindelingen:gemeente_gegeneraliseerd", "outputFormat": "application/json"}, timeout=120)
    r.raise_for_status()
    return {f["properties"]["statcode"]: f["properties"]["statnaam"] for f in r.json()["features"]}


def resolve(arg: str) -> tuple[str | None, str]:
    """(code or None, name) for a gemeente given as code or name. The registry decides; a code the registry does not know yet is looked up at CBS;
    an unknown name returns code None (the code then comes from PDOK or from `code` in gemeenten.json when the gemeente is fetched)."""
    import gemeenten
    code = gemeenten.known(arg)
    if code:
        return code, gemeenten.name_of(code)
    if gemeenten.is_code(arg.upper()):
        names = cbs_gemeenten()
        if arg.upper() not in names:
            raise KeyError(f"{arg} is not a current CBS gemeentecode")
        return arg.upper(), names[arg.upper()]
    return None, arg


def combine() -> None:
    """Merge every per-gemeente file into the combined files downstream reads (in gemeente-name order, as before the files were named by code)."""
    import pandas as pd
    import gemeenten

    def order(p):
        code = p.stem.split("_", 1)[1].upper()
        return _legacy_slug(gemeenten.name_of(code)), code

    for kind in ("streets", "buurten"):
        parts = [gpd.read_file(p) for p in sorted(RAW_DIR.glob(f"{kind}_*.geojson"), key=order)]
        combined = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
        combined.to_file(RAW_DIR / f"{kind}.geojson", driver="GeoJSON")
        print(f"Wrote {kind}.geojson: {len(combined)} rows from {combined['gemeente_code'].nunique()} gemeente(n)")


def acquire(arg: str) -> None:
    """Fetch one gemeente (code or name): buurten from PDOK, streets from the buurten outline, joined and written; then rebuild the combined files."""
    import gemeenten
    code, gemeente = resolve(arg)
    if not code and gemeenten.is_code(arg.upper()):
        raise KeyError(arg)
    cfg = CONFIG.get("merged", {}).get(gemeente) or CONFIG.get("aliases", {}).get(gemeente) or {}
    pdok = cfg.get("pdok", gemeente)
    buurten = fetch_buurten(gemeente, pdok, cfg.get("buurt_prefix"))
    if not len(buurten):
        raise RuntimeError(f"PDOK has no buurten for '{pdok}': add an entry to knowledge/global/gemeenten.json")
    if not code:
        code = cfg.get("code")
        cbs = buurten.attrs["cbs_codes"]
        if not code and len(cbs) == 1 and gemeente not in CONFIG.get("merged", {}):
            code = cbs[0]
        if not code:
            raise RuntimeError(f"cannot tell the gemeentecode of '{gemeente}' (PDOK files its buurten under {cbs}): add `code` to its entry in knowledge/global/gemeenten.json")
    record_gemeente(code, gemeente, buurten, historic=gemeente in CONFIG.get("merged", {}))
    streets = fetch_streets(buurten.geometry.union_all())
    streets["gemeente"] = gemeente
    streets["gemeente_code"] = code
    streets = join_streets_to_buurten(streets, buurten)
    buurten["gemeente_code"] = code
    buurten.to_file(RAW_DIR / f"buurten_{file_key(code)}.geojson", driver="GeoJSON")
    streets.to_file(RAW_DIR / f"streets_{file_key(code)}.geojson", driver="GeoJSON")
    _snapshot(code)


def _snapshot(code: str) -> None:
    import snapshots
    path = RAW_DIR / f"streets_{file_key(code)}.geojson"
    snapshots.record("streets/" + file_key(code), path, "OSM named highway ways (osm_streets.py) joined to CBS buurten", rows=len(gpd.read_file(path)), archive=False)


def supplement(code: str) -> None:
    """Add the named streets an earlier (osmnx drive-network) fetch missed, and fill highway/way_class for the streets it had.
    Existing rows keep their geometry; new rows are appended with `origin = supplement`."""
    import pandas as pd
    import gemeenten

    path = RAW_DIR / f"streets_{file_key(code)}.geojson"
    old = gpd.read_file(path)
    buurten = gpd.read_file(RAW_DIR / f"buurten_{file_key(code)}.geojson")
    fresh = fetch_streets(buurten.geometry.union_all())
    info = fresh.drop_duplicates("name").set_index("name")[["highway", "highway_all", "way_class"]]
    for col in info.columns:
        old[col] = old["name"].map(info[col])
    if "origin" not in old:
        old["origin"] = "drive_network"
    new = fresh[~fresh["name"].isin(set(old["name"]))].copy()
    if len(new):
        new["gemeente"] = gemeenten.name_of(code)
        new["gemeente_code"] = code
        new = join_streets_to_buurten(new, buurten)
        new["origin"] = "supplement"
        old = gpd.GeoDataFrame(pd.concat([old, new], ignore_index=True), crs=old.crs)
    old.to_file(path, driver="GeoJSON")
    _snapshot(code)
    print(f"{gemeenten.name_of(code)}: +{len(new)} streets ({new['way_class'].value_counts().to_dict() if len(new) else {}}); now {len(old)}")


def have(code: str) -> bool:
    return (RAW_DIR / f"streets_{file_key(code)}.geojson").exists()


def fetched_codes() -> list[str]:
    return sorted(p.stem[len("streets_"):].upper() for p in RAW_DIR.glob("streets_*.geojson"))


def migrate_codes() -> None:
    """One-off for a build directory made before gemeenten were keyed by code: streets_<slug>.geojson -> streets_gm####.geojson with a
    `gemeente_code` column (and the same for buurten), snapshot histories moved to the new names, combined files rebuilt."""
    import gemeenten
    import snapshots
    moved = []
    for kind in ("streets", "buurten"):
        for p in sorted(RAW_DIR.glob(f"{kind}_*.geojson")):
            if gemeenten.is_code(p.stem.split("_", 1)[1].upper()):
                continue
            df = gpd.read_file(p)
            code = gemeenten.code_of(df["gemeente"].iloc[0])
            if "gemeente_code" not in df:
                df.insert(list(df.columns).index("gemeente") + 1, "gemeente_code", code)
            new = RAW_DIR / f"{kind}_{file_key(code)}.geojson"
            df.to_file(new, driver="GeoJSON")
            p.unlink()
            if kind == "streets":
                moved.append((p.stem[len("streets_"):], code, new, len(df)))
    m = snapshots.load()
    for old_slug, code, new, rows in moved:
        hist = m["snapshots"].pop(f"streets/{old_slug}", [])
        m["snapshots"][f"streets/{file_key(code)}"] = hist
    snapshots.save(m)
    for old_slug, code, new, rows in moved:
        snapshots.record(f"streets/{file_key(code)}", new, "OSM named highway ways (osm_streets.py) joined to CBS buurten", rows=rows, archive=False,
                         note="gemeente_code column added; file renamed from the gemeente name to its CBS code")
    combine()
    print(f"migrated {len(moved)} gemeenten to code-named files")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gemeenten", nargs="*", help="gemeente names or CBS codes (GM####)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="refetch gemeenten that are already in build/raw")
    ap.add_argument("--supplement", action="store_true", help="add streets an older fetch missed to gemeenten already in build/raw (all of them if none named)")
    ap.add_argument("--migrate-codes", action="store_true", help="one-off: rename an older build directory's per-gemeente files by CBS code")
    ap.add_argument("--retries", type=int, default=4, help="Overpass is often busy: attempts per gemeente")
    a = ap.parse_args(argv)
    if a.migrate_codes:
        migrate_codes()
        return
    if a.supplement:
        todo = [resolve(g)[0] for g in a.gemeenten] if a.gemeenten else fetched_codes()
        failed = []
        for code in sorted(set(todo)):
            for attempt in range(1, a.retries + 1):
                try:
                    supplement(code)
                    break
                except Exception as e:                                 # noqa: BLE001
                    print(f"{code}: attempt {attempt}/{a.retries} failed: {str(e)[:120]}")
                    time.sleep(10 * attempt)
            else:
                failed.append(code)
        combine()
        if failed:
            sys.exit(f"failed: {failed}")
        return
    if a.list or not a.gemeenten:
        import gemeenten
        done = fetched_codes()
        print(f"{len(done)} gemeenten in build/raw: {', '.join(f'{c} {gemeenten.name_of(c)}' for c in done)}")
        return
    failed = []
    for g in a.gemeenten:
        code, _ = resolve(g)
        if code and have(code) and not a.force:
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
