"""Reconcile per-street Wikidata classifications with buurt-level naming themes.

A street's individual match is trusted when it's high-confidence AND agrees
with its buurt's dominant theme. When it's low-confidence or conflicts with
a strongly monothematic buurt, the buurt theme wins (this is what fixes
Pinkstraat -> "Pink" the singer, Pluvierlaan -> an unrelated person, etc.).
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONFIDENT_THRESHOLD = 0.7
STRONG_THEME_THRESHOLD = 0.8

# a title/honorific prefix is a strong, cheap signal that a street is named
# after a person, regardless of what the buurt's dominant theme is (this is
# what fixes cases like "Ingenieur Kalffstraat" getting swept into a
# buurt's "thing" theme just because that subtheme had the bigger share)
PERSON_TITLE_PREFIXES = [
    "Ingenieur", "Professor", "Doctor", "Dr", "Meester", "Mr", "Burgemeester",
    "Generaal", "Kapitein", "Monseigneur", "Pastoor", "Kardinaal", "Sint",
    "Dominee", "Rector", "Kanunnik", "Deken", "Baron", "Graaf", "Hertog",
    "Prins", "Prinses", "Koning", "Koningin", "Vicaris", "Pater", "President",
    "Minister", "Veldmaarschalk", "Kolonel", "Majoor", "Admiraal",
]
_TITLE_RE = re.compile(
    r"^(" + "|".join(re.escape(p) for p in PERSON_TITLE_PREFIXES) + r")\s+\S", re.IGNORECASE
)


def has_person_title(street_name: str) -> bool:
    return bool(_TITLE_RE.match(street_name))


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

        if has_person_title(street) and wd_category != "person":
            subcategory = "other"
            if theme:
                if theme.get("category") == "person":
                    subcategory = theme.get("subcategory") or "other"
                elif theme.get("category") == "mixed":
                    person_subs = [s for s in theme.get("subthemes", []) if s["category"] == "person"]
                    if person_subs:
                        subcategory = person_subs[0].get("subcategory") or "other"
            row["category"] = "person"
            row["subcategory"] = subcategory
            row["confidence"] = 0.65
            row["source"] = "title_heuristic"
            title = street.split()[0]
            row["notes"] = (
                f"street name starts with the person-title '{title}', overriding the "
                f"{wd_category or 'unresolved'} guess from Wikidata/buurt theme"
            )
            final.append(row)
            continue

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
                row["confidence"] = round(theme_conf * 0.9, 2)
            else:
                subthemes = theme.get("subthemes", [])
                if subthemes:
                    best_sub = max(subthemes, key=lambda s: s.get("share", 0))
                    row["category"] = best_sub["category"]
                    row["subcategory"] = best_sub.get("subcategory")
                    row["confidence"] = round(theme_conf * best_sub.get("share", 0.5) * 0.9, 2)
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
            else:
                # pick the largest sub-theme as the best guess; discount further
                # since within-buurt we can't tell which sub-cluster a given
                # street belongs to without more signal (e.g. its actual name)
                subthemes = theme.get("subthemes", [])
                if subthemes:
                    best_sub = max(subthemes, key=lambda s: s.get("share", 0))
                    row["category"] = best_sub["category"]
                    row["subcategory"] = best_sub.get("subcategory")
                    row["confidence"] = round(theme_conf * best_sub.get("share", 0.5) * 0.8, 2)
            row["source"] = "buurt_theme_fallback"
            row["notes"] = f"no confident individual match; inferred from buurt theme '{theme['theme']}'"
        else:
            row["notes"] = "kept as-is; theme present but not strong enough to override or assist"

        final.append(row)
    return final


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def main():
    import sys

    full_run = "--full" in sys.argv

    if full_run:
        import geopandas as gpd

        wikidata_results = load_jsonl(DATA_DIR / "enriched" / "all_streets_wikidata.jsonl")
        gdf = gpd.read_file(DATA_DIR / "raw" / "streets.geojson")
        context = {row["name"]: {"buurt": row["buurt"]} for _, row in gdf.iterrows()}
        themes = load_json(DATA_DIR / "enriched" / "buurt_themes_full.json")["buurten"]
        out_path = DATA_DIR / "enriched" / "streets_final.json"
    else:
        wikidata_results = load_json(DATA_DIR / "enriched" / "pilot_wikidata.json")
        context = load_json(DATA_DIR / "enriched" / "pilot_context.json")
        themes = load_json(DATA_DIR / "enriched" / "buurt_themes_pilot.json")["buurten"]
        out_path = DATA_DIR / "enriched" / "pilot_final.json"

    themes_by_buurt = {t["buurt"]: t for t in themes}
    final = reconcile(wikidata_results, context, themes_by_buurt)

    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path} ({len(final)} streets)")

    if not full_run:
        for row in final:
            print(
                f"{row['street']:30s} {row['category'] or '?':10s} "
                f"{row['subcategory'] or '':22s} conf={row['confidence']:.2f}  [{row['source']}]"
            )
    else:
        from collections import Counter

        counts = Counter(row["category"] for row in final)
        print("Category breakdown:", dict(counts))


if __name__ == "__main__":
    main()
