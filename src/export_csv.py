"""Write the flat CSV exports in output/: streets_classified.csv and buurt_themes.csv."""
import config
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiers import TIER_NAMES, evidence_tier  # noqa: E402

OUT = config.OUTPUT

COLS = ["gemeente", "street", "wijk", "buurt", "category", "subcategory", "entity_label",
        "entity_description", "evidence_tier", "evidence_tier_name", "highway", "way_class", "confidence", "source", "source_url",
        "buurt_theme", "notes"]


def main():
    final = pd.DataFrame(json.loads((config.ENRICHED / "streets_final.json").read_text()))
    if "evidence_tier" not in final:
        final["evidence_tier"] = [evidence_tier(r) for r in final.to_dict("records")]
    final["evidence_tier_name"] = final["evidence_tier"].map(TIER_NAMES)
    streets = gpd.read_file(config.RAW / "streets.geojson")[["gemeente", "name", "wijk"]]
    streets = streets.rename(columns={"name": "street"}).drop_duplicates(["gemeente", "street"])
    df = final.merge(streets, on=["gemeente", "street"], how="left")
    for c in COLS:
        if c not in df:
            df[c] = None
    df = df[COLS].sort_values(["gemeente", "wijk", "buurt", "street"])
    df.to_csv(OUT / "streets_classified.csv", index=False)

    themes = json.loads((config.ENRICHED / "buurt_themes_full.json").read_text())["buurten"]
    rows = [{**{k: t.get(k) for k in ("gemeente", "buurt", "wijk", "theme", "category", "subcategory",
                                      "confidence", "source")},
             "example_streets": "; ".join(t.get("example_streets", []))} for t in themes]
    pd.DataFrame(rows).to_csv(OUT / "buurt_themes.csv", index=False)
    print(f"streets_classified.csv: {len(df)} rows; buurt_themes.csv: {len(rows)} rows")


if __name__ == "__main__":
    main()
