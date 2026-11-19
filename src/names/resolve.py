"""Choose among a name's candidates for one street, using the street's buurt and wijk.

score(candidate) = (1 - lam) * prior + lam * fit
  prior  the candidate's share of the name's evidence mass (what the name usually means)
  fit    how well the candidate's kind matches the kinds of the street's neighbours (what this place is naming things after);
         neighbours in the same buurt count 0.7, in the same wijk 0.3; a neighbour of the same category but a different
         subcategory counts 0.4
  lam    LAMBDA_MAX x how much neighbour evidence there is (saturates at ~3 weighted neighbours)
The street's own classification and, when asked, a whole gemeente can be left out, so the resolver can be backtested."""
from __future__ import annotations

import collections
from dataclasses import dataclass, field

from rules.base import Context
from tiers import evidence_tier
from .candidates import LOCAL, TIER_WEIGHT, Kind, NameEntry, kind_of

PARTIAL = 0.4
LAMBDA_MAX = 0.5    # how much weight the neighbours can take from the name's own prior (reached at ~3 weighted neighbours)
BUURT_W, WIJK_W = 0.7, 0.3
ADJ_W, ADJ_BUURT_W, ADJ_WIJK_W = 0.6, 0.3, 0.1   # when the street's touching neighbours are known they dominate (Kooloos: themes are connected streets)
ACCEPT_SCORE, ACCEPT_MARGIN, ACCEPT_MASS = 0.40, 0.12, 0.8
LABEL_SHARE = 0.6


def norm_kind(row) -> Kind | None:
    k = kind_of(row)
    if k is None:
        return None
    return LOCAL if (k[0] == "place" and k[1] == "local_landscape_feature") else k


def _key(t):
    return None if t[1] is None else t


class ContextIndex:
    """Weighted kind counts for every buurt and wijk."""

    def __init__(self, ctx: Context, skip_gemeente: str | None = None, adjacency: dict | None = None):
        self.ctx = ctx
        self.adjacency = adjacency
        self.known = {}                         # (gemeente, street) -> (kind, weight): what each street currently contributes
        self.buurt = collections.defaultdict(collections.Counter)
        self.wijk = collections.defaultdict(collections.Counter)
        for r in ctx.final:
            if skip_gemeente and r["gemeente"] == skip_gemeente:
                continue
            self.add(r, TIER_WEIGHT[evidence_tier(r)])

    def _keys(self, row):
        return _key(self.ctx.buurt(row)), _key(self.ctx.wijk(row))

    def add(self, row, weight, kind=None):
        k = kind or norm_kind(row)
        if k is None:
            return
        self.known[(row["gemeente"], row["street"])] = (k, weight)
        b, w = self._keys(row)
        if b is not None:
            self.buurt[b][k] += weight
        if w is not None:
            self.wijk[w][k] += weight

    def sub(self, row, weight, kind):
        """Undo a contribution made with add(row, weight, kind)."""
        self.known.pop((row["gemeente"], row["street"]), None)
        b, w = self._keys(row)
        if b is not None:
            self.buurt[b][kind] -= weight
        if w is not None:
            self.wijk[w][kind] -= weight

    def remove(self, row):
        k = norm_kind(row)
        if k is None:
            return
        wt = TIER_WEIGHT[evidence_tier(row)]
        self.known.pop((row["gemeente"], row["street"]), None)
        b, w = self._keys(row)
        if b is not None:
            self.buurt[b][k] -= wt
        if w is not None:
            self.wijk[w][k] -= wt

    def adjacent(self, row):
        """Weighted kind counts of the streets that touch this one (empty without an adjacency map)."""
        c = collections.Counter()
        if self.adjacency:
            for nb in self.adjacency.get((row["gemeente"], row["street"]), ()):
                kw = self.known.get((row["gemeente"], nb))
                if kw:
                    c[kw[0]] += kw[1]
        return c

    def counters(self, row):
        b, w = self._keys(row)
        return self.buurt.get(b, collections.Counter()), self.wijk.get(w, collections.Counter())


def _fit(counter, kind: Kind):
    total = sum(v for v in counter.values() if v > 0)
    if total <= 0:
        return 0.0, 0.0
    if kind[1] is None:
        same = sum(v for k, v in counter.items() if v > 0 and k[0] == kind[0])
        partial = 0.0
    else:
        same = counter.get(kind, 0.0)
        partial = sum(v for k, v in counter.items() if v > 0 and k[0] == kind[0] and k != kind)
    return (max(same, 0.0) + PARTIAL * partial) / total, min(1.0, total / 3.0)


@dataclass
class Resolution:
    street: tuple
    kind: Kind | None
    label: str | None
    score: float
    margin: float
    decision: str                                     # accept / ambiguous / none
    alternatives: list = field(default_factory=list)   # [(kind, score, prior, fit)]


def score_candidates(entry: NameEntry, buurt_c, wijk_c, exclude=None, gemeente=None, use_wikidata=True, mode="full", adj_c=None):
    masses = {k: c.mass(exclude, gemeente, use_wikidata) for k, c in entry.candidates.items()}
    masses = {k: m for k, m in masses.items() if m > 0}
    total = sum(masses.values())
    if total == 0:
        return []
    out = []
    for k, m in masses.items():
        prior = m / total
        parts = [(BUURT_W, buurt_c), (WIJK_W, wijk_c)]
        if adj_c:
            parts = [(ADJ_W, adj_c), (ADJ_BUURT_W, buurt_c), (ADJ_WIJK_W, wijk_c)]
        fits = [(w,) + _fit(c, k) for w, c in parts]
        den = sum(w * conf for w, _, conf in fits)
        if den > 0:
            fit = sum(w * f * conf for w, f, conf in fits) / den
            lam = LAMBDA_MAX * min(1.0, den)
        else:
            fit, lam = 0.0, 0.0
        if mode == "prior":
            s = prior
        elif mode == "context":
            s = fit + 1e-3 * prior
        else:
            s = (1 - lam) * prior + lam * fit
        out.append((k, s, prior, fit, m))
    out.sort(key=lambda t: -t[1])
    return out


def resolve_street(entry: NameEntry, buurt_c, wijk_c, street=None, adj_c=None, **kw) -> Resolution:
    scored = score_candidates(entry, buurt_c, wijk_c, adj_c=adj_c, **kw)
    if not scored:
        return Resolution(street, None, None, 0.0, 0.0, "none")
    best = scored[0]
    margin = best[1] - (scored[1][1] if len(scored) > 1 else 0.0)
    labels = entry.candidates[best[0]].labels(kw.get("exclude"), kw.get("gemeente"))
    label = None
    if labels:
        top, w = labels.most_common(1)[0]
        if w / sum(labels.values()) >= LABEL_SHARE:
            label = top
    ok = best[1] >= ACCEPT_SCORE and margin >= ACCEPT_MARGIN and best[4] >= ACCEPT_MASS
    return Resolution(street, best[0], label, round(best[1], 3), round(margin, 3), "accept" if ok else "ambiguous",
                      [(k, round(s, 3), round(p, 3), round(f, 3)) for k, s, p, f, _ in scored[:4]])
