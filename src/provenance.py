"""Where an output came from: the code and knowledge commits and the dated OpenStreetMap snapshots behind it.

Written next to the outputs as `PROVENANCE.json` (and shown in the map footer), so any map, CSV or number can be tied to exact inputs.

  python src/provenance.py        print the provenance of the current build and write PROVENANCE.json
"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

import config
import snapshots


def git_state(path: Path) -> dict:
    """{commit, dirty} of the git repository at `path`; commit None when it is not a repository."""
    def git(*a):
        return subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True)
    top = git("rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != Path(path).resolve():     # not a repository of its own (e.g. a plain folder inside another one)
        return {"commit": None, "dirty": None}
    r = git("rev-parse", "--short=12", "HEAD")
    return {"commit": r.stdout.strip(), "dirty": bool(git("status", "--porcelain").stdout.strip())}


def latest_snapshots() -> dict:
    """{snapshot name: fetched_at of its newest fetch} for the OSM sources (per-gemeente street files collapse to the oldest and newest date)."""
    out, streets = {}, []
    for name, hist in snapshots.load()["snapshots"].items():
        if not hist:
            continue
        (streets if name.startswith("streets/") else None) and streets.append(hist[-1]["fetched_at"])
        if not name.startswith("streets/"):
            out[name] = hist[-1]["fetched_at"]
    if streets:
        out["streets (oldest..newest gemeente fetch)"] = f"{min(streets)}..{max(streets)}"
    return out


def collect() -> dict:
    return {"generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "code": git_state(config.ROOT),
            "knowledge": git_state(config.KNOWLEDGE), "osm_snapshots": latest_snapshots()}


def line(p: dict) -> str:
    def c(x):
        return (x["commit"] or "unversioned") + ("+modified" if x["dirty"] else "")
    osm = p["osm_snapshots"].get("osm_etymology_ways") or next(iter(p["osm_snapshots"].values()), "n/a")
    return f"Data © OpenStreetMap contributors (ODbL), CBS/PDOK (CC-BY 4.0), Wikidata (CC0). Built {p['generated_at'][:10]} from code {c(p['code'])}, knowledge {c(p['knowledge'])}, OSM etymology snapshot {osm[:10]}."


def write() -> dict:
    p = collect()
    config.OUTPUT.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT / "PROVENANCE.json").write_text(json.dumps(p, indent=1) + "\n")
    return p


if __name__ == "__main__":
    p = write()
    print(json.dumps(p, indent=1))
    print(line(p))
