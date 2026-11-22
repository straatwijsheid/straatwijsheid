"""The knowledge repository's schema version: core refuses a checkout it does not understand.

`<knowledge>/schema_version` holds one integer. It is bumped, in the knowledge repository, whenever the layout or the format of its files changes
in a way older code cannot read (a renamed folder, a new required field, a changed key). Core carries the one version it reads, SCHEMA_VERSION;
a checkout with another version, or with none (it predates the file), is refused with a message saying which side to update.
The check runs at the start of `pipeline.py` (every command but bootstrap) and `rules/run.py`, and again in `gemeenten.index()`, which every stage that touches
gemeenten reads first.

  python src/schema.py        print the versions and check
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import config

SCHEMA_VERSION = 1           # the version of the knowledge layout this code reads


class SchemaMismatch(SystemExit):
    """A SystemExit so a command stops with the message and no traceback; tests can catch it."""


def path() -> Path:
    return config.KNOWLEDGE / "schema_version"


@lru_cache(maxsize=8)
def _read(p: str, mtime: float) -> str:
    return Path(p).read_text().strip()


def found() -> int | None:
    """The version of the knowledge checkout, None when the file is missing or not an integer."""
    p = path()
    if not p.exists():
        return None
    try:
        return int(_read(str(p), p.stat().st_mtime))
    except ValueError:
        return None


def require() -> None:
    """Raise SchemaMismatch unless the knowledge checkout's schema_version equals SCHEMA_VERSION."""
    v = found()
    if v == SCHEMA_VERSION:
        return
    where = config.KNOWLEDGE
    if v is None:
        what = f"{where} has no readable schema_version file (an older checkout, or not the knowledge repository)"
        fix = "update it (git -C knowledge pull) and, if it still has none, the knowledge repository is too old for this code"
    elif v > SCHEMA_VERSION:
        what = f"{where} has schema_version {v}, newer than the {SCHEMA_VERSION} this code reads"
        fix = "update this code (git pull)"
    else:
        what = f"{where} has schema_version {v}, older than the {SCHEMA_VERSION} this code reads"
        fix = "update the knowledge checkout (git -C knowledge pull)"
    raise SchemaMismatch(f"Incompatible knowledge repository: {what}.\n  To fix: {fix}.")


if __name__ == "__main__":
    print(f"knowledge at {config.KNOWLEDGE}: schema_version {found()}, this code reads {SCHEMA_VERSION}")
    require()
    print("ok")
