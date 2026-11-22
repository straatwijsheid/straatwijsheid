"""Override layers: order, exclusion, regeneration. Run with: .venv/bin/python tests/test_overrides.py"""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config
import overrides as O


def entry(street, label, g="G"):
    return {"gemeente": g, "street": street, "category": "person", "subcategory": "other", "entity_label": label, "entity_description": None,
            "confidence": 0.5, "source": "claude_knowledge", "source_url": None, "notes": None}


class Tmp:
    """Point the layer directories at a temporary folder."""
    def __enter__(self):
        self.d = tempfile.TemporaryDirectory()
        self.old = (config.KNOWLEDGE, config.ENRICHED)
        config.KNOWLEDGE, config.ENRICHED = Path(self.d.name) / "k", Path(self.d.name) / "e"
        return self

    def __exit__(self, *a):
        config.KNOWLEDGE, config.ENRICHED = self.old
        self.d.cleanup()


def test_later_layer_wins_and_exclude_upto():
    with Tmp():
        O.write_layer("legacy_hand", [entry("A", "hand"), entry("B", "hand")])
        O.write_layer("vocabulary", [entry("A", "vocab")])
        O.write_layer("corrections", [entry("A", "reviewed"), entry("C", "reviewed")])
        m = O.merged()
        assert m[("G", "A")]["entity_label"] == "reviewed" and m[("G", "B")]["entity_label"] == "hand" and ("G", "C") in m
        assert O.merged(exclude={"corrections"})[("G", "A")]["entity_label"] == "vocab"
        assert O.merged(upto="vocabulary")[("G", "A")]["entity_label"] == "hand"      # a rule sees only what ranks below it
        assert ("G", "C") not in O.merged(upto="vocabulary")


def test_diff_reports_regeneration():
    old = [entry("A", "x"), entry("B", "y"), entry("C", "z")]
    new = [entry("A", "x"), entry("B", "changed"), entry("D", "new")]
    assert O.diff(old, new) == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}


def test_layer_order_is_complete_and_legacy_first():
    assert O.LAYER_ORDER[0] == "legacy_hand" and O.LAYER_ORDER[-1] == "corrections"
    assert len(set(O.LAYER_ORDER)) == len(O.LAYER_ORDER)
    assert O.LAYER_ORDER.index("vocabulary") < O.LAYER_ORDER.index("species") < O.LAYER_ORDER.index("name_resolver")   # species refines vocabulary's output


def test_write_layer_is_deterministic():
    with Tmp():
        O.write_layer("vocabulary", [entry("B", "b"), entry("A", "a")])
        first = O.layer_path("vocabulary").read_text()
        O.write_layer("vocabulary", [entry("A", "a"), entry("B", "b")])
        assert first == O.layer_path("vocabulary").read_text()


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} override tests pass")
    sys.exit(1 if fails else 0)
