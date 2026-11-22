"""Build an interactive map of Dutch streets colored by naming category,
with buurt polygons showing the detected theme on hover/click."""
import gzip
import json
from pathlib import Path

from tiers import TIER_NAMES, evidence_tier  # src/ is on sys.path when run as a script

import folium
import geopandas as gpd
import numpy as np
import shapely
import re

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
    "osm_etymology": "OpenStreetMap name:etymology tag, resolved via Wikidata",
    "claude_knowledge": "individually researched from general knowledge (not web-verified)",
}


# reconcile only keeps a plausible person for title_heuristic rows
TRUSTED_ENTITY_SOURCES = {"wikidata", "wikidata_surname_only", "web_search", "osm_etymology", "claude_knowledge", "title_heuristic"}
DEFAULT_GEMEENTE = "Eindhoven"  # the only gemeente switched on at load; the rest load when ticked
UNRESOLVED_TEXT = "Origin not identified (no confident match found)"


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


def gemeente_panel(registry: list[dict], map_name: str, render: dict, initial: list[str]) -> str:
    """Top-right control: multi-select checkboxes per gemeente (with an 'only' shortcut)
    plus on/off toggles for the street and buurt layers. A gemeente's data lives in its own
    script file (data/<slug>.js) that is fetched the first time it is switched on; it then
    owns one street and one buurt FeatureGroup that toggling adds/removes. The view refits
    to whatever is selected."""
    rows = "".join(
        f'''<div class="gm-row"><label><input type="checkbox" class="gm-check" autocomplete="off" data-g="{g["name"]}"{" checked" if g["name"] in initial else ""}>
        {g["name"]} <span class="gm-count" data-g="{g["name"]}">{g["streets"]:,} streets</span></label>
        <a href="#" class="gm-only" data-g="{g["name"]}">only</a></div>'''
        for g in registry
    )
    js_registry = json.dumps([
        {k: g[k] for k in ("name", "slug", "bounds")} for g in registry
    ])
    return """
    <div id="gm-panel" style="position:fixed; top:12px; right:12px; z-index:1000; background:white;
         padding:10px 14px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,0.3);
         font-family:sans-serif; font-size:13px; min-width:190px;
         max-height:calc(100vh - 24px); overflow-y:auto; box-sizing:border-box;">
      <style>
        #gm-panel .gm-row {display:flex; justify-content:space-between; align-items:center; gap:10px; margin:3px 0;}
        #gm-panel .gm-count {color:#888; font-size:11px;}
        #gm-panel .gm-only {font-size:11px; color:#2563eb; text-decoration:none;}
        #gm-panel .gm-sec {margin-top:8px; padding-top:6px; border-top:1px solid #eee;}
      </style>
      <b>Streets: gemeente</b>
      __ROWS__
      <div class="gm-sec"><b>Layers</b>
        <div class="gm-row"><label><input type="checkbox" class="ly-check" autocomplete="off" data-l="streets" checked> Streets</label></div>
        <div class="gm-row"><label><input type="checkbox" class="ly-check" autocomplete="off" data-l="paths" checked> Paths (footway, cycleway, track)</label></div>
        <div class="gm-row"><label><input type="checkbox" class="ly-check" autocomplete="off" data-l="planned" checked> Roads under construction</label></div>
        <div class="gm-row"><label><input type="checkbox" class="ly-check" autocomplete="off" data-l="buurten" checked> Buurt themes (all gemeenten)</label></div>
      </div>
    </div>
    <script>
    window.addEventListener('load', function () {
      var map = window[__MAP__], G = __REGISTRY__, R = __RENDER__, INITIAL = __INITIAL__;
      var on = {}, layers = {streets: true, buurten: true, paths: true, planned: true}, built = {}, loading = {};
      G.forEach(function (g) { on[g.name] = INITIAL.indexOf(g.name) >= 0; });

      var esc = function (t) { return String(t).replace(/[&<>"']/g,
        function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
      var tpl = function (f) {
        var p = f.properties, h = "<b>" + esc(p.n) + "</b><br>";
        var tier = p.t ? "<br><span style='color:#555'>Evidence tier " + p.t + ": " + esc(R.tiers[p.t]) + "</span>" : "";
        if (p.e === undefined) {
          if (p.t === undefined || p.t === 5) return h + R.unresolved + (p.t === 5 && p.c && p.c !== "unresolved" ? "<br>Best guess: " + esc(p.c) + "/" + esc(p.s || "") : "") + tier;
          return h + "No specific namesake identified<br>Kind: " + esc(p.c) + (p.s ? "/" + esc(p.s) : "") + tier;
        }
        h += "Likely named after: <b>" + esc(p.e) + "</b>" + (p.d ? " &mdash; " + esc(p.d) : "");
        if (p.u) h += ' &nbsp;<a href="' + esc(p.u) + '" target="_blank" rel="noopener">[source]</a>';
        return h + "<br>Category: " + esc(p.c) + "/" + esc(p.s || "") + " &middot; confidence: " + p.l + " (" + p.f
          + ")<br>Basis: " + esc(R.basis[p.b] || p.b || "unknown") + tier;
      };
      // Visual line and hover/click zone are separate: the visible line stays thin and
      // faint (non-interactive), while an invisible, wider line on top catches the
      // mouse. Gray hit zones go under the colored ones so a gray street never
      // steals hover from a colored one it runs alongside.
      function buildPart(data, want) {
        var grp = L.featureGroup();
        var isColored = function (f) { return f.properties.k !== undefined; };
        var hits = function (keep, weight) {
          return L.geoJson(data, {
            filter: function (f) { return want(f) && keep(f); },
            style: function () { return {weight: weight, opacity: 0, fill: false}; },
            onEachFeature: function (f, l) {
              l.bindTooltip(tpl(f), {sticky: true});
              l.bindPopup(tpl(f), {maxWidth: 320});
            }
          });
        };
        hits(function (f) { return !isColored(f); }, 14).addTo(grp);
        L.geoJson(data, {
          filter: want,
          interactive: false,
          style: function (f) { return isColored(f) ? {color: R.palette[f.properties.k], weight: 3, opacity: 0.8} : R.gray; }
        }).addTo(grp);
        hits(isColored, 9).addTo(grp);
        return grp;
      }
      // streets are drawn in three parts so the panel can switch paths and planned roads on and off:
      // p.w is absent for streets, "p" for paths (footway, cycleway, track...), "c" for roads under construction
      function buildStreets(data) {
        var grp = L.featureGroup(), parts = {};
        [["s", function (f) { return !f.properties.w; }], ["p", function (f) { return f.properties.w === "p"; }],
         ["c", function (f) { return f.properties.w === "c"; }]].forEach(function (d) { parts[d[0]] = buildPart(data, d[1]); });
        grp.parts = parts;
        return grp;
      }
      function syncParts(grp) {
        Object.keys(grp.parts).forEach(function (k) {
          var show = k === "s" || (k === "p" ? layers.paths : layers.planned), part = grp.parts[k];
          if (show && !grp.hasLayer(part)) grp.addLayer(part);
          if (!show && grp.hasLayer(part)) grp.removeLayer(part);
        });
      }
      // buurt polygons: p.t = theme text, p.c = colour; no p.t means no theme (p.o says why)
      function buildBuurten(data) {
        return L.geoJson(data, {
          style: function (f) {
            var p = f.properties;
            return p.t === undefined ? {fillOpacity: 0, color: "#6b7280", weight: 1, dashArray: "4"}
                                     : {fillColor: p.c, color: p.c, weight: 1, fillOpacity: 0.15};
          },
          onEachFeature: function (f, l) {
            var p = f.properties;
            if (p.t === undefined) {
              l.bindTooltip(esc(p.n) + " (" + esc(p.w) + "): " + (p.o ? "no theme assigned (no named streets here)"
                : "naming theme not yet analyzed"), {sticky: true});
            } else {
              l.bindTooltip(esc(p.n) + ": " + esc(p.t), {sticky: true});
              l.bindPopup("<b>" + esc(p.n) + "</b> (" + esc(p.w) + ")<br>" + esc(p.t) + "<br>confidence: " + p.f);
            }
          }
        });
      }
      function countLabel(name) { return document.querySelector('.gm-count[data-g="' + name.replace(/"/g, '\\"') + '"]'); }
      // Data files are shipped twice: plain .js (works when the page is opened from disk) and a
      // pre-gzipped .js.gz (about 5x smaller; used over http(s) where fetch + DecompressionStream
      // are available). Any failure on the gzip path falls back to the plain script.
      function loadScript(url, ok, fail) {
        function plain() {
          var sc = document.createElement("script");
          sc.src = url; sc.onload = ok; sc.onerror = function () { fail(url); };
          document.head.appendChild(sc);
        }
        if (!/^https?:$/.test(location.protocol) || !window.DecompressionStream || !window.fetch) return plain();
        fetch(url + ".gz").then(function (r) {
          if (!r.ok) throw new Error(r.status);
          return new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).text();
        }).then(function (code) {
          var sc = document.createElement("script");
          sc.text = code;               // inline scripts run synchronously on insertion
          document.head.appendChild(sc);
          ok();
        }, plain);                      // only a fetch/decompress failure falls back, not an error in ok()
      }
      function load(g) {
        if (built[g.name]) return Promise.resolve(built[g.name]);
        if (loading[g.name]) return loading[g.name];
        var lab = countLabel(g.name), orig = lab && lab.textContent;
        if (lab) lab.textContent = "loading\u2026";
        return loading[g.name] = new Promise(function (resolve, reject) {
          loadScript("data/" + g.slug + ".js", function () {
            var d = window.GM_DATA[g.slug];
            built[g.name] = buildStreets(d);
            if (lab) lab.textContent = orig;
            resolve(built[g.name]);
          }, function (url) {
            delete loading[g.name];
            if (lab) lab.textContent = "failed to load";
            reject(new Error("could not load " + url));
          });
        });
      }

      // Buurt polygons for every gemeente come from one file loaded at startup; the gemeente
      // selector only controls which gemeenten' streets are loaded and drawn.
      var buurtLayer = null, allBounds = L.latLngBounds(G.map(function (g) { return g.bounds; })[0]);
      G.forEach(function (g) { allBounds.extend(g.bounds); });
      function loadBuurten() {
        loadScript("data/buurten.js", function () { buurtLayer = buildBuurten(window.GM_BUURTEN); apply(false); },
                   function (url) { console.error("could not load " + url); });
      }
      // The view follows the selected gemeenten' streets (the whole region if none are selected).
      function fitSelection() {
        var bounds = null;
        G.forEach(function (g) { if (on[g.name]) { var b = L.latLngBounds(g.bounds); bounds = bounds ? bounds.extend(b) : b; } });
        map.fitBounds(bounds || allBounds, {padding: [20, 20], animate: false});
      }
      function apply(refit) {
        if (buurtLayer) {
          if (layers.buurten && !map.hasLayer(buurtLayer)) { map.addLayer(buurtLayer); buurtLayer.bringToBack(); }
          if (!layers.buurten && map.hasLayer(buurtLayer)) map.removeLayer(buurtLayer);
        }
        G.forEach(function (g) {
          if (on[g.name] && !built[g.name]) { load(g).then(function () { apply(false); }, function () {}); return; }
          var layer = built[g.name];
          if (!layer) return;
          var want = on[g.name] && layers.streets;
          if (want && !map.hasLayer(layer)) map.addLayer(layer);
          if (!want && map.hasLayer(layer)) map.removeLayer(layer);
          syncParts(layer);
        });
        if (refit) fitSelection();
      }
      function sync() {
        document.querySelectorAll('.gm-check').forEach(function (c) { c.checked = on[c.dataset.g]; });
      }
      sync(); document.querySelectorAll('.ly-check').forEach(function (c) { c.checked = layers[c.dataset.l]; });
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
      loadBuurten();
      if (!initialFit()) { map.on('resize', function once() { if (initialFit()) map.off('resize', once); }); }
    });
    </script>
    """.replace("__ROWS__", rows).replace("__MAP__", json.dumps(map_name)).replace("__REGISTRY__", js_registry)\
        .replace("__RENDER__", json.dumps(render, separators=(",", ":"), ensure_ascii=False)).replace("__INITIAL__", json.dumps(initial))


