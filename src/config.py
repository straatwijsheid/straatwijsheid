"""Where things live and how this machine is set up: one place for every path and setting.

Lookup order for each setting: environment variable > `config.local.toml` in the repository root (git-ignored, machine-specific, may hold
personal details such as the Wikidata contact) > default. `config.example.toml` documents the keys.

  setting            env variable            config.local.toml key   default
  build directory    STREETS_BUILD_DIR       build_dir               <repo>/build   (git-ignored; raw/ enriched/ output/ cache/ names/, everything rebuildable)
  knowledge dir      STREETS_KNOWLEDGE_DIR   knowledge_dir           <repo>/knowledge   (the knowledge repository checked out; `pipeline.py bootstrap` clones it)
  knowledge repo     STREETS_KNOWLEDGE_REPO  knowledge_repo          https://github.com/straatwijsheid/knowledge.git
  Wikidata contact   WIKIDATA_CONTACT        wikidata_contact        (none: lookups work but are throttled harder)
  Overpass URL       OVERPASS_URL            overpass_url            https://overpass-api.de/api/interpreter
  basemap tile URL   TILE_URL                tile_url                https://tile.openstreetmap.org/{z}/{x}/{y}.png   (TILE_ATTRIBUTION / tile_attribution: the credit the provider requires)

Rebuildable data lives under the build directory: raw/ enriched/ output/ cache/ names/. `python src/config.py` prints the resolved settings (the contact is only shown as set / not set).
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_FILE = ROOT / "config.local.toml"


def _local() -> dict:
    try:
        return tomllib.loads(LOCAL_FILE.read_text())
    except FileNotFoundError:
        return {}


_LOCAL = _local()


def setting(env: str, key: str, default=None):
    """environment variable > config.local.toml > default; empty values count as unset."""
    v = os.environ.get(env) or _LOCAL.get(key)
    return v if v not in (None, "") else default


def _dir(value) -> Path | None:
    return Path(value).expanduser().resolve() if value else None


BUILD_DIR = _dir(setting("STREETS_BUILD_DIR", "build_dir")) or ROOT / "build"
KNOWLEDGE = _dir(setting("STREETS_KNOWLEDGE_DIR", "knowledge_dir")) or ROOT / "knowledge"
KNOWLEDGE_REPO = setting("STREETS_KNOWLEDGE_REPO", "knowledge_repo", "https://github.com/straatwijsheid/knowledge.git")
GLOBAL = KNOWLEDGE / "global"        # curated lists that apply everywhere; per-gemeente knowledge is under KNOWLEDGE/gemeenten (see knowledge.py)
CONTACT = setting("WIKIDATA_CONTACT", "wikidata_contact")
OVERPASS_URL = setting("OVERPASS_URL", "overpass_url", "https://overpass-api.de/api/interpreter")
# The map's basemap. The OpenStreetMap tile policy asks sites not to hard-code the tile URL, so switching provider is a setting, not a code change.
TILE_URL = setting("TILE_URL", "tile_url", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
TILE_ATTRIBUTION = setting("TILE_ATTRIBUTION", "tile_attribution", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')

RAW, ENRICHED, OUTPUT, CACHE, NAMES = (BUILD_DIR / d for d in ("raw", "enriched", "output", "cache", "names"))


def rel(path) -> str:
    """A path for messages: relative to the repository when inside it, absolute otherwise (the build directory may be elsewhere)."""
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def ensure_dirs() -> None:
    """Create the build directories (scripts that write call this; reading scripts do not)."""
    for d in (RAW, ENRICHED, OUTPUT, CACHE, NAMES):
        d.mkdir(parents=True, exist_ok=True)


def describe() -> str:
    rows = [("repository", ROOT), ("build directory", BUILD_DIR), ("raw", RAW), ("enriched", ENRICHED), ("output", OUTPUT),
            ("cache", CACHE), ("names", NAMES), ("knowledge", KNOWLEDGE), ("knowledge repo", KNOWLEDGE_REPO), ("wikidata contact", "set" if CONTACT else "not set"), ("overpass", OVERPASS_URL), ("tiles", TILE_URL),
            ("local config", LOCAL_FILE if LOCAL_FILE.exists() else f"{LOCAL_FILE.name} not present")]
    return "\n".join(f"{k:18}{v}" for k, v in rows)


ensure_dirs()      # the build directory is created on first use


if __name__ == "__main__":
    print(describe())
