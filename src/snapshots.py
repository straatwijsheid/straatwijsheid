"""Dated, checksummed snapshots of the data we download, so every number can be tied to the exact OSM state it came from and a refresh shows what changed.

OpenStreetMap changes daily and a re-fetch never returns the same data. Each fetch of a raw dataset is recorded in `raw/snapshots.json`
(fetched_at, sha256, size, rows, source, a hash of the query) and a gzipped copy is archived under `raw/snapshots/<name>/` (big per-gemeente street files are
recorded but not archived). The current file is still the one the pipeline reads; the archive is what a later refresh is compared with.

  python src/snapshots.py --status             every snapshot: latest fetch, checksum, how many are archived
  python src/snapshots.py --verify             does each current file still match its recorded checksum?
  python src/snapshots.py --backfill           record the files already in raw/ as baseline snapshots (file time, marked 'backfilled')
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import config


def _rel(path) -> str:
    """Paths in the manifest are relative to the raw directory, so the build directory can be anywhere (absolute only if outside it)."""
    try:
        return str(Path(path).resolve().relative_to(config.RAW.resolve()))
    except ValueError:
        return str(path)


def _abs(stored: str) -> Path:
    return Path(stored) if Path(stored).is_absolute() else config.RAW / stored


def manifest_path() -> Path:
    return config.RAW / "snapshots.json"


def archive_dir(name: str) -> Path:
    return config.RAW / "snapshots" / name.replace("/", "_")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load() -> dict:
    p = manifest_path()
    return json.loads(p.read_text()) if p.exists() else {"snapshots": {}}


def save(m: dict) -> None:
    manifest_path().parent.mkdir(parents=True, exist_ok=True)
    manifest_path().write_text(json.dumps(m, indent=1, ensure_ascii=False, sort_keys=True))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(name: str, path: Path, source: str, query: str | None = None, rows: int | None = None, archive: bool = True,
           fetched_at: str | None = None, note: str | None = None) -> dict:
    """Record the file at `path` as the newest snapshot of dataset `name`; archive a gzipped copy unless an identical one is archived."""
    path = Path(path)
    digest = sha256(path)
    m = load()
    hist = m["snapshots"].setdefault(name, [])
    entry = {"fetched_at": fetched_at or now(), "sha256": digest, "bytes": path.stat().st_size, "rows": rows, "source": source,
             "query_sha256": hashlib.sha256(query.encode()).hexdigest() if query else None, "file": _rel(path), "archive": None}
    if note:
        entry["note"] = note
    if archive:
        prior = next((h for h in reversed(hist) if h["sha256"] == digest and h.get("archive")), None)
        if prior:
            entry["archive"] = prior["archive"]
        else:
            d = archive_dir(name)
            d.mkdir(parents=True, exist_ok=True)
            target = d / f"{entry['fetched_at'][:10].replace('-', '')}_{digest[:8]}{path.suffix}.gz"
            with path.open("rb") as src, gzip.open(target, "wb", compresslevel=6) as dst:
                shutil.copyfileobj(src, dst)
            entry["archive"] = _rel(target)
    if hist and hist[-1]["sha256"] == digest:
        hist[-1].update({k: v for k, v in entry.items() if k != "fetched_at"})      # same bytes fetched again: keep the first date, note the refresh
        hist[-1]["last_checked"] = entry["fetched_at"]
    else:
        hist.append(entry)
    save(m)
    return entry


def history(name: str) -> list[dict]:
    return load()["snapshots"].get(name, [])


def previous_archive(name: str, current_sha: str | None = None) -> Path | None:
    """The newest archived snapshot of `name` whose content differs from `current_sha` (what a new fetch is compared with)."""
    for h in reversed(history(name)):
        if h.get("archive") and h["sha256"] != current_sha:
            p = _abs(h["archive"])
            if p.exists():
                return p
    return None


def read_archive(path: Path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def status() -> None:
    m = load()["snapshots"]
    if not m:
        print("no snapshots recorded (run --backfill)")
        return
    for name, hist in sorted(m.items()):
        last = hist[-1]
        print(f"{name:28}{len(hist):3} version(s)  latest {last['fetched_at'][:19]}  {last['sha256'][:10]}  {last.get('rows') or '-':>8} rows  "
              f"{sum(1 for h in hist if h.get('archive'))} archived{'  [' + last['note'] + ']' if last.get('note') else ''}")


def verify() -> bool:
    ok = True
    for name, hist in sorted(load()["snapshots"].items()):
        last = hist[-1]
        p = _abs(last["file"])
        if not p.exists():
            print(f"MISSING  {name}: {last['file']}")
            ok = False
        elif sha256(p) != last["sha256"]:
            print(f"CHANGED  {name}: {last['file']} differs from the snapshot recorded {last['fetched_at'][:10]}")
            ok = False
    print("all snapshots match their recorded checksums" if ok else "see above")
    return ok


def backfill() -> None:
    """Record what is already in raw/ (fetched before snapshots existed): file time as fetched_at, marked 'backfilled'."""
    def mtime(p):
        return dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, fn, src in (("osm_etymology_ways", "osm_etymology_ways.json", "Overpass: named highways with etymology/wikidata tags, Noord-Brabant"),
                          ("osm_places", "osm_places.json", "Overpass: named places, water, parks, reserves, Noord-Brabant")):
        p = config.RAW / fn
        if p.exists() and not history(name):
            record(name, p, src, archive=True, fetched_at=mtime(p), note="backfilled")
    for p in sorted(config.RAW.glob("streets_*.geojson")):
        name = "streets/" + p.stem[len("streets_"):]
        if not history(name):
            record(name, p, "OSM street list (drive network + supplement) joined to CBS buurten", archive=False, fetched_at=mtime(p), note="backfilled")
    status()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        backfill()
    elif a.verify:
        raise SystemExit(0 if verify() else 1)
    else:
        status()
