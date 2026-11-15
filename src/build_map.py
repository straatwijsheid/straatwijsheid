"""Build an interactive map of Eindhoven streets colored by naming category,
with buurt polygons showing the detected theme on hover/click."""
import json
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import shapely
from branca.element import MacroElement
from jinja2 import Template

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
          "fiction_title_or_motif", "sport", "currency", "dynasty",
          "architecture_term", "archaeology_term"}),
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


# reconcile only keeps a plausible person for title_heuristic rows
TRUSTED_ENTITY_SOURCES = {"wikidata", "wikidata_surname_only", "web_search", "claude_knowledge", "title_heuristic"}
UNRESOLVED_TEXT = "Origin not identified (no confident match found)"


class StreetLayer(MacroElement):
    """One Leaflet layer holding all of a gemeente's streets. Each feature carries only
    geometry + a few short properties; style and tooltip/popup HTML are built in the
    browser from them, so the file doesn't repeat per-street markup.
    Gray streets: {n: name}. Colored: {n, k: palette index, e: entity, d: description,
    u: source url, c: category, s: subcategory, f: confidence, l: conf label, b: source}."""
    _template = Template("""
        {% macro script(this, kwargs) %}
        (function() {
            var pal = {{ this.palette }}, basis = {{ this.basis }}, gray = {{ this.gray }};
            var esc = function(t) { return String(t).replace(/[&<>"']/g,
                function(c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); };
            var tpl = function(f) {
                var p = f.properties, h = "<b>" + esc(p.n) + "</b><br>";
                if (p.e === undefined) return h + {{ this.unresolved }};
                h += "Likely named after: <b>" + esc(p.e) + "</b>" + (p.d ? " &mdash; " + esc(p.d) : "");
                if (p.u) h += ' &nbsp;<a href="' + esc(p.u) + '" target="_blank" rel="noopener">[source]</a>';
                return h + "<br>Category: " + esc(p.c) + "/" + esc(p.s || "") + " &middot; confidence: " + p.l + " (" + p.f
                    + ")<br>Basis: " + esc(basis[p.b] || p.b || "unknown");
            };
            var layer = L.geoJson({{ this.data }}, {
                style: function(f) { return f.properties.k === undefined ? gray
                    : {color: pal[f.properties.k], weight: 3, opacity: 0.8}; },
                onEachFeature: function(f, l) {
                    l.bindTooltip(tpl(f), {sticky: true});
                    l.bindPopup(tpl(f), {maxWidth: 320});
                }
            });
            layer.addTo({{ this._parent.get_name() }});
        })();
        {% endmacro %}
    """)

    def __init__(self, features: list, palette: list, basis: dict, gray: dict, unresolved: str):
        super().__init__()
        self._name = "StreetLayer"
        j = lambda o: json.dumps(o, separators=(",", ":"), ensure_ascii=False)
        self.data = j({"type": "FeatureCollection", "features": features})
        self.palette, self.basis, self.gray, self.unresolved = j(palette), j(basis), j(gray), j(unresolved)


def round_geom(g, nd=5):
    """~1 m precision plus ~0.5 m simplification: invisible on the map, ~3x smaller."""
    g = g.simplify(0.000005, preserve_topology=True)
    return shapely.transform(g, lambda c: np.round(c, nd))


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

    if not row.get("analyzed", True):
        return "Not yet analyzed (street geometry only)"

    if category == "unresolved" or category is None:
        return UNRESOLVED_TEXT

    # only trust the Wikidata entity_label when it's actually the source of
    # the final classification -- if a buurt-theme override replaced it,
    # showing the rejected guess (e.g. "Pink" the singer for a street about
    # ship types) would be actively misleading
    if entity and source not in TRUSTED_ENTITY_SOURCES:
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


