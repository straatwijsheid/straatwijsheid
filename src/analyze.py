"""Spatial analysis: does buurt-level theming cluster into larger wijk zones?

Since buurt themes were assigned by reading each buurt's own street list, of
course each buurt looks monothematic -- that's true by construction, not a
finding. The actual open question is whether neighboring buurten (grouped
into a wijk) share a category, i.e. whether the theming pattern operates at
a coarser geographic scale than the buurt itself.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "output"


def dominant_category(theme: dict) -> tuple[str, str, float]:
    """Return (category, subcategory, weight) -- for a mixed theme, the
    largest sub-theme; weight is 1.0 for a clean theme, else the sub-share."""
    if theme["category"] != "mixed":
        return theme["category"], theme.get("subcategory"), 1.0
    subthemes = theme.get("subthemes", [])
    if not subthemes:
        return "mixed", None, 0.5
    best = max(subthemes, key=lambda s: s.get("share", 0))
    return best["category"], best.get("subcategory"), best.get("share", 0.5)


def main():
    themes = json.loads((DATA_DIR / "enriched" / "buurt_themes_full.json").read_text())["buurten"]
    themes = [t for t in themes if t["category"] != "unclear"]

    by_wijk = defaultdict(list)
    for t in themes:
        by_wijk[t["wijk"]].append(t)

    rows = []
    for wijk, buurten in sorted(by_wijk.items()):
        cats = Counter(dominant_category(t)[0] for t in buurten)
        top_cat, top_count = cats.most_common(1)[0]
        homogeneity = top_count / len(buurten)
        rows.append({
            "wijk": wijk,
            "n_buurten": len(buurten),
            "dominant_category": top_cat,
            "homogeneity": round(homogeneity, 2),
            "category_breakdown": dict(cats),
            "buurten": [t["buurt"] for t in buurten],
            "buurt_themes": [t["theme"] for t in buurten],
        })

    rows.sort(key=lambda r: (-r["homogeneity"], -r["n_buurten"]))

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / "wijk_theme_clustering.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}\n")

    multi_buurt = [r for r in rows if r["n_buurten"] >= 2]
    fully_homogeneous = [r for r in multi_buurt if r["homogeneity"] == 1.0]
    print(f"{len(multi_buurt)} wijken have >=2 classified buurten")
    print(f"{len(fully_homogeneous)}/{len(multi_buurt)} of those are 100% single-category "
          f"({len(fully_homogeneous) / len(multi_buurt):.0%})\n")

    print(f"{'wijk':30s} {'n':>3s} {'dominant':12s} {'homog':>6s}  buurten")
    for r in multi_buurt:
        print(f"{r['wijk']:30s} {r['n_buurten']:3d} {r['dominant_category']:12s} "
              f"{r['homogeneity']:6.0%}  {', '.join(r['buurten'])}")


if __name__ == "__main__":
    main()
