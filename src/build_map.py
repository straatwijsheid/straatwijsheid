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

# The ~50 raw subcategories are too many to show distinctly without the map
# (and its legend) turning into visual noise. Bucket them into a handful of
# meaningful groups per top-level category, each rendered as a shade of that
# category's base hue -- close enough in color to still read as "person" /
# "place" / "thing" at a glance, distinct enough to tell the groups apart.
SUBGROUPS = {
    "person": [
        ("Arts (visual, sculpture, music)", "#1e3a8a",
         {"artist_visual", "artist_visual_sculptor", "musician_composer"}),
        ("Writers & legendary figures", "#2563eb",
         {"writer_poet", "mythological_figure", "literary_mythical_figure"}),
        ("Science & scholarship", "#3b82f6",
         {"scientist", "scientist_physician", "scientist_engineer", "engineer",
          "physician_medical", "legal_scholar", "cartographer", "aviation_pioneer",
          "architect_or_historian"}),
        ("Statesmen & military", "#60a5fa",
         {"monarch_statesman", "politician_statesman", "military",
          "military_naval_or_politician", "mayor_local", "boer_war_figure",
          "statesman_liberator", "industrialist_philips", "philips_engineer",
          "explorer", "activist", "human_rights_activist"}),
        ("Religious figures", "#93c5fd", {"religious"}),
        ("Other / unspecified", "#bfdbfe",
         {"other", "unspecified_individual", None}),
    ],
    "place": [
        ("Towns & regions", "#14532d",
         {"foreign_town", "foreign_town_wwii", "dutch_region", "dutch_town",
          "village", "city", "town", "country", "human settlement",
          "south_africa", "dutch_east_indies", "alpine_geography"}),
        ("Castles & estates", "#16a34a", {"castle_estate", "estate_feature"}),
        ("Natural features", "#22c55e",
         {"river", "mountain", "lake", "local_landscape_feature"}),
        ("Biblical & mythological", "#4ade80", {"biblical", "mythological"}),
        ("Local landmarks", "#86efac", {"local_landmark", None}),
    ],
    "thing": [
        ("Flora", "#7c2d12",
         {"flora", "flora_flower", "flora_herb", "flora_food", "wood_type", "fungus"}),
        ("Fauna", "#c2410c",
         {"fauna", "fauna_butterfly", "fauna_mammal", "fauna_fish", "fauna_and_flora"}),
        ("Culture & craft", "#ea580c",
         {"instrument", "occupation_guild", "occupation_guild_textile",
          "fiction_title_or_motif", "sport", "currency", "dynasty"}),
        ("Science & technology", "#fb923c",
         {"astronomy", "technology_term", "mineral", "industrial_philips_term",
          "infrastructure", "vessel_type"}),
        ("Development / other", "#fed7aa",
         {"development_concept", "local_landscape_feature", "local_landmark",
          "dutch_east_indies", "mythological", "military", None}),
    ],
}


def subgroup_color(category: str, subcategory) -> tuple[str, str]:
    """Returns (group_label, color) for a (category, subcategory) pair,
    falling back to the flat category color when category itself isn't
    one of person/place/thing (mixed, unresolved, unclear)."""
    groups = SUBGROUPS.get(category)
    if not groups:
        return category, CATEGORY_COLORS.get(category, "#9ca3af")
    for label, color, members in groups:
        if subcategory in members:
            return label, color
    # subcategory exists but wasn't anticipated in the grouping -- fall back
    # to the category's own base color rather than silently drop it
    return "Other / unspecified", CATEGORY_COLORS.get(category, "#9ca3af")

