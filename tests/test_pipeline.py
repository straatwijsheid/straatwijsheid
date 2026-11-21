"""Pipeline pieces that must work for any gemeente, not just the ones already in the data.
Run with: .venv/bin/python tests/test_pipeline.py"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import themes as T


def _fin(items):
    return {("G", s): {"category": c, "subcategory": sub, "entity_label": lab} for s, c, sub, lab in items}


def test_theme_single_mixed_unclear():
    b = {"gemeente": "G", "name": "B", "wijk": "W"}
    fin = _fin([("a", "person", "musician_composer", "Bach"), ("b", "person", "musician_composer", None), ("c", "person", "musician_composer", None),
                ("d", "person", "musician_composer", None), ("e", "thing", "flora", None)])
    t = T.derive(b, list("abcde"), fin)
    assert t["theme"] == "Mostly composers" and t["category"] == "person" and t["source"] == T.DERIVED and t["example_streets"][0] == "a"
    mixed = T.derive(b, list("abcde"), _fin([("a", "person", "musician_composer", None), ("b", "person", "musician_composer", None), ("c", "thing", "flora", None),
                                             ("d", "thing", "flora", None), ("e", "place", "river", None)]))
    assert mixed["category"] == "mixed" and "composers" in mixed["theme"]
    few = T.derive(b, ["a", "b"], fin)
    assert few["category"] == "unclear"


def test_themes_never_touch_hand_written(tmp=None):
    # run() rewrites only buurten without a theme; --rebuild drops only derived ones
    data = {"buurten": [{"gemeente": "G", "buurt": "B", "source": T.HAND}, {"gemeente": "G", "buurt": "C", "source": T.DERIVED}]}
    kept = [t for t in data["buurten"] if t.get("source") != T.DERIVED]
    assert [t["buurt"] for t in kept] == ["B"]


def test_acquire_config():
    import acquire
    cfg = acquire.CONFIG
    assert cfg["merged"]["Weesp"]["pdok"] == "Amsterdam" and cfg["merged"]["Weesp"]["buurt_prefix"].startswith("BU")
    assert cfg["aliases"]["Nuenen"]["pdok"] == "Nuenen, Gerwen en Nederwetten"
    assert acquire.slug("Bergen op Zoom") == "bergen-op-zoom"


def test_missing_street_names():
    import enrich_wikidata as E
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "c.jsonl"
        cache.write_text(json.dumps({"street": "Kerkstraat"}) + "\n")
        names = E.missing_street_names(cache)
        assert "Kerkstraat" not in names              # cached names are never looked up again
        assert names == sorted(set(names))


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} pipeline tests pass")
    sys.exit(1 if fails else 0)
