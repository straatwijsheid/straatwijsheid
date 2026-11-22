"""A temporary gemeente registry for tests that build their own knowledge directory: `write_registry({"GM0001": ("G", "Province")})`."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import schema


def write_registry(entries: dict) -> None:
    """Write global/gemeenten_index.json under the (patched) config.KNOWLEDGE. entries: {code: (name, province)}."""
    p = config.KNOWLEDGE / "global" / "gemeenten_index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    (config.KNOWLEDGE / "schema_version").write_text(f"{schema.SCHEMA_VERSION}\n")
    p.write_text(json.dumps({"gemeenten": {c: {"name": n, "province": pr} for c, (n, pr) in entries.items()}}))