def gemeente_panel(registry: list[dict], map_name: str) -> str:
    """Top-right control: multi-select checkboxes per gemeente (with an 'only' shortcut)
    plus on/off toggles for the street and buurt layers. Each gemeente owns one street
    FeatureGroup and one buurt FeatureGroup; toggling adds/removes them from the map,
    and the view refits to whatever is selected."""
    rows = "".join(
        f'''<div class="gm-row"><label><input type="checkbox" class="gm-check" data-g="{g["name"]}" checked>
        {g["name"]} <span class="gm-count">{g["streets"]:,} streets</span></label>
        <a href="#" class="gm-only" data-g="{g["name"]}">only</a></div>'''
        for g in registry
    )
    js_registry = json.dumps([
        {k: g[k] for k in ("name", "street_group", "buurt_group", "bounds")} for g in registry
    ])
    return """
    <div id="gm-panel" style="position:fixed; top:12px; right:12px; z-index:1000; background:white;
         padding:10px 14px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,0.3);
         font-family:sans-serif; font-size:13px; min-width:190px;">
      <style>
        #gm-panel .gm-row {display:flex; justify-content:space-between; align-items:center; gap:10px; margin:3px 0;}
        #gm-panel .gm-count {color:#888; font-size:11px;}
        #gm-panel .gm-only {font-size:11px; color:#2563eb; text-decoration:none;}
        #gm-panel .gm-sec {margin-top:8px; padding-top:6px; border-top:1px solid #eee;}
      </style>
      <b>Gemeente</b>
      __ROWS__
      <div class="gm-sec"><b>Layers</b>
        <div class="gm-row"><label><input type="checkbox" class="ly-check" data-l="streets" checked> Streets</label></div>
        <div class="gm-row"><label><input type="checkbox" class="ly-check" data-l="buurten" checked> Buurt themes</label></div>
      </div>
    </div>
    <script>
    window.addEventListener('load', function () {
      var map = window[__MAP__], G = __REGISTRY__;
      var on = {}, layers = {streets: true, buurten: true};
      G.forEach(function (g) { on[g.name] = true; });

      function apply(refit) {
        var bounds = null;
        G.forEach(function (g) {
          [['streets', g.street_group], ['buurten', g.buurt_group]].forEach(function (p) {
            var layer = window[p[1]], want = on[g.name] && layers[p[0]];
            if (want && !map.hasLayer(layer)) { map.addLayer(layer); if (p[0] === 'buurten') layer.bringToBack(); }
            if (!want && map.hasLayer(layer)) map.removeLayer(layer);
          });
          if (on[g.name]) { var b = L.latLngBounds(g.bounds); bounds = bounds ? bounds.extend(b) : b; }
        });
        if (refit && bounds) map.fitBounds(bounds, {padding: [20, 20], animate: false});
      }
      function sync() {
        document.querySelectorAll('.gm-check').forEach(function (c) { c.checked = on[c.dataset.g]; });
      }
      document.querySelectorAll('.gm-check').forEach(function (c) {
        c.addEventListener('change', function () { on[c.dataset.g] = c.checked; apply(true); });
      });
      document.querySelectorAll('.gm-only').forEach(function (a) {
        a.addEventListener('click', function (e) {
          e.preventDefault();
          G.forEach(function (g) { on[g.name] = (g.name === a.dataset.g); });
          sync(); apply(true);
        });
      });
      document.querySelectorAll('.ly-check').forEach(function (c) {
        c.addEventListener('change', function () { layers[c.dataset.l] = c.checked; apply(false); });
      });
      // fitBounds on a zero-sized container clamps to max zoom, so wait until the map has a size
      function initialFit() {
        map.invalidateSize();
        if (map.getSize().x === 0) return false;
        apply(true);
        return true;
      }
      if (!initialFit()) { map.on('resize', function once() { if (initialFit()) map.off('resize', once); }); }
    });
    </script>
    """.replace("__ROWS__", rows).replace("__MAP__", json.dumps(map_name)).replace("__REGISTRY__", js_registry)


