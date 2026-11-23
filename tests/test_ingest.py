"""Review-sheet answers -> corrections, and the pull-request checks.
Run with: .venv/bin/python tests/test_ingest.py"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import _need_knowledge  # noqa: F401
import ingest_answers as I
import review_sheet as RS


def _row(street, sub="musician_composer"):
    return {"gemeente_code": "GM0772", "street": street, "buurt": "B", "category": "person", "subcategory": sub, "evidence_tier": 3,
            "entity_label": None, "buurt_theme": "Composers", "source": "claude_knowledge"}


def _sheet(rows, answers):
    return RS.render("Eindhoven", RS.candidates(rows, "GM0772"), {}, [], answers)


def test_parse():
    a = I.parse("Jan Ban, organist https://nl.wikipedia.org/wiki/Jan_Ban.")
    assert (a.kind, a.name, a.description, a.url) == ("namesake", "Jan Ban", "organist", "https://nl.wikipedia.org/wiki/Jan_Ban")
    assert I.parse("Banstraat = Jan Ban, organist", "Banstraat").name == "Jan Ban"
    assert I.parse("waarschijnlijk Jan Ban, organist").kind == "guess" and I.parse("Jan Ban?").kind == "guess"
    w = I.parse("fout: dit is een plant")
    assert w.kind == "wrong" and w.description == "dit is een plant" and I.parse("wrong, a plant").kind == "wrong"
    assert I.parse("???").kind == "unclear" and I.parse("").kind == "unclear"


def test_triage_accepts_only_what_it_can_stand_behind():
    rows = [_row("Banstraat"), _row("Cortstraat"), _row("Dorpstraat"), _row("Eikenlaan"), _row("Fokstraat")]
    answers = {"Banstraat": "Jan Ban, organist", "Cortstraat": "probably Piet Cort", "Dorpstraat": "wrong: a village",
               "Eikenlaan": "Eik, schilder https://www.wikidata.org/wiki/Q1", "Oudstraat": "Jan Oud"}
    res = {s: (o, c) for s, a, o, c in I.triage("GM0772", rows, _sheet(rows, answers), corrected={"Eikenlaan"})}
    assert res["Banstraat"][0] == "accept"
    c = res["Banstraat"][1]
    assert (c["category"], c["subcategory"], c["entity_label"], c["confidence"]) == ("person", "musician_composer", "Jan Ban", 0.7)
    assert "unverified" in c["reason"] and "source_url" not in c                        # no link: local knowledge, tier 2 at most
    assert res["Cortstraat"][0].startswith("skip: a guess") and res["Dorpstraat"][0].startswith("maintainer")
    assert res["Eikenlaan"][0] == "skip: already has a correction"
    assert res["Oudstraat"][0].startswith("skip: not asked")                           # an answer for a street the sheet no longer lists
    assert "Fokstraat" not in res                                                       # unanswered


def test_a_source_link_is_recorded_but_stays_a_correction():
    rows = [_row("Banstraat", sub="specific")]
    (_, _, outcome, c), = I.triage("GM0772", rows, _sheet(rows, {"Banstraat": "Jan Ban, organist https://www.wikidata.org/wiki/Q9"}), set())
    assert outcome == "accept" and c["source_url"].endswith("Q9") and c["confidence"] == 0.8 and c["subcategory"] == "other"


def test_pull_request_check_allows_only_answers():
    rows = [_row("Banstraat"), _row("Cortstraat")]
    base = _sheet(rows, {})
    good = base.replace("| Banstraat | musician composer | 3 |  | |", "| Banstraat | musician composer | 3 |  | Jan Ban, organist |")
    assert good != base and I.check_sheet(base, good) == ([], ["Banstraat: no source link; it will be recorded as local knowledge, unverified (tier 2)"])
    assert I.check_sheet(base, good.replace("\n", "\r\n"))[0] == []                      # line endings do not matter
    def bad(head, *words):
        errs = I.check_sheet(base, head)[0]
        assert errs and all(any(w in e for e in errs) for w in words), (errs, words)
    bad(good.replace("| Cortstraat | musician composer |", "| Cortstraat | painter |"), "outside the answer column", "Cortstraat")
    bad(good.replace("| Cortstraat | musician composer | 3 |  | |\n", ""), "removed")
    bad(good + "| Nieuwstraat | x | 3 |  | iets |\n", "added")
    bad(good.replace("| Banstraat |", "| Banstrat |"), "Banstrat")                       # a respelled street
    bad(good.replace("### B (Eindhoven)", "### Bb (Eindhoven)"), "outside the answer column")   # a heading is an anchor
    bad(good.replace("|---|---|---|---|---|", "|---|---|---|---|"), "outside the answer column")   # a butchered separator
    bad(good.replace("Streets read", "Strets read").replace("Welkom", "Hallo"), "outside the answer column")
    bad(good.replace("| Cortstraat | musician composer | 3 |  | |", "| Cortstraat | musician composer | 3 | | |  | x |"), "columns")
    bad(base.replace("| Banstraat | musician composer | 3 |  | |", "| Banstraat | musician composer | 3 |  | 12 |"), "could not read")


def test_a_row_that_lost_a_cell_gives_no_answer():
    rows = [_row("Banstraat")]
    text = _sheet(rows, {}).replace("| Banstraat | musician composer | 3 |  | |", "| Banstraat | musician composer | 3 | wrong column |")
    assert RS.parse_answers(text) == {} and RS.malformed(text)[0][1] == "Banstraat"        # not read as the answer "wrong column"
    stray = _sheet(rows, {}) + "\n| Banstraat | musician composer | 3 |  | stiekem |\n"
    assert RS.parse_answers(stray) == {}                                                    # a row outside any table is not an answer
    assert I.check_sheet(_sheet(rows, {}), stray)[0]                                         # and the check refuses it


def test_corrections_checked():
    ok = {"corrections": [{"gemeente": "G", "street": "S", "category": "person", "subcategory": "writer_poet", "entity_label": "X", "confidence": 0.7, "reason": "r"}]}
    assert I.check_corrections(json.dumps(ok)) == []
    bad = {"corrections": [{"gemeente": "G", "street": "S", "category": "animal", "confidence": 2}]}
    errs = I.check_corrections(json.dumps(bad))
    assert any("missing reason" in e for e in errs) and any("category must" in e for e in errs) and any("confidence" in e for e in errs)
    assert I.check_corrections("{nope")[0].startswith("not valid JSON")


def test_a_settled_answer_leaves_the_sheet():
    rows = [_row("Cortstraat")]
    gone = RS.render("Eindhoven", RS.candidates(rows, "GM0772"), {}, [], {"Banstraat": "Jan Ban"}, settled={"Banstraat"})
    kept = RS.render("Eindhoven", RS.candidates(rows, "GM0772"), {}, [], {"Banstraat": "Jan Ban"})
    assert "Banstraat" not in gone and "Banstraat" in kept          # once in corrections.json, an answer no longer needs keeping


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} ingest tests pass")
    sys.exit(1 if fails else 0)
