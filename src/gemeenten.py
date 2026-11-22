"""Gemeente identity: the CBS gemeentecode (GM####) is the key, the name is for display.

A name is not unique (Bergen in Noord-Holland and in Limburg, Hengelo in Gelderland and in Overijssel), so override layers, snapshots, raw files and the
in-memory street keys use the code. The registry lives in the knowledge repository: `global/gemeenten_index.json`,
`{"gemeenten": {"GM0772": {"name": "Eindhoven", "province": "Noord-Brabant"}, ...}}`. `acquire.py` adds a gemeente when it first fetches it.

  python src/gemeenten.py              list the registry
  python src/gemeenten.py Eindhoven    resolve a name (or code) to its code
"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import config

CODE = re.compile(r"^GM\d{4}$")


def path() -> Path:
    return config.KNOWLEDGE / "global" / "gemeenten_index.json"


@lru_cache(maxsize=8)
def _load(p: str, mtime: float) -> dict:
    return json.loads(Path(p).read_text())["gemeenten"]


def index() -> dict[str, dict]:
    """{code: {"name", "province", ["historic"]}}"""
    p = path()
    return _load(str(p), p.stat().st_mtime) if p.exists() else {}


def is_code(s: str) -> bool:
    return bool(CODE.match(s))


def name_of(code: str) -> str:
    return index()[code]["name"]


def province_of(code: str) -> str:
    return index()[code]["province"]


def codes_for(name: str) -> list[str]:
    return [c for c, v in index().items() if v["name"] == name]


def code_of(name_or_code: str) -> str:
    """The code of a gemeente given by code or by (display) name. A name shared by two gemeenten raises: use the code."""
    if is_code(name_or_code):
        if name_or_code not in index():
            raise KeyError(f"{name_or_code} is not in {path().name}")
        return name_or_code
    found = codes_for(name_or_code)
    if not found:
        raise KeyError(f"unknown gemeente {name_or_code!r}: not in {path().name} (acquire.py adds it)")
    if len(found) > 1:
        raise ValueError(f"{name_or_code!r} names {len(found)} gemeenten ({', '.join(found)}): use the code")
    return found[0]


def known(name_or_code: str) -> str | None:
    """The code if the registry knows this gemeente, else None. A name shared by two gemeenten still raises (ValueError): never guess between them."""
    try:
        return code_of(name_or_code)
    except KeyError:
        return None


def register(code: str, name: str, province: str, historic: bool = False) -> None:
    """Add a gemeente to the registry (idempotent; an existing entry is never overwritten)."""
    if not is_code(code):
        raise ValueError(f"not a CBS gemeentecode: {code!r}")
    p = path()
    data = json.loads(p.read_text()) if p.exists() else {"_comment": "see src/gemeenten.py", "gemeenten": {}}
    if code in data["gemeenten"]:
        return
    entry = {"name": name, "province": province}
    if historic:
        entry["historic"] = True
    data["gemeenten"][code] = entry
    data["gemeenten"] = dict(sorted(data["gemeenten"].items()))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            c = code_of(a)
            print(f"{c}\t{name_of(c)}\t{province_of(c)}")
    else:
        for c, v in index().items():
            print(f"{c}\t{v['name']}\t{v['province']}{'\thistoric' if v.get('historic') else ''}")