def main():
    streets = gpd.read_file(DATA_DIR / "raw" / "streets.geojson")
    # a street name can exist in several gemeenten, so everything is keyed by (gemeente, name)
    final = {(r["gemeente"], r["street"]): r
             for r in json.loads((DATA_DIR / "enriched" / "streets_final.json").read_text())}
    themes = {(t.get("gemeente", "Eindhoven"), t["buurt"]): t
              for t in json.loads((DATA_DIR / "enriched" / "buurt_themes_full.json").read_text())["buurten"]}
    buurten = gpd.read_file(DATA_DIR / "raw" / "buurten.geojson")
    streets["geometry"] = streets.geometry.apply(round_geom)
    buurten["geometry"] = buurten.geometry.apply(round_geom)

    keys = list(zip(streets["gemeente"], streets["name"]))
    for field, default in (("category", "unresolved"), ("subcategory", None), ("confidence", None),
                           ("source", None), ("entity_label", None), ("entity_description", None),
                           ("buurt_theme", None), ("source_url", None)):
        streets[field] = [final.get(k, {}).get(field, default) for k in keys]

    streets["analyzed"] = [k in final for k in keys]
    gemeenten = sorted(streets["gemeente"].unique())
    analyzed_gemeenten = set(streets.loc[streets["analyzed"], "gemeente"])
    # initial view is a placeholder; the panel's load handler fits to the selected gemeenten
    m = folium.Map(location=[51.44, 5.47], zoom_start=12, tiles="OpenStreetMap")

    buurt_groups = {g: folium.FeatureGroup(name=f"Buurt themes: {g}", show=True) for g in gemeenten}
    street_groups = {g: folium.FeatureGroup(name=f"Streets: {g}", show=True) for g in gemeenten}

    for _, row in buurten.iterrows():
        theme = themes.get((row["gemeente"], row["name"]))
        if not theme:
            # buurt not labeled yet: outline only, so the area is still visible
            folium.GeoJson(
                row["geometry"],
                style_function=lambda _: {"fillOpacity": 0, "color": "#6b7280", "weight": 1, "dashArray": "4"},
                tooltip=f"{row['name']} ({row['wijk']}): " + (
                    "no theme assigned (no named streets here)" if row["gemeente"] in analyzed_gemeenten
                    else "naming theme not yet analyzed"),
            ).add_to(buurt_groups[row["gemeente"]])
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
        ).add_to(buurt_groups[row["gemeente"]])
    for g in gemeenten:
        buurt_groups[g].add_to(m)

    palette = []
    def color_index(c):
        if c not in palette:
            palette.append(c)
        return palette.index(c)

    feats = {g: [] for g in gemeenten}
    for _, row in streets.iterrows():
        # color only reflects a specific, identified namesake (real entity_label);
        # everything else is thin gray with one shared "origin not identified" tooltip
        # (a buurt's naming theme is shown by the buurt polygon itself)
        geom = row["geometry"].__geo_interface__
        entity = row["entity_label"] if isinstance(row["entity_label"], str) and row["entity_label"] else None
        if entity and row["source"] not in TRUSTED_ENTITY_SOURCES:
            entity = None  # e.g. a weak Wikidata guess: don't present it as identified
        if entity is None or not row.get("analyzed", True):
            feats[row["gemeente"]].append({"type": "Feature", "properties": {"n": row["name"]}, "geometry": geom})
            continue
        subcat = row["subcategory"] if isinstance(row["subcategory"], str) and row["subcategory"] else None
        _, color = subgroup_color(row["category"], subcat)
        conf = row["confidence"]
        conf = None if conf is None or conf != conf else conf
        props = {"n": row["name"], "k": color_index(color), "e": entity, "c": row["category"], "s": subcat or "",
                 "f": conf, "l": "high" if (conf or 0) >= 0.75 else "medium" if (conf or 0) >= 0.5 else "low",
                 "b": row["source"] if isinstance(row["source"], str) else ""}
        for key, field in (("d", "entity_description"), ("u", "source_url")):
            if isinstance(row[field], str) and row[field]:
                props[key] = row[field]
        feats[row["gemeente"]].append({"type": "Feature", "properties": props, "geometry": geom})
    gray_style = {"color": CATEGORY_COLORS["unresolved"], "weight": 1, "opacity": 0.5}
    for g in gemeenten:
        StreetLayer(feats[g], palette, SOURCE_LABELS, gray_style, UNRESOLVED_TEXT).add_to(street_groups[g])
        street_groups[g].add_to(m)

    registry = []
    for g in gemeenten:
        gs = streets[streets["gemeente"] == g]
        minx, miny, maxx, maxy = gs.total_bounds
        registry.append({
            "name": g, "streets": len(gs),
            "street_group": street_groups[g].get_name(), "buurt_group": buurt_groups[g].get_name(),
            "bounds": [[miny, minx], [maxy, maxx]],
        })
    m.get_root().html.add_child(folium.Element(gemeente_panel(registry, m.get_name())))

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

    out_path = OUT_DIR / "streets_map.html"
    m.save(str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
