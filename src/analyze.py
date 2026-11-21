"""Spatial analysis: do naming themes cluster at the wijk level, per gemeente?

Each buurt's theme was assigned by reading its own street list, so a buurt looks
monothematic by construction -- that is not a finding. The open question is whether
buurten grouped into the same wijk share a theme more often than chance would give.

"Uniformity" of a wijk = share of its buurten carrying the wijk's most common label.
Raw uniformity is misleading on its own (if 60% of buurten are 'person', wijken look
uniform by chance, and a gemeente with 3 wijken behaves very differently from one with
20), so each gemeente is also tested against a permutation baseline: shuffle the labels
across that gemeente's buurten, keep the wijk structure, and see how often chance matches
the observed pooled uniformity. Two label levels: the top-level category (person / place /
thing) and the finer legend group used on the map.
"""
import json
import random
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from build_map import subgroup_color

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "output"
PERMUTATIONS = 10_000
SEED = 20260920


def dominant_category(theme: dict) -> tuple[str, str | None]:
    """(category, subcategory) of a buurt's theme; for a mixed theme, its largest sub-theme."""
    if theme["category"] != "mixed":
        return theme["category"], theme.get("subcategory")
    subthemes = theme.get("subthemes", [])
    if not subthemes:
        return "mixed", None
    best = max(subthemes, key=lambda s: s.get("share", 0))
    return best["category"], best.get("subcategory")


def labels_for(theme: dict) -> dict:
    cat, sub = dominant_category(theme)
    return {"category": cat, "group": subgroup_color(cat, sub)[0]}


def pooled_uniformity(wijken: list[list[str]]) -> float:
    """Share of buurten (in wijken with >=2) that match their wijk's modal label."""
    kept = [w for w in wijken if len(w) >= 2]
    return sum(Counter(w).most_common(1)[0][1] for w in kept) / sum(len(w) for w in kept)


def permutation_test(wijken: list[list[str]], rng: random.Random) -> dict:
    sizes = [len(w) for w in wijken]
    pool = [x for w in wijken for x in w]
    observed = pooled_uniformity(wijken)
    at_least, null_sum = 0, 0.0
    for _ in range(PERMUTATIONS):
        rng.shuffle(pool)
        i, shuffled = 0, []
        for n in sizes:
            shuffled.append(pool[i:i + n])
            i += n
        u = pooled_uniformity(shuffled)
        null_sum += u
        at_least += u >= observed
    return {
        "observed": round(observed, 3),
        "chance_mean": round(null_sum / PERMUTATIONS, 3),
        "p_value": round((at_least + 1) / (PERMUTATIONS + 1), 4),
    }


def main():
    themes = json.loads((DATA_DIR / "enriched" / "buurt_themes_full.json").read_text())["buurten"]
    themes = [t for t in themes if t["category"] != "unclear"]

    by_gemeente = defaultdict(lambda: defaultdict(list))
    for t in themes:
        by_gemeente[t["gemeente"]][t["wijk"]].append(t)

    wijk_rows, tests = [], []
    for gemeente, wijken in sorted(by_gemeente.items()):
        for wijk, buurten in sorted(wijken.items()):
            labs = [labels_for(t) for t in buurten]
            cats = Counter(l["category"] for l in labs)
            groups = Counter(l["group"] for l in labs)
            wijk_rows.append({
                "gemeente": gemeente, "wijk": wijk, "n_buurten": len(buurten),
                "dominant_category": cats.most_common(1)[0][0],
                "category_uniformity": round(cats.most_common(1)[0][1] / len(buurten), 2),
                "dominant_group": groups.most_common(1)[0][0],
                "group_uniformity": round(groups.most_common(1)[0][1] / len(buurten), 2),
                "category_breakdown": dict(cats), "group_breakdown": dict(groups),
                "buurten": [t["buurt"] for t in buurten],
            })
        for level in ("category", "group"):
            # seed per (gemeente, level) so adding a gemeente never shifts earlier results
            rng = random.Random(SEED + zlib.crc32(f"{gemeente}|{level}".encode()))
            wijk_labels = [[labels_for(t)[level] for t in b] for b in wijken.values()]
            n_testable = sum(1 for w in wijk_labels if len(w) >= 2)
            tests.append({
                "gemeente": gemeente, "level": level,
                "wijken_total": len(wijken), "wijken_testable": n_testable,
                "buurten_testable": sum(len(w) for w in wijk_labels if len(w) >= 2),
                **permutation_test(wijk_labels, rng),
            })

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / "wijk_theme_clustering.json"
    out_path.write_text(json.dumps({"permutation_tests": tests, "wijken": wijk_rows},
                                   indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}\n")

    print("Permutation tests (observed pooled uniformity vs. shuffled-label baseline)")
    print(f"{'gemeente':10s} {'level':9s} {'wijken':>6s} {'buurten':>7s} {'observed':>9s} {'chance':>7s} {'p':>8s}")
    for t in tests:
        print(f"{t['gemeente']:10s} {t['level']:9s} {t['wijken_testable']:>6d} {t['buurten_testable']:>7d} "
              f"{t['observed']:>9.0%} {t['chance_mean']:>7.0%} {t['p_value']:>8.4f}")

    for gemeente in sorted(by_gemeente):
        print(f"\n{gemeente}: wijken with >=2 analyzable buurten")
        print(f"  {'wijk':34s} {'n':>3s} {'dominant group':32s} {'uniform':>8s}")
        for r in sorted((r for r in wijk_rows if r["gemeente"] == gemeente and r["n_buurten"] >= 2),
                        key=lambda r: (-r["group_uniformity"], -r["n_buurten"])):
            print(f"  {r['wijk']:34s} {r['n_buurten']:3d} {r['dominant_group']:32s} {r['group_uniformity']:8.0%}")


if __name__ == "__main__":
    main()
