"""Review sheets: regenerating keeps contributors' answers.
Run with: .venv/bin/python tests/test_review_sheet.py"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import review_sheet as R


def _row(street, buurt="B", sub="musician_composer", tier=3, label=None, theme="Composers"):
    return {"gemeente_code": "GM1", "street": street, "buurt": buurt, "category": "person", "subcategory": sub,
            "evidence_tier": tier, "entity_label": label, "buurt_theme": theme}


def _sheet(rows, answers=None, notes=None, extra=()):
    return R.render("G", R.candidates(rows, "GM1"), notes or {}, list(extra), answers or {})


def test_only_unidentified_people_are_asked_about():
    rows = [_row("Banstraat"), _row("Bachstraat", label="Bach"), _row("Eikenlaan", tier=2), _row("Dennenlaan", tier=3)]
    rows[3]["category"] = "thing"
    assert set(R.candidates(rows, "GM1")["B"][i]["street"] for i in range(len(R.candidates(rows, "GM1")["B"]))) == {"Banstraat"}
    assert R.candidates(rows, "GM2") == {}


def test_answers_survive_regeneration():
    rows = [_row("Banstraat"), _row("Cortstraat")]
    first = _sheet(rows)
    typed = first.replace("| Banstraat | musician composer | 3 |  | |", "| Banstraat | musician composer | 3 |  | Jan Ban, organist |")
    assert typed != first and R.parse_answers(typed) == {"Banstraat": "Jan Ban, organist"}
    again = _sheet(rows, R.parse_answers(typed))
    assert again == typed                                              # regenerating changes nothing
    assert _sheet(rows + [_row("Dorpstraat")], R.parse_answers(typed)).count("| Jan Ban, organist |") == 1


def test_answer_for_a_street_no_longer_listed_is_kept():
    rows = [_row("Banstraat"), _row("Cortstraat")]
    ans = {"Banstraat": "Jan Ban", "Cortstraat": "wrong: a plant"}
    text = _sheet([_row("Cortstraat")], ans)                          # Banstraat was identified meanwhile
    assert R.ORPHANS in text and R.parse_answers(text) == ans
    assert _sheet([_row("Cortstraat")], R.parse_answers(text)) == text      # stable on the next round
    back = _sheet(rows, R.parse_answers(text))                         # and it returns to its place if it is asked about again
    assert R.ORPHANS not in back and R.parse_answers(back) == ans


def test_pipe_in_text_cannot_break_the_table():
    text = _sheet([_row("Banstraat")], {"Banstraat": "a | b"}, notes={"Banstraat": "x | y"})
    assert R.parse_answers(text) == {"Banstraat": "a / b"}


def test_further_checks_keep_answers():
    x = {"street": "Eikenlaan", "buurt": "B", "question": "A tree, or a person?"}
    text = _sheet([], {"Eikenlaan": "a tree"}, extra=[x])
    assert "Further checks" in text and R.parse_answers(text) == {"Eikenlaan": "a tree"}


def test_sections_and_each_street_once():
    rows = [_row("Banstraat")]
    held = {"places": [("Lindenlaan", "place: city (Linden)", "place: foreign town", "n"), ("Banstraat", "x", "y", "")],
            "surnames": [("Molen", "person", "place: local", "")]}
    themed = [dict(_row("Dorpstraat", tier=4), source="buurt_theme_fallback", category="place", subcategory="foreign_town"), _row("Banstraat")]
    text = R.render("G", R.candidates(rows, "GM1"), {}, [], {"Molen": "een molen", "Lindenlaan": "ja"}, held, themed)
    assert text.count("| Banstraat |") == 1                                                 # asked in the first section only
    for title in (R.S_PERSONS[0], R.S_PLACES[0], R.S_SURNAMES[0], R.S_THEME[0]):
        assert f"## {title}" in text
    assert R.parse_answers(text) == {"Molen": "een molen", "Lindenlaan": "ja"} and R.ORPHANS not in text
    assert "Uw antwoord (Your answer)" in text and "Welkom!" in text


def test_old_english_sheet_still_parses():
    old = "| Street | We read it as | Tier | Our note | Your answer |\n|---|---|---|---|---|\n| Banstraat | composer | 3 |  | Jan Ban |\n"
    assert R.parse_answers(old) == {"Banstraat": "Jan Ban"}


def test_placements_match_github_anchors_and_the_sheet():
    assert R.anchor("Generalenbuurt (Eindhoven)") == "generalenbuurt-eindhoven"
    assert R.anchor("Is dit wel een plaats? (Is this really a place?)") == "is-dit-wel-een-plaats-is-this-really-a-place"
    seen = {}
    assert [R.anchor("Zuid", seen), R.anchor("Zuid", seen)] == ["zuid", "zuid-1"]
    rows = [_row("Banstraat", buurt="Noord"), _row("Cortstraat", buurt="Zuid")]
    held = {"places": [("Lindenlaan", "a", "b", "")], "surnames": []}
    text = R.render("G", R.candidates(rows, "GM1"), {}, [], {"Oudstraat": "een antwoord"}, held, [])
    assert R.placements(text) == {"Banstraat": "noord-g", "Cortstraat": "zuid-g",
                                  "Lindenlaan": "is-dit-wel-een-plaats-is-this-really-a-place"}   # an answer-only street is not asked about


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} review sheet tests pass")
    sys.exit(1 if fails else 0)
