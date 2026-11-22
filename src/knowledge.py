"""Where the hand-curated knowledge lives, and how it is sharded by province and gemeente.

  <knowledge>/global/                                         lists that apply everywhere (vocabulary, species, famous people, ...), plus gemeenten_index.json
  <knowledge>/gemeenten/<province>/<gemeente>/corrections.json         reviewed street-level corrections
  <knowledge>/gemeenten/<province>/<gemeente>/review_notes.json        notes and extra questions for the review sheet
  <knowledge>/gemeenten/<province>/<gemeente>/overrides/<layer>.json   the street-level classification layers (see overrides.py)

Every gemeente lies in exactly one province. global/gemeenten_index.json (see gemeenten.py) maps the CBS gemeentecode (GM####) to name and province, and acquire.py
adds new gemeenten; a gemeente without an entry is filed under `unassigned`, which `python src/knowledge.py --check` reports. Directory names are slugs
(province, then name), so a pull request about one gemeente touches one directory and two same-named gemeenten in different provinces never share one.
The shard directory *is* the gemeente's identity on disk: the entries inside keep their `gemeente` name for readability, and the loaders attach the
`gemeente_code` of the shard they came from (the in-memory key is `(gemeente_code, street)`, never the name).

  python src/knowledge.py --check     provinces known for every shard directory and every acquired gemeente
  python src/knowledge.py --layout    print the tree with entry counts
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import config
import gemeenten

UNASSIGNED = "unassigned"


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[’'`]", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def global_dir() -> Path:
    return config.KNOWLEDGE / "global"


def province_of(gemeente: str) -> str:
    """The province of a gemeente given by code or name (a name must be unique); UNASSIGNED if the registry does not know it."""
    code = gemeenten.known(gemeente)
    return gemeenten.province_of(code) if code else UNASSIGNED


def gemeente_dir(gemeente: str) -> Path:
    """The shard directory of a gemeente given by code or name."""
    code = gemeenten.known(gemeente)
    name = gemeenten.name_of(code) if code else gemeente
    return config.KNOWLEDGE / "gemeenten" / slug(province_of(gemeente)) / slug(name)


def code_of_shard(d: Path) -> str | None:
    """The gemeentecode a shard directory belongs to (None for a directory the registry does not know)."""
    by_dir = {gemeente_dir(c): c for c in gemeenten.index()}
    return by_dir.get(d)


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
        code = code_of_shard(d)
        out.extend({**o, "gemeente_code": code} for o in read_json(d / filename, {}).get(key, []))
    return out


def check() -> int:
    known = set(gemeenten.index())
    bad = 0
    for d in shard_dirs():
        if d.parent.name == UNASSIGNED or code_of_shard(d) is None:
            print(f"shard without a registry entry: {d.relative_to(config.KNOWLEDGE)}"); bad += 1
    try:
        import geopandas as gpd
        gems = set(gpd.read_file(config.RAW / "streets.geojson")["gemeente_code"])
        for g in sorted(gems - known):
            print(f"acquired gemeente not in gemeenten_index.json: {g}"); bad += 1
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
