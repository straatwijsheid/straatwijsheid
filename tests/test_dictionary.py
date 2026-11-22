"""The data dictionary (docs/data-dictionary.md) is generated from the code and must match it and the data.
Run with: .venv/bin/python tests/test_dictionary.py"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import _need_knowledge  # noqa: F401  (the rules and the knowledge file list are read from the checkout)

import dictionary  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixture"


def test_the_document_is_up_to_date():
    assert dictionary.check_doc(), "docs/data-dictionary.md is out of date: run python src/dictionary.py --write"


def test_code_and_dictionary_agree():
    assert dictionary.verify_code() == []


def test_the_golden_classification_is_fully_described():
    records = json.loads((FIX / "expected_final.json").read_text())
    assert dictionary.verify_records(records) == []


def test_verification_catches_an_undocumented_field_or_value():
    bad = [{"street": "X", "category": "person", "subcategory": "no_such_kind", "source": "no_such_source", "way_class": "street", "mystery": 1}]
    found = " ".join(dictionary.verify_records(bad))
    assert "mystery" in found and "no_such_kind" in found and "no_such_source" in found


def test_every_tier_and_documented_field_has_a_meaning():
    import tiers
    assert set(tiers.TIER_NAMES) == {1, 2, 3, 4, 5}
    for fields in (dictionary.STREET_FIELDS, dictionary.THEME_FIELDS, dictionary.LAYER_FIELDS, dictionary.CORRECTION_FIELDS, dictionary.RAW_FIELDS):
        assert all(t and m for t, m in fields.values())


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} dictionary tests pass")
    sys.exit(1 if fails else 0)
