"""Gemeente identity: the CBS code is the key, the name is for display; two same-named gemeenten coexist in one build.
Run with: .venv/bin/python tests/test_gemeenten.py"""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import gemeenten
import overrides as O
import reconcile
from _registry import write_registry
from rules.base import Context, Override

NH, L = "GM0373", "GM0893"          # Bergen (Noord-Holland) and Bergen (Limburg): both are called "Bergen"


class Tmp:
    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        self.old = config.KNOWLEDGE
        config.KNOWLEDGE = Path(self.d.name) / "k"
        write_registry({NH: ("Bergen", "Noord-Holland"), L: ("Bergen", "Limburg"), "GM0772": ("Eindhoven", "Noord-Brabant")})
        return self

    def __exit__(self, *a):
        config.KNOWLEDGE = self.old
        self.d.cleanup()


def test_resolution_by_code_and_name():
    with Tmp():
        assert gemeenten.code_of("Eindhoven") == "GM0772" and gemeenten.code_of("GM0772") == "GM0772"
        assert gemeenten.name_of(NH) == gemeenten.name_of(L) == "Bergen"
        assert gemeenten.province_of(NH) == "Noord-Holland" and gemeenten.province_of(L) == "Limburg"
        assert gemeenten.codes_for("Bergen") == [NH, L]
        assert gemeenten.known("Nowhere") is None
        for bad in ("Bergen",):
            try:
                gemeenten.code_of(bad)
                raise AssertionError("an ambiguous name must raise")
            except ValueError as e:
                assert NH in str(e) and L in str(e)                      # the error names the codes to choose from
        try:
            gemeenten.code_of("GM9999")
            raise AssertionError("an unregistered code must raise")
        except KeyError:
            pass


def test_register_is_idempotent_and_never_overwrites():
    with Tmp():
        gemeenten.register("GM0001", "Test", "Groningen")
        gemeenten.register("GM0001", "Renamed", "Drenthe")
        assert gemeenten.name_of("GM0001") == "Test" and gemeenten.province_of("GM0001") == "Groningen"
        gemeenten.register("GM0002", "Old", "Limburg", historic=True)
        assert gemeenten.index()["GM0002"]["historic"] is True
        try:
            gemeenten.register("Bergen", "x", "y")
            raise AssertionError("not a code")
        except ValueError:
            pass


def test_the_real_registry_is_consistent():
    """The curated registry in the knowledge repository (skipped without the checkout): unique codes, a province each, a slug-unique shard per gemeente."""
    import _need_knowledge  # noqa: F401
    import knowledge
    idx = gemeenten.index()
    assert idx and all(gemeenten.is_code(c) for c in idx)
    assert all(v["name"] and v["province"] for v in idx.values())
    dirs = [knowledge.gemeente_dir(c) for c in idx]
    assert len(set(dirs)) == len(dirs)                                   # no two gemeenten share a shard directory


def test_reconcile_keeps_same_named_gemeenten_apart():
    """The same street name in both Bergens gets its own buurt theme and its own override, keyed by code."""
    wikidata = [{"street": "Kerkstraat", "category": "place", "subcategory": "local_landmark", "confidence": 0.3, "source": "wikidata"}]
    context = {"Kerkstraat": [{"gemeente": "Bergen", "gemeente_code": NH, "buurt": "Centrum"}, {"gemeente": "Bergen", "gemeente_code": L, "buurt": "Centrum"}]}
    themes = {(NH, "Centrum"): {"theme": "Churches", "category": "place", "confidence": 0.8},
              (L, "Centrum"): {"theme": "Composers", "category": "person", "confidence": 0.8}}
    final = reconcile.reconcile(wikidata, context, themes)
    by = {r["gemeente_code"]: r for r in final}
    assert len(final) == 2 and set(by) == {NH, L}
    assert by[NH]["buurt_theme"] == "Churches" and by[L]["buurt_theme"] == "Composers"      # a name-keyed lookup would give both the same theme


