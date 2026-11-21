"""Build, inspect and backtest the name-level candidate table.

  python src/names/run.py --build                 write data/names/candidates.jsonl (derived; rebuilt in seconds)
  python src/names/run.py --show NAME [NAME ...]   a name's candidates, and how each of its streets would resolve
  python src/names/run.py --backtest [--n 4000]    how well does the resolver recover classifications it is not shown?
  python src/names/run.py --propose                dry run on streets with no named namesake (tiers 3-5): what would be accepted
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from names import adjacency as A, candidates as C, resolve as R   # noqa: E402
from rules.base import Context, DATA                          # noqa: E402
from tiers import evidence_tier                               # noqa: E402

OUT = DATA / "names" / "candidates.jsonl"


def load():
    ctx = Context.load()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from osm_etymology import load as load_osm
    return ctx, C.build_table(ctx, C.load_wikidata_records(), osm=load_osm())


def write_table(table):
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as f:
        for key, e in sorted(table.items()):
            f.write(json.dumps({
                "name": key, "streets": len(e.streets), "gemeenten": len({g for g, _ in e.streets}),
                "candidates": [{"category": k[0], "subcategory": k[1], "mass": round(c.mass(), 2), "occurrences": len(c.occurrences),
                                "labels": [[l, round(w, 2)] for l, w in c.labels().most_common(3)], "rules": sorted(c.rules),
                                "wikidata": [{"strength": s, "label": l, "description": d} for s, l, d in c.wikidata[:2]]}
                               for k, c in sorted(e.candidates.items(), key=lambda kv: -kv[1].mass())]}, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(DATA.parent)} ({len(table)} names)")


def _tokens(s):
    return {t for t in re.split(r"[^a-zë]+", (s or "").lower()) if len(t) >= 4}


def label_match(truth, pred):
    return bool(truth) and bool(pred) and (re.sub(r"\W", "", truth.lower()) == re.sub(r"\W", "", pred.lower()) or bool(_tokens(truth) & _tokens(pred)))


class Score:
    def __init__(self):
        self.n = self.kind = self.cat = self.accepted = self.acc_kind = self.acc_cat = self.lab_n = self.lab_ok = 0

    def add(self, truth_kind, truth_label, res):
        self.n += 1
        if res.kind is None:
            return
        k = res.kind[0] == truth_kind[0] and (res.kind[1] == truth_kind[1] or res.kind[1] is None)
        c = res.kind[0] == truth_kind[0]
        self.kind += k
        self.cat += c
        if res.decision == "accept":
            self.accepted += 1
            self.acc_kind += k
            self.acc_cat += c
        if truth_label:
            self.lab_n += 1
            self.lab_ok += label_match(truth_label, res.label)

    def row(self, name):
        pct = lambda a, b: f"{a / b:6.1%}" if b else "   n/a"
        return (f"{name:34}{self.n:>6}  kind {pct(self.kind, self.n)}  category {pct(self.cat, self.n)}   "
                f"accepted {pct(self.accepted, self.n)} -> kind {pct(self.acc_kind, self.accepted)} cat {pct(self.acc_cat, self.accepted)}   "
                f"label {pct(self.lab_ok, self.lab_n)} of {self.lab_n}")


def backtest(ctx, table, n=4000, seed=7):
    rng = random.Random(seed)
    truth = [r for r in ctx.final if evidence_tier(r) <= 2 and R.norm_kind(r) is not None and r.get("entity_label")]
    sample = rng.sample(truth, min(n, len(truth)))
    adj = A.load()
    idx = R.ContextIndex(ctx, adjacency=adj)
    modes = {"name only (prior)": dict(mode="prior"), "buurt context only": dict(mode="context"), "full: name + buurt/wijk": dict(mode="full"),
             "adjacent streets only (context)": dict(mode="context", adj=True, only_adj=True), "full: name + adjacent streets": dict(mode="full", adj=True),
             "full + adjacent, no Wikidata": dict(mode="full", adj=True, use_wikidata=False), "full, no Wikidata evidence": dict(mode="full", use_wikidata=False)}
    scores = {m: Score() for m in modes}
    t1 = {m: Score() for m in modes}
    for r in sample:
        entry = table[C.name_key(r["street"])]
        k = R.norm_kind(r)
        idx.remove(r)
        bc, wc = idx.counters(r)
        ac = idx.adjacent(r)
        for m, kw in modes.items():
            kw = dict(kw)
            use_adj, only_adj = kw.pop("adj", False), kw.pop("only_adj", False)
            res = R.resolve_street(entry, collections.Counter() if only_adj else bc, collections.Counter() if only_adj else wc,
                                   street=(r["gemeente"], r["street"]), exclude=(r["gemeente"], r["street"]), adj_c=ac if use_adj else None, **kw)
            scores[m].add(k, r["entity_label"], res)
            if evidence_tier(r) == 1:
                t1[m].add(k, r["entity_label"], res)
        idx.add(r, C.TIER_WEIGHT[evidence_tier(r)])
    print(f"\nA. Leave-one-out: hide one street's own classification, recover it ({len(sample)} streets with a named namesake)")
    for m, s in scores.items():
        print("  ", s.row(m))
    print("   --- only the externally verified (tier 1) streets ---")
    for m, s in t1.items():
        print("  ", s.row(m))
    return sample


def new_gemeente(ctx, table, gemeenten):
    print("\nB. New-gemeente simulation: hide a whole gemeente and resolve it from what is known elsewhere.")
    print("   Seeds = the gemeente's own externally verified (tier 1) streets, as Wikidata would give for a new gemeente.")
    print("   Pass 1 uses the name only; pass 2 adds the seeds and the confident pass-1 predictions as neighbour context.")
    print("   Truth = the streets of that gemeente with a known kind (tier 1-3); each street's own seed/prediction is removed before it is scored.")
    tot1, tot2 = Score(), Score()
    for g in gemeenten:
        rows = [r for r in ctx.final if r["gemeente"] == g]
        truth = {(g, r["street"]): r for r in rows if evidence_tier(r) <= 3 and R.norm_kind(r) is not None}
        idx = R.ContextIndex(ctx, skip_gemeente=g)
        contrib = {}
        for r in rows:                                   # seeds: external evidence only
            if evidence_tier(r) == 1 and R.norm_kind(r) is not None:
                k = R.norm_kind(r)
                idx.add(r, C.TIER_WEIGHT[1], k)
                contrib[(g, r["street"])] = (k, C.TIER_WEIGHT[1])
        pass1 = {}
        for r in rows:
            key = (g, r["street"])
            entry = table[C.name_key(r["street"])]
            res = R.resolve_street(entry, *idx.counters(r), street=key, gemeente=g, mode="prior", use_wikidata=True)
            pass1[key] = res
        for r in rows:                                   # confident predictions join the context
            key = (g, r["street"])
            res = pass1[key]
            if res.decision == "accept" and res.kind[1] is not None and key not in contrib:
                idx.add(r, C.TIER_WEIGHT[3], res.kind)
                contrib[key] = (res.kind, C.TIER_WEIGHT[3])
        s1, s2 = Score(), Score()
        for r in rows:
            key = (g, r["street"])
            if key not in truth:
                continue
            tk = R.norm_kind(truth[key])
            lab = truth[key].get("entity_label")
            s1.add(tk, lab, pass1[key])
            if key in contrib:
                idx.sub(r, contrib[key][1], contrib[key][0])
            res = R.resolve_street(table[C.name_key(r["street"])], *idx.counters(r), street=key, gemeente=g, mode="full")
            if key in contrib:
                idx.add(r, contrib[key][1], contrib[key][0])
            s2.add(tk, lab, res)
        for a_, b_ in ((tot1, s1), (tot2, s2)):
            for f in ("n", "kind", "cat", "accepted", "acc_kind", "acc_cat", "lab_n", "lab_ok"):
                setattr(a_, f, getattr(a_, f) + getattr(b_, f))
        print(f"   {g:16} pass 1 (name only) kind {s1.kind / max(s1.n, 1):5.1%}   pass 2 (with context) kind {s2.kind / max(s2.n, 1):5.1%}   ({s1.n} streets, {sum(1 for k in contrib if True)} seeds+predictions)")
    print("  ", tot1.row("all, pass 1: name only"))
    print("  ", tot2.row("all, pass 2: + seeds and context"))


def cmd_show(ctx, table, names):
    idx = R.ContextIndex(ctx)
    for nm in names:
        e = table.get(C.name_key(nm)) or table.get(nm.lower())
        if not e:
            print(f"\n{nm}: no such name")
            continue
        print(f"\n{e.key}: {len(e.streets)} streets in {len({g for g, _ in e.streets})} gemeenten")
        for k, c in sorted(e.candidates.items(), key=lambda kv: -kv[1].mass()):
            print(f"   {str(k):52} mass {c.mass():6.1f}  occ {len(c.occurrences):3}  rules {sorted(c.rules)}  wikidata {[w[0] for w in c.wikidata]}  labels {c.labels().most_common(2)}")
        shown = 0
        for g, s in e.streets[:8]:
            r = ctx.rows[(g, s)]
            res = R.resolve_street(e, *idx.counters(r), street=(g, s))
            print(f"      {g[:14]:15}{s:26} now {r['category']}/{r.get('subcategory')}/{r.get('entity_label')} | resolver: {res.decision} {res.kind} {res.label} score {res.score} margin {res.margin}")


def cmd_propose(ctx, table):
    idx = R.ContextIndex(ctx)
    out = collections.Counter(); samples = collections.defaultdict(list)
    for r in ctx.final:
        t = evidence_tier(r)
        if t < 3:
            continue
        e = table[C.name_key(r["street"])]
        res = R.resolve_street(e, *idx.counters(r), street=(r["gemeente"], r["street"]))
        cur = R.norm_kind(r) or (None, None)
        if res.decision != "accept":
            out[(t, "ambiguous/none")] += 1
            continue
        if res.kind == cur and (res.label is None or res.label == r.get("entity_label")):
            out[(t, "agrees")] += 1
        elif res.kind == cur or (res.kind[0] == cur[0] and cur[1] is not None and res.kind[1] is None):
            out[(t, "names it" if res.label and not r.get("entity_label") else "same kind")] += 1
        else:
            out[(t, "changes kind")] += 1
            if len(samples[t]) < 14 and out[(t, "changes kind")] > 0:
                samples[t].append(f"{r['gemeente'][:10]:11}{r['street']:28} {r['category']}/{r.get('subcategory')} -> {res.kind[0]}/{res.kind[1]}  {res.label}  (score {res.score})")
    for k in sorted(out): print(f"tier {k[0]} {k[1]:16} {out[k]:>6}")
    for t, L in samples.items():
        print(f"\n-- tier {t} examples of proposed changes --")
        print("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--show", nargs="+")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--n", type=int, default=4000)
    a = ap.parse_args(argv)
    ctx, table = load()
    print(C.table_summary(table))
    if a.build:
        write_table(table)
    if a.show:
        cmd_show(ctx, table, a.show)
    if a.backtest:
        backtest(ctx, table, a.n)
        new_gemeente(ctx, table, ["Tilburg", "Helmond", "Roosendaal", "Oss", "Boxtel", "Veghel"])
    if a.propose:
        cmd_propose(ctx, table)


if __name__ == "__main__":
    main()
