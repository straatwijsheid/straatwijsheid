"""Run a test against the golden fixture's build data instead of the real build directory: `with fixture_build(): ...`"""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config

FIX = Path(__file__).resolve().parent / "fixture"


@contextlib.contextmanager
def fixture_build():
    old = config.RAW, config.ENRICHED
    config.RAW, config.ENRICHED = FIX / "build" / "raw", FIX / "build" / "enriched"
    try:
        yield
    finally:
        config.RAW, config.ENRICHED = old
