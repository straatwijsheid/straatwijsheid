# Map guide

`src/build_map.py` builds an interactive Leaflet map (via folium) from the classified streets: `output/streets_map.html` plus one data file per gemeente under `output/data/`. It is a static site: no server code, just files.
Serve it with `python3 -m http.server --directory build/output 8765` and open `http://localhost:8765/streets_map.html`. Opened straight from disk it works too, but loads the larger uncompressed files (see [Data files](#data-files)).

## What you see

**Streets.** Each street is a line. A street whose namesake is **identified** (it has a specific label from a trusted source) is drawn in colour; every other street is a thin grey line. Colour is deliberately reserved for confirmed namesakes: a street that only
inherits a kind from its buurt's theme is grey, even though its category is known (see [method.md](method.md)). The colour is the category's hue (blue person, green place, orange thing/concept); a darker or lighter shade of it marks the sub-group
(for example arts, science or statesmen among persons; towns, castles or natural features among places; flora, fauna or crafts among things). The sub-groups are buckets of the finer subcategories, defined in `SUBGROUPS` in `build_map.py`.

**Buurt themes.** Neighbourhood polygons are tinted with their naming theme's colour and carry the theme as a tooltip. A buurt with no theme is an outline only; a tooltip says whether it was analysed and had no named streets, or has not been analysed yet.

**Tooltips and popups.** Hovering a street shows a short answer to "what is this named after, and how sure are we": the namesake and its description (shortened if long), category and subcategory, a confidence label (high, medium, low), the basis
(Wikidata match, OpenStreetMap etymology tag, inferred from the neighbourhood theme...), and the evidence tier. Clicking opens the full text, including the `[source]` link where there is one. Tooltips are capped in width and wrap; they never include links, since a tooltip vanishes when the pointer moves.

**Help name it.** For a street at tier 3 to 5, the click popup invites the reader to contribute. If the gemeente's review sheet asks about the street, the link goes to that sheet, anchored to the street's buurt (or section); the map reads the published `REVIEW.md` when it is built, so a link never points at a street that is not there. Other tier 3 to 5 streets link to the general call to contribute in the knowledge repository.

**Evidence tiers** (1 identified with external evidence ... 5 not identified) are shown in each street's tooltip and explained in the legend. They are defined in `src/tiers.py`.

**Legend** (bottom left): the three categories, grey for "no specific reference confirmed", a note on what colour means, the tiers, and a link to help name the unidentified streets. *Show detail* expands the sub-groups with their colours.

**Footer**: where the build came from: the code commit, the knowledge commit and the OpenStreetMap etymology snapshot date (from `output/PROVENANCE.json`), and the data attribution (OpenStreetMap contributors, CBS/PDOK, Wikidata; see [NOTICE.md](../NOTICE.md)).

## The panel (top right)

- **Search.** Type at least two letters to find a gemeente, a buurt or a street; results are grouped, and each shows its gemeente (names repeat). Pick one (click, or arrows and Enter) to show only that gemeente and fly to the result. A street is highlighted and its popup opens;
  if its layer is switched off, it is switched on. Escape clears. The index loads the first time the box is used.
- **Gemeente checkboxes** with street counts. Only the default gemeente (Eindhoven) is on at load. Ticking one loads its data and refits the view to the selection. *only* shows just that gemeente.
- **Layers.** *Streets* (roads and pedestrian streets), *Paths* (footway, cycleway, track), *Roads under construction*, and *Buurt themes* (all gemeenten) are independent switches. A street belongs to one of the first three by its OpenStreetMap type (`way_class`), so switching
  Streets off leaves paths and roads under construction showing. All three are drawn the same way: coloured if identified, grey otherwise.

## Data files

The data is split so a visitor loads only what they look at:

| File | Holds | Loaded |
|---|---|---|
| `streets_map.html` | the map, the panel, the legend, the render settings (palette, basis labels, tier names) | always |
| `data/gm####.js` | one gemeente's streets as GeoJSON, named by CBS code (`gm0772` is Eindhoven) | the first time the gemeente is switched on |
| `data/buurten.js` | the buurt polygons of every gemeente, with themes | at start |
| `data/search.js` | name, gemeente and bounding box of every street and buurt | the first time the search box is used |

Each file is written twice: plain `.js` and a pre-gzipped `.js.gz` several times smaller. Over http(s) the page fetches the `.gz` and decompresses it in the browser (`DecompressionStream`); if that fails, or when the page is opened from disk, it falls
back to the plain script. The data files are `<script>` files rather than `fetch`ed JSON so the page also works from disk.

Coordinates are rounded to about a metre and lightly simplified, which is invisible on the map and keeps the files smaller. Properties use short keys (`n` name, `k` colour index, `e` entity, `c` category, `s` subcategory, `f` confidence, `l` confidence label,
`b` basis, `t` tier, `d` description, `u` source URL, `w` way class: `p` path, `c` under construction, `a` the anchor of the street in its gemeente's review sheet, set only when the sheet asks about it); they are set in `build_map.py`.

## Building and checking it

```bash
.venv/bin/python src/build_map.py       # or: pipeline.py rebuild
```

It reads `raw/streets.geojson`, `raw/buurten.geojson`, `enriched/streets_final.json` and `enriched/buurt_themes_full.json`, and writes the map, `data/` and `PROVENANCE.json` into `output/`. It rewrites `data/` completely, so removed gemeenten do not leave stale files.
`src/analyze.py` imports its colour grouping, so the clustering analysis and the map agree on the sub-groups.

## Limits

- A single page loads and draws one or a few gemeenten at a time; showing the whole country at once needs tiled data (issue #45).
- The search index is one file; it will need splitting as coverage grows (#52, #45).
- The basemap is the OpenStreetMap standard tile layer, used under its tile usage policy (see [NOTICE.md](../NOTICE.md)); the provider is the `tile_url` setting.
