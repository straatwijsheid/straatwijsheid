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

SOURCE_LABELS = {
    "wikidata": "Wikidata match",
    "wikidata_surname_only": "Wikidata (surname only, individual not identified)",
    "buurt_theme_override": "inferred from neighborhood theme (overrode a weaker individual match)",
    "buurt_theme_fallback": "inferred from neighborhood theme (no individual match found)",
    "title_heuristic": "inferred from a person-title prefix in the name",
    "wikidata_weak_match": "Wikidata (weak/unreliable match)",
    "wikidata_low_similarity": "Wikidata (low-confidence match)",
    "wikidata_no_match": "no match found",
}


def street_explanation(row) -> str:
    """A short, human-readable answer to 'what is this street actually named after,
    and how sure are we', for the map tooltip."""
    def clean(v):
        return v if isinstance(v, str) and v else None

    category = clean(row["category"]) or "unresolved"
    subcategory = clean(row["subcategory"]) or ""
    entity = clean(row["entity_label"])
    desc = clean(row["entity_description"])
    conf = row["confidence"]
    if isinstance(conf, float) and conf != conf:  # NaN check without importing math
        conf = None
    source = clean(row["source"])

    if category == "unresolved" or category is None:
        return "Origin not identified (no confident match found)"

    # only trust the Wikidata entity_label when it's actually the source of
    # the final classification -- if a buurt-theme override replaced it,
    # showing the rejected guess (e.g. "Pink" the singer for a street about
    # ship types) would be actively misleading
    trusted_entity_sources = {"wikidata", "wikidata_surname_only"}
    if entity and source not in trusted_entity_sources:
        entity = None

    if entity:
        origin = f"Likely named after: <b>{entity}</b>" + (f" &mdash; {desc}" if desc else "")
    else:
        theme = clean(row.get("buurt_theme"))
        if theme:
            origin = f"No specific match; fits neighborhood theme: <i>{theme}</i>"
        else:
            origin = f"Classified as {category}" + (f" ({subcategory})" if subcategory else "")

    basis = SOURCE_LABELS.get(source, source or "unknown")
    conf_label = "high" if (conf or 0) >= 0.75 else "medium" if (conf or 0) >= 0.5 else "low"
    return f"{origin}<br>Category: {category}/{subcategory} &middot; confidence: {conf_label} ({conf})<br>Basis: {basis}"


def main():
    streets = gpd.read_file(DATA_DIR / "raw" / "streets.geojson")
    final = {r["street"]: r for r in json.loads((DATA_DIR / "enriched" / "streets_final.json").read_text())}
    themes = {t["buurt"]: t for t in json.loads((DATA_DIR / "enriched" / "buurt_themes_full.json").read_text())["buurten"]}
    buurten = gpd.read_file(DATA_DIR / "raw" / "buurten.geojson")

    streets["category"] = streets["name"].map(lambda n: final.get(n, {}).get("category", "unresolved"))
    streets["subcategory"] = streets["name"].map(lambda n: final.get(n, {}).get("subcategory"))
    streets["confidence"] = streets["name"].map(lambda n: final.get(n, {}).get("confidence"))
    streets["source"] = streets["name"].map(lambda n: final.get(n, {}).get("source"))
    streets["entity_label"] = streets["name"].map(lambda n: final.get(n, {}).get("entity_label"))
    streets["entity_description"] = streets["name"].map(lambda n: final.get(n, {}).get("entity_description"))
    streets["buurt_theme"] = streets["name"].map(lambda n: final.get(n, {}).get("buurt_theme"))

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
        explanation = street_explanation(row)
        tooltip = f"<b>{row['name']}</b><br>{explanation}"
        folium.GeoJson(
            row["geometry"],
            style_function=lambda _, c=color: {"color": c, "weight": 3, "opacity": 0.8},
            tooltip=folium.Tooltip(tooltip, sticky=True),
            popup=folium.Popup(tooltip, max_width=320),
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
