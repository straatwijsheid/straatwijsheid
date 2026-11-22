# Pipeline guide

How a gemeente goes from nothing to a classified street list and a map. All commands run from the repository root with the project's virtualenv
(`.venv/bin/python`). Paths below are relative to the build directory (`build/`, see [Where things live](#where-things-live)) unless they start with `knowledge/`.

```
acquire  ->  wikidata  ->  reconcile  ->  themes  ->  reconcile  ->  rules (check / apply)  ->  analyze  ->  map  ->  CSVs
 OSM+PDOK     lookup        classify      buurt          again          override layers                    HTML       flat files
                            streets       themes
```

## The short version

```bash
.venv/bin/python src/pipeline.py bootstrap                # once: build directory, and the knowledge repository cloned into knowledge/
.venv/bin/python src/pipeline.py add Tilburg Breda        # new gemeenten, end to end (names or CBS codes; use the code when a name is shared, e.g. GM0373)
.venv/bin/python src/pipeline.py status                   # what is still missing at each stage
.venv/bin/python src/pipeline.py rebuild                  # after rules, overrides or knowledge changed
```

`add` runs stages 1 to 4 and 6 to 7 below; `rebuild` re-runs reconcile and the outputs (7), and with `--themes` the themes as well. Every stage is also a script you can run alone;
that is what to do when a stage fails or is long. A fresh checkout has no `build/` data: nothing is committed there, and everything in it can be recreated.

## The stages

| # | Stage | Command | Reads | Writes |
|---|---|---|---|---|
| 1 | acquire | `src/acquire.py <gemeente...>` | OpenStreetMap (Overpass), CBS buurten (PDOK), `knowledge/global/gemeenten*.json` | `raw/streets_gm####.geojson`, `raw/buurten_gm####.geojson`, then the combined `raw/streets.geojson`, `raw/buurten.geojson`; a dated snapshot entry in `raw/snapshots.json` |
| 2 | wikidata | `src/enrich_wikidata.py --missing` | the street names in `raw/streets.geojson` | `enriched/all_streets_wikidata.jsonl` (a cache: resumable, one record per name) |
| 3 | reconcile | `src/reconcile.py` | Wikidata cache, `raw/streets.geojson`, `enriched/buurt_themes_full.json`, the override layers in `knowledge/gemeenten/` | `enriched/streets_final.json` |
| 4 | themes | `src/themes.py` | `enriched/streets_final.json` | `enriched/buurt_themes_full.json` (themes for buurten that have none) |
| 5 | osm | `src/osm_etymology.py --refresh` | OpenStreetMap `name:etymology*` tags, Wikidata | `raw/osm_etymology_ways.json`, `enriched/osm_etymology.json`, `output/OSM_CHANGES.md` |
| 6 | rules | `src/rules/run.py --check` (or `--apply RULE`) | `streets_final.json`, knowledge lists | with `--apply`: `knowledge/gemeenten/<province>/<gemeente>/overrides/<rule>.json` |
| 7 | outputs | `src/analyze.py`, `src/build_map.py`, `src/export_csv.py` | `streets_final.json`, themes, `raw/*.geojson` | `output/wijk_theme_clustering.json`; `output/streets_map.html` + `output/data/`, `output/PROVENANCE.json`; `output/streets_classified.csv`, `output/buurt_themes.csv` |

Notes per stage:

1. **acquire.** The street network is taken from the outline of the gemeente's own CBS buurten, so no geocoding is involved, and every named `highway=*` way inside counts
   (`src/osm_streets.py`; each street keeps its OSM type, and a `way_class` of street, path or planned). Gemeenten that are merged, renamed or have a long official name need an entry
   in `knowledge/global/gemeenten.json`. A gemeente is identified by its CBS code (`GM0855`); the first fetch adds it to `knowledge/global/gemeenten_index.json`.
   Already fetched gemeenten are skipped (`--force` refetches; `--supplement` adds streets an older fetch missed; `--list` shows what is in `raw/`).
2. **wikidata.** Looks up each distinct street name once (the name without the road word, "straat", "laan"...) and caches the answer, so a rerun only does what is missing.
3. **reconcile.** A confident Wikidata match is trusted; a weak one gives way to a strongly themed buurt; the override layers are applied on top. It is a pure function of its inputs and is cheap, so it is run
   again whenever something it reads changes.
4. **themes.** A buurt's theme is what its classified streets mostly are. Hand-written themes (the first 394) are never touched; `--rebuild` re-derives all derived ones.
5. **osm.** Not part of `pipeline.py add` by default: run it with `pipeline.py rebuild --refresh-osm` (or `add ... --refresh-osm`). It currently fetches all of Noord-Brabant in one go. It records a dated snapshot and a per-way
   change report (`output/OSM_CHANGES.md`) so a refresh shows what changed in OpenStreetMap.
6. **rules.** Rules add what Wikidata cannot (species, composers, saints, directional roads, titles...), each into its own override layer. `--check` only prints what each rule proposes and how that compares with the data now; `--apply RULE`
   writes that rule's layer and prints how the layer changed. See [src/rules/README.md](../src/rules/README.md). Rules that need human review stay a human step, which is why `pipeline.py add` only checks.
7. **outputs.** Analyse whether themes cluster by wijk, build the map, export the CSVs, print the evidence-tier counts. `output/PROVENANCE.json` records the code commit, the knowledge commit and the OSM snapshot dates the build came from.

## Order matters

- **A new gemeente needs reconcile, themes, reconcile.** The themes are derived from classified streets, and reconcile uses themes to settle weak Wikidata matches, so the first pass produces the streets and
  the second lets the new themes act. `pipeline.py add` does this; when running stages by hand, do it yourself: `reconcile.py`, `themes.py`, `reconcile.py`.
- **After `--apply RULE`, run reconcile again** (and then the outputs). Layers are read by reconcile; the map and CSVs only change after it.
- **Wikidata before reconcile.** Reconcile only classifies names that are in the Wikidata cache, so a street not looked up yet is missing from `streets_final.json` and shows as not yet analysed on the map; `pipeline.py status` shows how many names are still to do.
- **Knowledge first.** A change to anything under `knowledge/` (lists, corrections, exclusions) takes effect only through the rules (`--apply`) and reconcile; `pipeline.py rebuild` runs the reconcile and outputs, not `--apply`.
- **Rules are applied by name.** Regenerating every layer at once would change thousands of reviewed entries, so `--apply-rules RULE ...` always names the rules (see #24).

## Network practicalities

- **Overpass** is often busy or refuses a busy IP. Acquire retries with growing pauses (`--retries`); a changed VPN endpoint has fixed a refusal. A different server can be set with `overpass_url` (below).
- **Wikidata** lookups are polite by default and faster when a contact is set: put it in `config.local.toml` (`wikidata_contact`, git-ignored) or in the `WIKIDATA_CONTACT` environment variable. It is sent in the User-Agent and is never
  written to a tracked file or an output. `pipeline.py add` stops at this stage if no contact is set and prints the command to run yourself; a long lookup is best run in your own shell, then continue with
  `pipeline.py rebuild --themes`. The README measures roughly 100 names a minute with a contact set.
- **PDOK** (CBS buurten) needs no key. See [NOTICE.md](../NOTICE.md) for the terms of every source.
- None of the unit tests need the network.

## Where things live

`python src/config.py` prints where everything is and which settings are in effect. Lookup order for each setting: environment variable, then `config.local.toml` (copy `config.example.toml`), then the default.

| Setting | Default |
|---|---|
| build directory (`raw/ enriched/ output/ cache/ names/`, rebuildable, never committed) | `build/` |
| knowledge directory (the knowledge repository) | `knowledge/` |
| Wikidata contact | none |
| Overpass URL | `https://overpass-api.de/api/interpreter` |
| Basemap tile URL and credit (`tile_url`, `tile_attribution`) | OpenStreetMap's tile server |

`pipeline.py bootstrap` creates the build directory and clones the knowledge repository (`--no-clone` only checks it is there). Core refuses a knowledge checkout whose `schema_version` it does not read (`src/schema.py`).

## Outside `pipeline.py`

- `src/osm_places.py --fetch` fetches named OSM geographic features (places, water, woods...) into `raw/osm_places.json`; the `osm_places` rule uses it.
- `src/names/run.py --build` builds the name-level candidate table (`names/candidates.jsonl`); `--backtest`, `--show` and `--propose` inspect it. The `name_resolver` rule uses it.
- `src/osm_report.py`, `src/osm_fixes.py`, `src/wikidata_fixes.py` write reports (`output/reports/`): how well we agree with OpenStreetMap's etymology tags, and fixes worth making in OSM or Wikidata.
- `src/knowledge.py --check` checks every shard of the knowledge repository against the registry.
- Tests: `for t in tests/test_*.py; do .venv/bin/python $t | tail -1; done`.

## When something fails

| Symptom | Likely cause and fix |
|---|---|
| `Overpass unavailable` / HTTP 429, 502 | busy server: rerun (finished gemeenten are skipped), raise `--retries`, change IP, or use another `overpass_url` |
| `Stage wikidata needs a Wikidata contact` | set `WIKIDATA_CONTACT` or `wikidata_contact`, or run the lookup yourself as the message says |
| `Incompatible knowledge repository` | the knowledge checkout and the code disagree on `schema_version`: update the one the message names |
| `No knowledge at ...` | run `pipeline.py bootstrap`, or point `knowledge_dir` at a checkout |
| `names N gemeenten` | two gemeenten share the name (Bergen): pass the CBS code |
| a gemeente is missing from the map | `pipeline.py status` shows which stage has not run for it |
