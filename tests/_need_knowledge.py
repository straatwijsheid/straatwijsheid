"""Import first in a test that reads the curated knowledge lists (vocabulary, species, famous people, ...): stops with a clear message when the
knowledge repository is not checked out (run `python src/pipeline.py bootstrap`, or point knowledge_dir at a checkout)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config

if not (config.GLOBAL / "vocabulary.json").exists():
    sys.exit(f"This test needs the knowledge repository at {config.KNOWLEDGE} (run: python src/pipeline.py bootstrap; or set knowledge_dir in config.local.toml).")
