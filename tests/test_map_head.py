"""Run with: .venv/bin/python tests/test_map_head.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import build_map

h = build_map.seo_head()
assert '<meta name="description"' in h and 'rel="canonical" href="https://maps.straatwijsheid.nl/"' in h
assert 'property="og:image" content="https://straatwijsheid.nl/og.png"' in h
assert "twitter" not in h.lower()
assert '"' not in build_map.MAP_DESCRIPTION           # would break the attribute if unescaped
print("ok")
