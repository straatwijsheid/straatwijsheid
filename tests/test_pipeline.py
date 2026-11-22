"""Pipeline pieces that must work for any gemeente, not just the ones already in the data.
Run with: .venv/bin/python tests/test_pipeline.py"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import _need_knowledge  # noqa: F401  (stops with a clear message when the knowledge repository is not checked out)
from _fixture import fixture_build
import themes as T


def _fin(items):
    return {("G", s): {"category": c, "subcategory": sub, "entity_label": lab} for s, c, sub, lab in items}


def test_theme_single_mixed_unclear():
    b = {"gemeente": "G", "gemeente_code": "G", "name": "B", "wijk": "W"}
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
    assert acquire.file_key("GM0758") == "gm0758"                  # raw files are named by CBS code, not by name


def test_missing_street_names():
    import enrich_wikidata as E
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "c.jsonl"
        cache.write_text(json.dumps({"street": "Kerkstraat"}) + "\n")
        with fixture_build():
            names = E.missing_street_names(cache)
        assert "Kerkstraat" not in names              # cached names are never looked up again
        assert names == sorted(set(names))


def test_config_precedence_and_build_dir():
    import os
    import subprocess
    import config
    old_local, old_env = dict(config._LOCAL), os.environ.get("TEST_SETTING")
    try:
        config._LOCAL.clear()
        config._LOCAL["k"] = "from-file"
        os.environ.pop("TEST_SETTING", None)
        assert config.setting("TEST_SETTING", "k", "dflt") == "from-file"          # file beats default
        os.environ["TEST_SETTING"] = "from-env"
        assert config.setting("TEST_SETTING", "k", "dflt") == "from-env"           # environment beats file
        os.environ["TEST_SETTING"] = ""
        assert config.setting("TEST_SETTING", "missing", "dflt") == "dflt"         # empty counts as unset
    finally:
        config._LOCAL.clear(); config._LOCAL.update(old_local)
        os.environ.pop("TEST_SETTING", None)
        if old_env is not None:
            os.environ["TEST_SETTING"] = old_env
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, STREETS_BUILD_DIR=d, WIKIDATA_CONTACT="secret@example.org")
        out = subprocess.run([sys.executable, str(Path(config.__file__)), ], env=env, capture_output=True, text=True, check=True).stdout
        assert f"{Path(d).resolve()}/raw" in out and "enriched" in out and (Path(d) / "raw").is_dir()   # build dir is created and used
        assert "secret@example.org" not in out and "set" in out                                         # the contact is never printed


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