W = {"path": "p", "planned": "c"}   # way_class -> the one-letter code in the feature properties (streets carry none)


def main():
    streets = gpd.read_file(DATA_DIR / "raw" / "streets.geojson")
    # a street name can exist in several gemeenten, so everything is keyed by (gemeente, name)
    final = {(r["gemeente"], r["street"]): r
             for r in json.loads((DATA_DIR / "enriched" / "streets_final.json").read_text())}
    themes = {(t["gemeente"], t["buurt"]): t
              for t in json.loads((DATA_DIR / "enriched" / "buurt_themes_full.json").read_text())["buurten"]}
    buurten = gpd.read_file(DATA_DIR / "raw" / "buurten.geojson")
    streets["geometry"] = streets.geometry.apply(round_geom)
    buurten["geometry"] = buurten.geometry.apply(round_geom)

    keys = list(zip(streets["gemeente"], streets["name"]))
    for field, default in (("category", "unresolved"), ("subcategory", None), ("confidence", None),
                           ("source", None), ("entity_label", None), ("entity_description", None),
                           ("buurt_theme", None), ("source_url", None), ("evidence_tier", None), ("notes", None)):
        streets[field] = [final.get(k, {}).get(field, default) for k in keys]

    streets["analyzed"] = [k in final for k in keys]
    streets["evidence_tier"] = [int(t) if t == t and t is not None else evidence_tier(final[k]) if k in final else 5
                                for t, k in zip(streets["evidence_tier"], keys)]
    gemeenten = sorted(streets["gemeente"].unique())
    analyzed_gemeenten = set(streets.loc[streets["analyzed"], "gemeente"])
    # initial view is a placeholder; the panel's load handler fits to the selected gemeenten
    m = folium.Map(location=[51.44, 5.47], zoom_start=12, tiles="OpenStreetMap")

    def slug(g):
        return re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-")

    bfeats = {g: [] for g in gemeenten}
    for _, row in buurten.iterrows():
        theme = themes.get((row["gemeente"], row["name"]))
        props = {"n": row["name"], "w": row["wijk"]}
        if theme:
            props.update(t=theme["theme"], c=CATEGORY_COLORS.get(theme["category"], "#9ca3af"), f=theme["confidence"])
        else:
            # not labeled: outline only, so the area is still visible; o=1 if analyzed but no streets
            props["o"] = int(row["gemeente"] in analyzed_gemeenten)
        bfeats[row["gemeente"]].append({"type": "Feature", "properties": props, "geometry": row["geometry"].__geo_interface__})

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
            gprops = {"n": row["name"]}
            if W.get(row.get("way_class")):
                gprops["w"] = W[row["way_class"]]
            if row.get("analyzed", True):
                gprops["t"] = int(row["evidence_tier"])
                gsub = row["subcategory"] if isinstance(row["subcategory"], str) and row["subcategory"] else ""
                gprops["c"] = row["category"] if isinstance(row["category"], str) else "unresolved"
                gprops["s"] = gsub
            feats[row["gemeente"]].append({"type": "Feature", "properties": gprops, "geometry": geom})
            continue
        subcat = row["subcategory"] if isinstance(row["subcategory"], str) and row["subcategory"] else None
        _, color = subgroup_color(row["category"], subcat)
        conf = row["confidence"]
        conf = None if conf is None or conf != conf else conf
        props = {"n": row["name"], "k": color_index(color), **({"w": W[row["way_class"]]} if W.get(row.get("way_class")) else {}), "e": entity, "c": row["category"], "s": subcat or "",
                 "f": conf, "l": "high" if (conf or 0) >= 0.75 else "medium" if (conf or 0) >= 0.5 else "low",
                 "b": row["source"] if isinstance(row["source"], str) else "", "t": int(row["evidence_tier"])}
        for key, field in (("d", "entity_description"), ("u", "source_url")):
            if isinstance(row[field], str) and row[field]:
                props[key] = row[field]
        feats[row["gemeente"]].append({"type": "Feature", "properties": props, "geometry": geom})
    gray_style = {"color": CATEGORY_COLORS["unresolved"], "weight": 1, "opacity": 0.5}
    # one script per gemeente, loaded on demand (a <script> rather than fetch() so the map
    # still works when streets_map.html is opened straight from disk)
    data_dir = OUT_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    for old in list(data_dir.glob("*.js")) + list(data_dir.glob("*.js.gz")):
        old.unlink()

    def write_js(path, text):
        path.write_text(text)
        path.with_name(path.name + ".gz").write_bytes(gzip.compress(text.encode("utf-8"), 9, mtime=0))

    registry = []
    for g in gemeenten:
        payload = {"type": "FeatureCollection", "features": feats[g]}
        write_js(data_dir / f"{slug(g)}.js",
            f"(window.GM_DATA=window.GM_DATA||{{}})[{json.dumps(slug(g))}]="
            + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n")
        gs = streets[streets["gemeente"] == g]
        minx, miny, maxx, maxy = gs.total_bounds
        registry.append({"name": g, "slug": slug(g), "streets": len(gs), "bounds": [[miny, minx], [maxy, maxx]]})
    allb = [f for g in gemeenten for f in bfeats[g]]
    write_js(data_dir / "buurten.js",
        "window.GM_BUURTEN=" + json.dumps({"type": "FeatureCollection", "features": allb},
                                          separators=(",", ":"), ensure_ascii=False) + ";\n")
    render = {"palette": palette, "basis": SOURCE_LABELS, "tiers": {str(k): v for k, v in TIER_NAMES.items()}, "gray": gray_style, "unresolved": UNRESOLVED_TEXT}
    initial = [DEFAULT_GEMEENTE] if DEFAULT_GEMEENTE in gemeenten else gemeenten
    m.get_root().html.add_child(folium.Element(gemeente_panel(registry, m.get_name(), render, initial)))

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
      <div style="margin-top:6px; font-size:11px; color:#666; max-width:220px;">
        <b>Evidence tier</b> (shown in each street's tooltip): 1 identified, external evidence &middot;
        2 identified from knowledge, unverified &middot; 3 kind known from the name &middot;
        4 kind inferred from the neighbourhood theme &middot; 5 not identified.
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
