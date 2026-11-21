"""Run with: .venv/bin/python tests/test_names.py"""
import collections
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from names import candidates as C, resolve as R      # noqa: E402
from rules.base import Context                          # noqa: E402


def row(g, s, cat, sub=None, label=None, source="claude_knowledge", notes=None):
    return {"gemeente": g, "street": s, "category": cat, "subcategory": sub, "entity_label": label, "entity_description": None,
            "confidence": 0.5, "source": source, "notes": notes}


def ctx_of(rows, buurt_of, wijk_of=None):
    streets = [{"gemeente": r["gemeente"], "name": r["street"], "buurt": buurt_of[(r["gemeente"], r["street"])],
                "wijk": (wijk_of or {}).get((r["gemeente"], r["street"]))} for r in rows]
    return Context(streets, rows, {}, set())


def test_name_key():
    assert C.name_key("De Beukenlaan") == C.name_key("Beukenstraat") == "beuken"
    assert C.name_key("Van der Waalsstraat") == "van der waals"


def test_table_candidates_and_mass():
    rows = [row("A", "Willemstraat", "person", "monarch_statesman", "Willem"), row("B", "Willemlaan", "person", "monarch_statesman", "Willem"),
            row("C", "Willemstraat", "person", "politician_statesman", "Willem Drees")]
    ctx = ctx_of(rows, {(r["gemeente"], r["street"]): f"b{r['gemeente']}" for r in rows})
    t = C.build_table(ctx, rules=False)
    e = t["willem"] if "willem" in t else t["willems"]
    assert set(e.candidates) >= {("person", "monarch_statesman"), ("person", "politician_statesman")}
    mon, pol = e.candidates[("person", "monarch_statesman")], e.candidates[("person", "politician_statesman")]
    assert mon.mass() > pol.mass()
    assert mon.mass(exclude=("A", "Willemstraat")) < mon.mass()                  # leave-one-out removes that street's own evidence
    assert mon.mass(gemeente="A") < mon.mass()


def _ambiguous_world():
    rows, buurt = [], {}
    def add(r, b):
        rows.append(r); buurt[(r["gemeente"], r["street"])] = b
    for i, g in enumerate("ABC"):                                   # three places where Willemstraat is a royal
        add(row(g, "Willemstraat", "person", "monarch_statesman", "Willem (House of Orange)"), f"roy{g}")
    for g in "DEF":                                                  # three where it is a politician
        add(row(g, "Willemstraat", "person", "politician_statesman", "Willem Drees"), f"pol{g}")
    for i in range(4):                                               # buurt "newroy": royals; buurt "newpol": politicians
        add(row("N", f"Prinsenstraat{i}", "person", "monarch_statesman", f"Prins {i}"), "newroy")
        add(row("N", f"Staatsliedenstraat{i}", "person", "politician_statesman", f"Staatsman {i}"), "newpol")
    add(row("N", "Willemstraat", "person", None, None, source="wikidata_weak_match") | {"category": "unresolved"}, "newroy")
    return ctx_of(rows, buurt)


def test_context_picks_the_reading_the_buurt_supports():
    ctx = _ambiguous_world()
    table = C.build_table(ctx, rules=False)
    idx = R.ContextIndex(ctx)
    entry = table[C.name_key("Willemstraat")]
    street = ctx.rows[("N", "Willemstraat")]
    res_roy = R.resolve_street(entry, *idx.counters(street))
    assert res_roy.kind == ("person", "monarch_statesman"), res_roy
    # the same name in a politicians' buurt resolves the other way
    pol_buurt = R.ContextIndex(ctx).buurt[("N", "newpol")]
    res_pol = R.resolve_street(entry, pol_buurt, collections.Counter())
    assert res_pol.kind == ("person", "politician_statesman"), res_pol


def test_no_evidence_gives_no_resolution():
    ctx = ctx_of([row("A", "Zzzlaan", "unresolved")], {("A", "Zzzlaan"): "b"})
    table = C.build_table(ctx, rules=False)
    res = R.resolve_street(table["zzz"], *R.ContextIndex(ctx).counters(ctx.rows[("A", "Zzzlaan")]))
    assert res.decision == "none" and res.kind is None


