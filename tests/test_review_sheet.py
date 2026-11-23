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