SOURCE_LABELS = {
    "wikidata": "Wikidata match",
    "wikidata_surname_only": "Wikidata (surname only, individual not identified)",
    "buurt_theme_override": "inferred from neighborhood theme (overrode a weaker individual match)",
    "buurt_theme_fallback": "inferred from neighborhood theme (no individual match found)",
    "title_heuristic": "inferred from a person-title prefix in the name",
    "wikidata_weak_match": "Wikidata (weak/unreliable match)",
    "wikidata_low_similarity": "Wikidata (low-confidence match)",
    "wikidata_no_match": "no match found",
    "surname_unsupported": "Wikidata surname match rejected (no corroborating evidence)",
    "web_search": "individually researched via web search",
    "claude_knowledge": "individually researched from general knowledge (not web-verified)",
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
    trusted_entity_sources = {"wikidata", "wikidata_surname_only", "wikidata_thing_match", "web_search", "claude_knowledge"}
    if entity and source not in trusted_entity_sources:
        entity = None

    if entity:
        origin = f"Likely named after: <b>{entity}</b>" + (f" &mdash; {desc}" if desc else "")
        url = clean(row.get("source_url"))
        if url:
            origin += f' &nbsp;<a href="{url}" target="_blank" rel="noopener">[source]</a>'
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
    streets["source_url"] = streets["name"].map(lambda n: final.get(n, {}).get("source_url"))

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
        # color only reflects a specific, trusted identification (real entity_label);
        # a street classified purely by buurt theme (no confirmed namesake) renders
        # as unresolved gray -- the tooltip still explains the theme-based guess,
        # but the color coding itself only highlights what's actually confirmed
        has_specific_entity = isinstance(row["entity_label"], str) and bool(row["entity_label"])
        if has_specific_entity:
            subcat = row["subcategory"] if isinstance(row["subcategory"], str) and row["subcategory"] else None
            _, color = subgroup_color(row["category"], subcat)
        else:
            color = CATEGORY_COLORS["unresolved"]
        explanation = street_explanation(row)
        tooltip = f"<b>{row['name']}</b><br>{explanation}"
        folium.GeoJson(
            row["geometry"],
            style_function=lambda _, c=color: {"color": c, "weight": 3, "opacity": 0.8},
            tooltip=folium.Tooltip(tooltip, sticky=True),
            popup=folium.Popup(tooltip, max_width=320),
        ).add_to(street_layer)
    street_layer.add_to(m)

    def subgroup_rows(category):
        return "".join(
            f'<div style="margin:2px 0 2px 14px;"><span style="color:{color};">&#9632;</span> {label}</div>'
            for label, color, _ in SUBGROUPS[category]
        )

    legend_html = f"""
    <div id="legend-box" style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 10px 14px; border-radius: 6px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 13px;
                max-height: 70vh; overflow-y: auto;">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">
        <b>Street naming category</b>
        <button id="legend-toggle" onclick="
            var d = document.getElementById('legend-detail');
            var expanded = d.style.display !== 'none';
            d.style.display = expanded ? 'none' : 'block';
            this.textContent = expanded ? 'show detail' : 'hide detail';
          " style="font-size:11px; padding:2px 6px; cursor:pointer; border:1px solid #ccc;
                    border-radius:4px; background:#f8f8f8;">show detail</button>
      </div>
      <div style="margin-top:6px;">
        <span style="color:#2563eb;">&#9632;</span> Person<br>
        <span style="color:#16a34a;">&#9632;</span> Place<br>
        <span style="color:#ea580c;">&#9632;</span> Thing/concept<br>
        <span style="color:#9ca3af;">&#9632;</span> No specific reference confirmed
      </div>
      <div style="margin-top:4px; font-size:11px; color:#666; max-width:220px;">
        Color only shown when a specific namesake is confirmed (hover for details).
        A buurt-theme guess with no confirmed individual reference is shown gray,
        even though its category may still be known.
      </div>
      <div id="legend-detail" style="display:none; margin-top:8px; border-top:1px solid #eee; padding-top:6px;">
        <div style="color:#2563eb; font-weight:600;">Person</div>
        {subgroup_rows("person")}
        <div style="color:#16a34a; font-weight:600; margin-top:6px;">Place</div>
        {subgroup_rows("place")}
        <div style="color:#ea580c; font-weight:600; margin-top:6px;">Thing/concept</div>
        {subgroup_rows("thing")}
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)

    out_path = OUT_DIR / "eindhoven_streets_map.html"
    m.save(str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
