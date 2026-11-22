"""Knowledge sharding: slugs, province/gemeente paths, layer files per gemeente. Run with: .venv/bin/python tests/test_knowledge.py"""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import knowledge as K
import overrides as O


class Tmp:
    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        self.old = config.KNOWLEDGE
        config.KNOWLEDGE = Path(self.d.name) / "k"
        K.write_json(K.global_dir() / "provinces.json", {"provinces": {"Bergen": "Noord-Holland", "Bergen (L)": "Limburg", "Eindhoven": "Noord-Brabant"}})
        return self

    def __exit__(self, *a):
        config.KNOWLEDGE = self.old
        self.d.cleanup()


def e(g, street):
    return {"gemeente": g, "street": street, "category": "person", "subcategory": None, "entity_label": "x", "entity_description": None, "confidence": 0.5,
            "source": "claude_knowledge", "source_url": None, "notes": None}


def test_slugs():
    assert K.slug("'s-Hertogenbosch") == "s-hertogenbosch" and K.slug("Fryslân") == "fryslan" and K.slug("Bergen op Zoom") == "bergen-op-zoom"


def test_province_first_path_and_same_name_gemeenten_do_not_collide():
    with Tmp():
        assert K.gemeente_dir("Eindhoven").parts[-2:] == ("noord-brabant", "eindhoven")
        assert K.gemeente_dir("Bergen") != K.gemeente_dir("Bergen (L)")
        assert K.gemeente_dir("Unknown").parts[-2] == K.UNASSIGNED


def test_layer_is_sharded_by_gemeente_and_stale_shards_are_removed():
    with Tmp():
        O.write_layer("vocabulary", [e("Eindhoven", "A"), e("Bergen", "B")])
        assert len(O.layer_files("vocabulary")) == 2 and len(O.load_layer("vocabulary")) == 2
        O.write_layer("vocabulary", [e("Eindhoven", "A")])
        assert len(O.layer_files("vocabulary")) == 1 and [o["street"] for o in O.load_layer("vocabulary")] == ["A"]


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
