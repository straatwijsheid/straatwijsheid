"""Build an interactive map of Eindhoven streets colored by naming category,
with buurt polygons showing the detected theme on hover/click."""
import json
from pathlib import Path

import folium
import geopandas as gpd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "output"

CATEGORY_COLORS = {
    "person": "#2563eb",     # blue
    "place": "#16a34a",      # green
    "thing": "#ea580c",      # orange
    "mixed": "#9333ea",      # purple
    "unresolved": "#9ca3af", # gray
    "unclear": "#9ca3af",
}


def main():
    streets = gpd.read_file(DATA_DIR / "raw" / "streets.geojson")
    final = {r["street"]: r for r in json.loads((DATA_DIR / "enriched" / "streets_final.json").read_text())}
    themes = {t["buurt"]: t for t in json.loads((DATA_DIR / "enriched" / "buurt_themes_full.json").read_text())["buurten"]}
    buurten = gpd.read_file(DATA_DIR / "raw" / "buurten.geojson")

    streets["category"] = streets["name"].map(lambda n: final.get(n, {}).get("category", "unresolved"))
    streets["subcategory"] = streets["name"].map(lambda n: final.get(n, {}).get("subcategory"))
    streets["confidence"] = streets["name"].map(lambda n: final.get(n, {}).get("confidence"))
    streets["source"] = streets["name"].map(lambda n: final.get(n, {}).get("source"))

    center = [51.4416, 5.4697]  # Eindhoven
    m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    buurt_layer = folium.FeatureGroup(name="Buurt themes", show=True)
    for _, row in buurten.iterrows():
        theme = themes.get(row["name"])
        if not theme:
            continue
        color = CATEGORY_COLORS.get(theme["category"], "#9ca3af")
        popup = f"<b>{row['name']}</b> ({theme['wijk']})<br>{theme['theme']}<br>confidence: {theme['confidence']}"
        folium.GeoJson(
            row["geometry"],
            style_function=lambda _, c=color: {
                "fillColor": c, "color": c, "weight": 1, "fillOpacity": 0.15,
            },
            tooltip=f"{row['name']}: {theme['theme']}",
            popup=popup,
        ).add_to(buurt_layer)
    buurt_layer.add_to(m)

    street_layer = folium.FeatureGroup(name="Streets", show=True)
    for _, row in streets.iterrows():
        color = CATEGORY_COLORS.get(row["category"], "#9ca3af")
        popup = (
            f"<b>{row['name']}</b><br>category: {row['category']} / {row['subcategory']}"
            f"<br>confidence: {row['confidence']}<br>source: {row['source']}"
        )
        folium.GeoJson(
            row["geometry"],
            style_function=lambda _, c=color: {"color": c, "weight": 3, "opacity": 0.8},
            tooltip=row["name"],
            popup=popup,
        ).add_to(street_layer)
    street_layer.add_to(m)

    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 10px 14px; border-radius: 6px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 13px;">
      <b>Street naming category</b><br>
      <span style="color:#2563eb;">&#9632;</span> Person<br>
      <span style="color:#16a34a;">&#9632;</span> Place<br>
      <span style="color:#ea580c;">&#9632;</span> Thing/concept<br>
      <span style="color:#9333ea;">&#9632;</span> Mixed theme<br>
      <span style="color:#9ca3af;">&#9632;</span> Unresolved<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)

    out_path = OUT_DIR / "eindhoven_streets_map.html"
    m.save(str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
