"""Reconcile per-street Wikidata classifications with buurt-level naming themes.

A street's individual match is trusted when it's high-confidence AND agrees
with its buurt's dominant theme. When it's low-confidence or conflicts with
a strongly monothematic buurt, the buurt theme wins (this is what fixes
Pinkstraat -> "Pink" the singer, Pluvierlaan -> an unrelated person, etc.).
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONFIDENT_THRESHOLD = 0.7
STRONG_THEME_THRESHOLD = 0.8


def load_json(path: Path):
    return json.loads(path.read_text())


def reconcile(wikidata_results: list[dict], context: dict, themes_by_buurt: dict) -> list[dict]:
    final = []
    for r in wikidata_results:
        street = r["street"]
        buurt = context.get(street, {}).get("buurt")
        theme = themes_by_buurt.get(buurt)

        wd_conf = r.get("confidence", 0.0)
        wd_category = r.get("category")

        row = {
            "street": street,
            "buurt": buurt,
            "category": wd_category,
            "subcategory": r.get("subcategory"),
            "entity_label": r.get("wikidata_label"),
            "entity_description": r.get("wikidata_description"),
            "confidence": wd_conf,
            "source": r.get("source"),
            "buurt_theme": theme.get("theme") if theme else None,
            "notes": "",
        }

        if theme is None:
            final.append(row)
            continue

        theme_conf = theme.get("confidence", 0.0)
        theme_category = theme.get("category")

        agrees = (
            wd_category == theme_category
            or (theme_category == "mixed" and wd_category in {
                s["category"] for s in theme.get("subthemes", [])
            })
        )

        if wd_conf >= CONFIDENT_THRESHOLD and (agrees or theme_category is None):
            row["notes"] = "individual match kept (confident + consistent with buurt)"
        elif theme_conf >= STRONG_THEME_THRESHOLD and not agrees:
            # buurt theme overrides a weak or conflicting individual match
            if theme_category != "mixed":
                row["category"] = theme_category
                row["subcategory"] = theme.get("subcategory")
            row["confidence"] = round(theme_conf * 0.9, 2)  # slightly discounted: inferred, not direct
            row["source"] = "buurt_theme_override"
            row["notes"] = (
                f"overridden: individual match ({wd_category}, conf={wd_conf}) "
                f"conflicted with strong buurt theme '{theme['theme']}'"
            )
        elif wd_conf < CONFIDENT_THRESHOLD and theme_conf >= 0.6:
            if theme_category != "mixed":
                row["category"] = theme_category
                row["subcategory"] = theme.get("subcategory")
            row["confidence"] = round(theme_conf * 0.8, 2)
            row["source"] = "buurt_theme_fallback"
            row["notes"] = f"no confident individual match; inferred from buurt theme '{theme['theme']}'"
        else:
            row["notes"] = "kept as-is; theme present but not strong enough to override or assist"

        final.append(row)
    return final


def main():
    wikidata_results = load_json(DATA_DIR / "enriched" / "pilot_wikidata.json")
    context = load_json(DATA_DIR / "enriched" / "pilot_context.json")
    themes = load_json(DATA_DIR / "enriched" / "buurt_themes_pilot.json")["buurten"]
    themes_by_buurt = {t["buurt"]: t for t in themes}

    final = reconcile(wikidata_results, context, themes_by_buurt)

    out_path = DATA_DIR / "enriched" / "pilot_final.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}")

    for row in final:
        print(
            f"{row['street']:30s} {row['category'] or '?':10s} "
            f"{row['subcategory'] or '':22s} conf={row['confidence']:.2f}  [{row['source']}]"
        )


if __name__ == "__main__":
    main()
