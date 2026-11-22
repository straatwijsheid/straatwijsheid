"""Where the hand-curated knowledge lives, and how it is sharded by province and gemeente.

  <knowledge>/global/                                         lists that apply everywhere (vocabulary, species, famous people, ...), plus provinces.json
  <knowledge>/gemeenten/<province>/<gemeente>/corrections.json         reviewed street-level corrections
  <knowledge>/gemeenten/<province>/<gemeente>/review_notes.json        notes and extra questions for the review sheet
  <knowledge>/gemeenten/<province>/<gemeente>/overrides/<layer>.json   the street-level classification layers (see overrides.py)

Every gemeente lies in exactly one province; global/provinces.json maps gemeente name -> province name (acquire.py adds new gemeenten; a gemeente
without an entry is filed under `unassigned`, which `python src/knowledge.py --check` reports). Directory names are slugs, so a pull request
about one gemeente touches one directory.

  python src/knowledge.py --check     provinces known for every shard directory and every acquired gemeente
  python src/knowledge.py --layout    print the tree with entry counts
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import config

UNASSIGNED = "unassigned"


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[’'`]", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def global_dir() -> Path:
    return config.KNOWLEDGE / "global"


def provinces() -> dict:
    p = global_dir() / "provinces.json"
    return json.loads(p.read_text()).get("provinces", {}) if p.exists() else {}


def province_of(gemeente: str) -> str:
    return provinces().get(gemeente, UNASSIGNED)


def gemeente_dir(gemeente: str) -> Path:
    return config.KNOWLEDGE / "gemeenten" / slug(province_of(gemeente)) / slug(gemeente)


def shard_dirs() -> list[Path]:
    root = config.KNOWLEDGE / "gemeenten"
    return sorted(d for p in root.glob("*/") for d in p.glob("*/") if d.is_dir()) if root.exists() else []


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def load_sharded(filename: str, key: str, gemeente_field: str = "gemeente") -> list[dict]:
    """The entries of `<gemeente dir>/<filename>[key]` from every shard, in a stable order (shard path, then file order)."""
    out = []
    for d in shard_dirs():
        out.extend(read_json(d / filename, {}).get(key, []))
    return out


def check() -> int:
    prov = provinces()
    bad = 0
    for d in shard_dirs():
        if d.parent.name == UNASSIGNED:
            print(f"unassigned shard: {d.relative_to(config.KNOWLEDGE)}"); bad += 1
    try:
        import geopandas as gpd
        gems = set(gpd.read_file(config.RAW / "streets.geojson")["gemeente"])
        for g in sorted(gems - set(prov)):
            print(f"no province for acquired gemeente: {g}"); bad += 1
    except Exception as e:      # no build data (e.g. in a bare knowledge checkout): skip
        print(f"(acquired gemeenten not checked: {type(e).__name__})")
    print("ok" if not bad else f"{bad} problem(s)")
    return bad


def layout() -> None:
    for d in shard_dirs():
        files = [f"{p.relative_to(d)}" for p in sorted(d.rglob("*.json"))]
        print(f"{d.relative_to(config.KNOWLEDGE)}: {len(files)} files")


if __name__ == "__main__":
    import sys
    sys.exit(check()) if "--check" in sys.argv else layout()
