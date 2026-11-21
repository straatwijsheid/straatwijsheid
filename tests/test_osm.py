"""Run with: .venv/bin/python tests/test_osm.py"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import osm_etymology as O                      # noqa: E402
from osm_report import classify_pair, label_agrees   # noqa: E402
from rules import osm                          # noqa: E402
from rules.base import Context                 # noqa: E402


def ent(p31=(), p106=(), desc="", ):
    claim = lambda ids: [{"mainsnak": {"datavalue": {"value": {"id": i}}}} for i in ids]
    return {"claims": {"P31": claim(p31), "P106": claim(p106)}, "descriptions": {"en": {"value": desc}}}


def row(g, s, cat, sub=None, label=None, source="claude_knowledge"):
    return {"gemeente": g, "street": s, "category": cat, "subcategory": sub, "entity_label": label, "entity_description": None,
            "confidence": 0.5, "source": source, "notes": None}


def test_classify_entity():
    assert O.classify_entity(ent(["Q5"], ["Q1028181"])) == ("person", "artist_visual")
    assert O.classify_entity(ent(["Q5"], [], "Dutch king")) == ("person", "monarch_statesman")
    assert O.classify_entity(ent(["Q5"], ["Q999"])) == ("person", "other")
    assert O.classify_entity(ent([], [], "village in North Brabant, the Netherlands")) == ("place", "dutch_town")
    assert O.classify_entity(ent([], [], "river in France"))[1] == "river"
    assert O.classify_entity(ent(["Q16521"], [], "species of bird")) == ("thing", "fauna")
    assert O.classify_entity(ent([], [], "something unrecognisable")) == (None, None)


def _ctx(rows):
    return Context([{"gemeente": r["gemeente"], "name": r["street"], "buurt": "b", "wijk": None} for r in rows], rows, {}, set())


def rec(g, s, cat, sub, label, qid="Q1"):
    return {"gemeente": g, "street": s, "via": "name:etymology:wikidata", "ways": 1, "text": [],
            "items": [{"qid": qid, "label": label, "description": "d", "category": cat, "subcategory": sub}]}


def test_pairing_and_rule():
    rows = [row("A", "Zzstraat", "place", "local_landscape_feature"),                          # tier 5 -> new information
            row("A", "Vermeerstraat", "person", "artist_visual", None),                         # tier 3, agrees -> named
            row("A", "Rembrandtlaan", "person", "artist_visual", "Rembrandt van Rijn", source="wikidata"),  # tier 1 agrees -> nothing to do
            row("A", "Frederiklaan", "person", "musician_composer", "Frederik", source="wikidata"),     # tier 1 but a bare first name vs the OSM item -> OSM wins
            row("A", "Clashlaan", "person", "artist_visual", "Someone")]                        # tier 2 vs a place -> conflict
    recs = [rec("A", "Zzstraat", "person", "writer_poet", "Some Writer"), rec("A", "Vermeerstraat", "person", "artist_visual", "Johannes Vermeer"),
            rec("A", "Rembrandtlaan", "person", "artist_visual", "Rembrandt van Rijn"), rec("A", "Clashlaan", "place", "dutch_town", "Clash"), rec("A", "Frederiklaan", "person", "industrialist", "Frederik Philips", "Q1453131")]
    ctx = _ctx(rows)
    assert classify_pair(ctx.rows[("A", "Clashlaan")], recs[3])[0] == "conflict"
    out = {o.street: o for o in osm.propose(ctx, recs)}
    assert set(out) == {"Zzstraat", "Vermeerstraat", "Frederiklaan"}                      # tier-1 agreement and the conflict are left alone
    assert out["Vermeerstraat"].source == "osm_etymology" and out["Vermeerstraat"].entity_label == "Johannes Vermeer"
    assert out["Zzstraat"].category == "person"
    assert out["Frederiklaan"].entity_label == "Frederik Philips" and out["Frederiklaan"].subcategory == "industrialist"


def test_label_agreement():
    assert label_agrees("Vincent van Gogh", "Vincent Willem van Gogh") and not label_agrees("Beech", "Oak")


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} osm tests pass")
    sys.exit(1 if fails else 0)
