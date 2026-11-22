"""Snapshots and OSM change detection. Run with: .venv/bin/python tests/test_snapshots.py"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import osm_changes as C
import snapshots as S


def way(i, name, **tags):
    return {"id": i, "tags": {"highway": "residential", "name": name, **tags}, "center": {"lat": 51.4, "lon": 5.4}}


def test_diff_added_changed_removed():
    old = [way(1, "A"), way(2, "B", **{"name:etymology:wikidata": "Q1"}), way(3, "C", wikidata="Q9")]
    new = [way(1, "A"), way(2, "B", **{"name:etymology:wikidata": "Q2"}), way(4, "D", **{"name:etymology:wikidata": "Q5"})]
    d = {c["way"]: c for c in C.diff_ways(old, new)}
    assert set(d) == {2, 3, 4}                                                      # way 1 is unchanged
    assert d[2]["change"] == "changed" and d[2]["old"]["name:etymology:wikidata"] == "Q1" and d[2]["new"]["name:etymology:wikidata"] == "Q2"
    assert d[3]["change"] == "removed" and d[4]["change"] == "added"


def test_irrelevant_tags_are_not_changes():
    old = [way(1, "A", surface="asphalt")]
    new = [way(1, "A", surface="paving_stones", maxspeed="30")]
    assert C.diff_ways(old, new) == []


def test_snapshot_record_dedupe_and_archive():
    with tempfile.TemporaryDirectory() as d:
        old = config.RAW
        config.RAW = Path(d)
        try:
            f = Path(d) / "x.json"
            f.write_text(json.dumps([{"id": 1}]))
            e1 = S.record("x", f, "test", rows=1)
            e1b = S.record("x", f, "test", rows=1)                                  # same bytes again: no second version
            assert len(S.history("x")) == 1 and e1["archive"] == e1b["archive"] and Path(d, "snapshots", "x").exists()
            f.write_text(json.dumps([{"id": 1}, {"id": 2}]))
            e2 = S.record("x", f, "test", rows=2)
            assert len(S.history("x")) == 2 and e2["sha256"] != e1["sha256"]
            prev = S.previous_archive("x", e2["sha256"])
            assert S.read_archive(prev) == [{"id": 1}]                              # the archive is what the next refresh compares with
            assert S.verify() is True
            f.write_text("tampered")
            assert S.verify() is False
        finally:
            config.RAW = old


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} snapshot tests pass")
    sys.exit(1 if fails else 0)