def test_overrides_apply_per_code_through_the_whole_chain():
    with Tmp():
        def entry(code, label):
            return {"gemeente": "Bergen", "gemeente_code": code, "street": "Kerkstraat", "category": "person", "subcategory": "other", "entity_label": label,
                    "entity_description": None, "confidence": 0.5, "source": "claude_knowledge", "source_url": None, "notes": None}
        O.write_layer("legacy_hand", [entry(NH, "Noord-Holland namesake"), entry(L, "Limburg namesake")])
        rows = [{"street": "Kerkstraat", "gemeente": "Bergen", "gemeente_code": c, "category": "place", "subcategory": "local_landmark", "entity_label": None,
                 "entity_description": None, "confidence": 0.3, "source": "wikidata"} for c in (NH, L)]
        out = {r["gemeente_code"]: r for r in reconcile.apply_manual_overrides(rows)}
        assert out[NH]["entity_label"] == "Noord-Holland namesake" and out[L]["entity_label"] == "Limburg namesake"


def test_override_record_carries_name_and_code():
    with Tmp():
        rec = Override(L, "Kerkstraat", "place", "local_landmark").record()
        assert rec["gemeente"] == "Bergen" and rec["gemeente_code"] == L and "rule" not in rec


def test_context_separates_same_named_gemeenten():
    rows = [{"gemeente": "Bergen", "gemeente_code": c, "street": "Kerkstraat", "category": "place", "subcategory": "local_landmark", "entity_label": None,
             "source": "x"} for c in (NH, L)]
    streets = [{"gemeente_code": NH, "name": "Kerkstraat", "buurt": "A", "wijk": None}, {"gemeente_code": L, "name": "Kerkstraat", "buurt": "B", "wijk": None}]
    ctx = Context(streets, rows, {}, set())
    assert ctx.buurt(rows[0]) == (NH, "A") and ctx.buurt(rows[1]) == (L, "B")
    assert set(ctx.rows) == {(NH, "Kerkstraat"), (L, "Kerkstraat")}


def test_migrate_codes_renames_files_and_keeps_snapshot_history():
    import geopandas as gpd
    import acquire
    import snapshots
    from shapely.geometry import Point
    with Tmp(), tempfile.TemporaryDirectory() as d:
        old = config.RAW, acquire.RAW_DIR
        config.RAW = acquire.RAW_DIR = Path(d)
        try:
            for kind in ("streets", "buurten"):
                gpd.GeoDataFrame({"name": ["Kerkstraat"], "gemeente": ["Eindhoven"], "buurt": ["B"], "wijk": ["W"]}, geometry=[Point(5.4, 51.4)],
                                 crs="EPSG:4326").to_file(Path(d) / f"{kind}_eindhoven.geojson", driver="GeoJSON")
            snapshots.record("streets/eindhoven", Path(d) / "streets_eindhoven.geojson", "test", archive=False, fetched_at="2026-01-01T00:00:00Z")
            acquire.migrate_codes()
            assert sorted(p.name for p in Path(d).glob("streets_*.geojson")) == ["streets_gm0772.geojson"]
            assert not (Path(d) / "streets_eindhoven.geojson").exists()
            assert list(gpd.read_file(Path(d) / "streets.geojson")["gemeente_code"]) == ["GM0772"]
            hist = snapshots.history("streets/gm0772")
            assert len(hist) == 2 and hist[0]["fetched_at"] == "2026-01-01T00:00:00Z" and snapshots.history("streets/eindhoven") == []   # history moved, not lost
            assert snapshots.verify()
            acquire.migrate_codes()                                               # idempotent
            assert len(snapshots.history("streets/gm0772")) == 2
        finally:
            config.RAW, acquire.RAW_DIR = old


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} gemeente-identity tests pass")
    sys.exit(1 if fails else 0)
