"""Run with: .venv/bin/python tests/test_rules.py   (no pytest needed)"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rules import audits, compound, directional, place_review, species, surnames, vocabulary   # noqa: E402
from rules.base import Context, core                                                             # noqa: E402


def row(g, s, cat, sub=None, label=None, source="claude_knowledge", desc=None, notes=None):
    return {"gemeente": g, "street": s, "category": cat, "subcategory": sub, "entity_label": label, "entity_description": desc,
            "confidence": 0.5, "source": source, "notes": notes}


def ctx(rows, buurten=None, wikidata=None, places=()):
    streets = [{"gemeente": r["gemeente"], "name": r["street"], "buurt": (buurten or {}).get((r["gemeente"], r["street"]), "B")} for r in rows]
    return Context(streets, rows, wikidata or {}, set(places))


def test_core():
    assert core("De Beukenlaan") == "Beuken" and core("Kerkstraat") == "Kerk" and core("Markt") == "Markt"


def test_vocabulary():
    c = vocabulary.classify
    m = c("X", "Mozartstraat")
    assert (m.category, m.subcategory, m.entity_label) == ("person", "musician_composer", "Wolfgang Amadeus Mozart")
    assert c("X", "Tulpstraat").subcategory == "flora_flower"
    assert c("X", "Sint Jorisstraat").subcategory == "religious"
    assert c("X", "Einsteinstraat").subcategory == "scientist"          # second layer
    assert c("X", "Kerkstraat") is None


def test_titles():
    t = vocabulary.classify_titles
    assert t("X", "Burgemeester Smitstraat").subcategory == "mayor_local"
    assert t("X", "Pastoor Janssenstraat").subcategory == "religious"
    assert t("X", "Jan Smitstraat").subcategory == "other"
    assert t("X", "Kerkstraat") is None


def test_directional():
    d = directional.classify
    o = d("X", "Eindhovensedijk", {"eindhoven"})
    assert (o.category, o.subcategory, o.entity_label) == ("place", "dutch_town", "Eindhoven")
    assert d("X", "Antwerpseweg", set()).subcategory == "foreign_town"
    assert d("X", "Kerkstraat", {"kerk"}) is None and d("X", "Zonderlingeweg", set()) is None


def test_species():
    en, la, stem = species.describe("Tulpstraat")
    assert (en, stem) == ("Tulip", "tulp") and species.describe("Zandstraat") is None
    assert species.description("Tulipa", "tulp") == "Tulipa; Dutch name 'tulp'"
    assert species.describe("De Acacia") is not None                    # leading article


def test_compound():
    assert compound.is_compound("Akkerstraat") and compound.is_compound("Kerkdijk")
    assert not compound.is_compound("Mozartstraat")


def test_bare_surname():
    rows = [row("A", "Molenstraat", "person", "unspecified_individual", source="wikidata_surname_only"),
            row("A", "Daltonstraat", "person", "unspecified_individual", source="wikidata_surname_only")]
    rows += [row("A", f"S{i}", "person", "scientist", f"Sci {i}") for i in range(3)]
    out = {o.street: o for o in surnames.resolve(ctx(rows))}
    assert out["Molenstraat"].category == "place" and out["Molenstraat"].subcategory == "local_landscape_feature"
    assert out["Daltonstraat"].entity_label == "John Dalton"
    # same famous surname in a buurt with no scientists: not asserted
    lone = [row("A", "Daltonstraat", "person", "unspecified_individual", source="wikidata_surname_only")]
    assert surnames.resolve(ctx(lone)) == []


def test_harmonise_same_name():
    rows = [row(f"G{i}", "Kerkstraat", "place", "local_landmark") for i in range(4)]
    rows.append(row("G9", "Kerkstraat", "thing", "fauna", source="buurt_theme_fallback"))
    out = audits.harmonise_same_name(ctx(rows))
    assert len(out) == 1 and out[0].gemeente == "G9" and out[0].category == "place"
    # a person majority is never harmonised by vote
    prow = [row(f"G{i}", "Willemstraat", "person", "monarch_statesman", "Willem") for i in range(4)] + [row("G9", "Willemstraat", "place", "local_landmark")]
    assert audits.harmonise_same_name(ctx(prow)) == []


def test_theme_forced():
    rows = [row("A", "Parklaan", "thing", "fauna", source="buurt_theme_fallback"),
            row("A", "Jan Smitstraat", "thing", "flora", source="buurt_theme_fallback"),
            row("A", "Pluvierlaan", "thing", "fauna", source="buurt_theme_fallback")]
    out = {o.street: o for o in audits.theme_forced(ctx(rows))}
    assert out["Parklaan"].subcategory == "local_landscape_feature"       # ordinary compound word
    assert out["Jan Smitstraat"].category == "person"                      # first name + surname
    assert "Pluvierlaan" not in out                                        # a bird word: the label is supported by the name


def test_place_review():
    rows = [row("A", "Brugstraat", "place", "town", "Bruges", source="wikidata", desc="city in Belgium"),
            row("A", "Berlinstraat", "place", "town", "Berlin", source="wikidata", desc="town in Maryland, United States"),
            row("A", "Venlostraat", "place", "city", "Venlo", source="wikidata", desc="city in Limburg, the Netherlands")]
    out = {o.street: o for o in place_review.review(ctx(rows))}
    assert out["Brugstraat"].subcategory == "local_landscape_feature"
    assert "not determined" in out["Berlinstraat"].entity_description or out["Berlinstraat"].entity_label == "Berlin"
    assert "Venlostraat" not in out


def test_saint_labels_drop_the_road_word():
    from rules import labels
    assert labels.saint_label("Saint Janstraat") == "Saint John"
    assert labels.saint_label("Saint Catharinaplein") == "Saint Catherine"
    assert labels.saint_label("Saint Pieterspark") == "Saint Peter"
    rows = [row("A", "Sint Janstraat", "person", "religious", "Saint Janstraat")]
    out = labels.repair_saint_labels(ctx(rows))
    assert len(out) == 1 and out[0].entity_label == "Saint John"
    assert labels.repair_saint_labels(ctx([row("A", "Sint Janstraat", "person", "religious", "Saint John")])) == []


def test_corrections_apply_to_existing_streets_only():
    from rules import corrections
    entries = corrections.entries()
    assert entries and all(e.get("reason") for e in entries)               # every correction says why
    streets = {(e["gemeente"], e["street"]) for e in entries}
    rows = [row(g, s, "place", "local_landscape_feature") for g, s in list(streets)[:3]]
    assert len(corrections.apply(ctx(rows))) == len(rows)                   # ones not present in the data are skipped


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f()
            print("ok  ", n)
        except Exception:
            fails += 1
            print("FAIL", n)
            traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} rule tests pass")
    sys.exit(1 if fails else 0)
