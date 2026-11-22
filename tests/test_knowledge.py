"""Knowledge sharding: slugs, province/gemeente paths, layer files per gemeente. Run with: .venv/bin/python tests/test_knowledge.py"""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import knowledge as K
import overrides as O
from _registry import write_registry

BERGEN_NH, BERGEN_L, EINDHOVEN = "GM0373", "GM0893", "GM0772"


class Tmp:
    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        self.old = config.KNOWLEDGE
        config.KNOWLEDGE = Path(self.d.name) / "k"
        write_registry({BERGEN_NH: ("Bergen", "Noord-Holland"), BERGEN_L: ("Bergen", "Limburg"), EINDHOVEN: ("Eindhoven", "Noord-Brabant")})   # two gemeenten, one name
        return self

    def __exit__(self, *a):
        config.KNOWLEDGE = self.old
        self.d.cleanup()


def e(code, street):
    return {"gemeente": {BERGEN_NH: "Bergen", BERGEN_L: "Bergen", EINDHOVEN: "Eindhoven"}[code], "gemeente_code": code, "street": street, "category": "person", "subcategory": None, "entity_label": "x", "entity_description": None, "confidence": 0.5,
            "source": "claude_knowledge", "source_url": None, "notes": None}


def test_slugs():
    assert K.slug("'s-Hertogenbosch") == "s-hertogenbosch" and K.slug("Fryslân") == "fryslan" and K.slug("Bergen op Zoom") == "bergen-op-zoom"


def test_province_first_path_and_same_name_gemeenten_do_not_collide():
    with Tmp():
        assert K.gemeente_dir(EINDHOVEN).parts[-2:] == ("noord-brabant", "eindhoven")
        assert K.gemeente_dir("Eindhoven") == K.gemeente_dir(EINDHOVEN)         # a unique name still resolves
        assert K.gemeente_dir(BERGEN_NH) != K.gemeente_dir(BERGEN_L)
        assert K.gemeente_dir(BERGEN_NH).parts[-2:] == ("noord-holland", "bergen") and K.gemeente_dir(BERGEN_L).parts[-2:] == ("limburg", "bergen")
        assert K.gemeente_dir("Unknown").parts[-2] == K.UNASSIGNED
        try:
            K.gemeente_dir("Bergen")                                           # the name alone cannot say which Bergen
            raise AssertionError("an ambiguous name must raise")
        except ValueError:
            pass


def test_layer_is_sharded_by_gemeente_and_stale_shards_are_removed():
    with Tmp():
        O.write_layer("vocabulary", [e(EINDHOVEN, "A"), e(BERGEN_NH, "B")])
        assert len(O.layer_files("vocabulary")) == 2 and len(O.load_layer("vocabulary")) == 2
        O.write_layer("vocabulary", [e(EINDHOVEN, "A")])
        assert len(O.layer_files("vocabulary")) == 1 and [o["street"] for o in O.load_layer("vocabulary")] == ["A"]


def test_same_named_gemeenten_keep_separate_entries_for_the_same_street():
    with Tmp():
        a, b = e(BERGEN_NH, "Kerkstraat"), e(BERGEN_L, "Kerkstraat")
        a["entity_label"], b["entity_label"] = "from Noord-Holland", "from Limburg"
        O.write_layer("legacy_hand", [a, b])
        assert len(O.layer_files("legacy_hand")) == 2
        m = O.merged()
        assert m[(BERGEN_NH, "Kerkstraat")]["entity_label"] == "from Noord-Holland" and m[(BERGEN_L, "Kerkstraat")]["entity_label"] == "from Limburg"
        stored = O.layer_path("legacy_hand", BERGEN_L).read_text()
        assert "gemeente_code" not in stored and '"gemeente": "Bergen"' in stored        # the shard is the code on disk; the name stays readable


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} knowledge tests pass")
    sys.exit(1 if fails else 0)