def test_label_only_when_namesakes_agree():
    rows = [row(g, "Mozartstraat", "person", "musician_composer", "Wolfgang Amadeus Mozart", source="wikidata") for g in "ABC"]
    rows += [row(g, "Beukenlaan", "thing", "flora", lab) for g, lab in zip("ABC", ("Beech", "Birch", "Oak"))]
    ctx = ctx_of(rows, {(r["gemeente"], r["street"]): "b" + r["gemeente"] for r in rows})
    table, idx = C.build_table(ctx, rules=False), R.ContextIndex(ctx)
    m = R.resolve_street(table["mozart"], *idx.counters(ctx.rows[("A", "Mozartstraat")]))
    b = R.resolve_street(table["beuken"], *idx.counters(ctx.rows[("A", "Beukenlaan")]))
    assert m.label == "Wolfgang Amadeus Mozart" and b.label is None        # disagreeing labels -> kind only

def test_adjacency_themes_and_context():
    from names import adjacency as A, resolve as R
    adj = {("G", "A"): ["B", "C"], ("G", "B"): ["A", "C"], ("G", "C"): ["A", "B", "D"], ("G", "D"): ["C", "E"], ("G", "E"): ["D"]}
    kinds = {("G", n): ("person", "musician_composer") for n in "ABCD"}
    kinds[("G", "E")] = ("thing", "flora")
    themes = A.themes(adj, kinds, min_size=4)
    assert len(themes) == 1 and len(themes[0][1]) == 4                 # four connected same-kind streets form a theme; E is not part of it
    assert A.themes(adj, kinds, min_size=5) == []


def _world(extra):
    rows, buurt = [], {}
    def add(r):
        rows.append(r); buurt[(r["gemeente"], r["street"])] = "b" + r["gemeente"]
    for g in "ABCD":
        add(row(g, "Hendrikstraat", "person", "monarch_statesman", "Prince Hendrik"))
        add(row(g, "Brouwersstraat", "thing", "occupation_guild", "Brewer"))
        add(row(g, "Bakkerslaan", "thing", "occupation_guild", "Baker"))
    for r in extra:
        add(r)
    return ctx_of(rows, buurt)


def test_propose_person_kind_only_and_skips_reviewed():
    from names import propose
    rows = [row("N", "Hendrikstraat", "place", "local_landscape_feature"),
            row("N", "Brouwersstraat", "place", "local_landscape_feature", notes="Ordinary Dutch word, not a surname"),   # reviewed: leave alone
            row("N", "Bakkerslaan", "place", "local_landscape_feature")]
    ctx = _world(rows)
    table = C.build_table(ctx, rules=False)
    got = {o.street: o for o, _ in propose.evaluate(ctx, table, min_score=0.3, min_margin=0.1) if o.gemeente == "N"}
    assert "Brouwersstraat" not in got                                   # a deliberately reviewed street is never overridden
    assert got["Hendrikstraat"].category == "person" and got["Hendrikstraat"].entity_label is None   # a shared first name: kind only
    assert got["Bakkerslaan"].subcategory == "occupation_guild"


def test_propose_refuses_wikidata_only_place_guesses():
    from names import propose
    rows = [row("N", "Zandveld", "place", "local_landscape_feature")]
    ctx = _world(rows)
    table = C.build_table(ctx, rules=False)
    table[C.name_key("Zandveld")].cand(("place", "village")).wikidata.append(("strong", "Zandveld", "village in Gelderland"))   # Wikidata alone
    got = [o for o, _ in propose.evaluate(ctx, table, min_score=0.1, min_margin=0.0) if o.street == "Zandveld"]
    assert got == []


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f(); print("ok  ", n)
        except Exception:
            fails += 1; print("FAIL", n); traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} name-table tests pass")
    sys.exit(1 if fails else 0)
