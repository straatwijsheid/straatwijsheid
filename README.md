# Straatwijsheid

*Where the streets have a name.*

A pipeline and an interactive map that work out what Dutch streets are named after: **a person, a place or a thing**,
with sub-kinds (composer, saint, tree, river, castle...), and test whether naming themes cluster by neighbourhood.

Current coverage: **all of Noord-Brabant, 59 gemeenten and about 44,600 named streets, paths and roads under construction**, built up wave by wave from Eindhoven outwards.
The long-term goal is the whole of the Netherlands, and a steadily growing share of streets we can actually identify.
Open work is tracked in the [issue tracker](https://github.com/straatwijsheid/straatwijsheid/issues).

**Live map: <https://straatwijsheid.github.io/straatwijsheid/>**

## Documentation

| | |
|---|---|
| [docs/method.md](docs/method.md) | the question, the evidence tiers, how a street is decided, the principles |
| [docs/pipeline.md](docs/pipeline.md) | the stages from OpenStreetMap to the map, commands, ordering, network practicalities |
| [docs/data-dictionary.md](docs/data-dictionary.md) | every field and value (generated from the code) |
| [src/rules/README.md](src/rules/README.md) | the rules, the override layers, exclusions and corrections, the knowledge files |
| [docs/map.md](docs/map.md) | the map: what you see, the panel and search, the data files |
| [docs/repository-model.md](docs/repository-model.md) | core, build directory and knowledge repository, and how their versions are tied together |
| [docs/limitations.md](docs/limitations.md) | structural limits of the data and method |
| [CONTRIBUTING.md](CONTRIBUTING.md) | set up, test, and add a gemeente, a correction, an exclusion or a rule |
| [NOTICE.md](NOTICE.md) | data sources, licences and what you may reuse |

## What you get

| Output | Where |
|---|---|
| Interactive map (open it over http; gemeenten load on demand) | `build/output/streets_map.html` + `build/output/data/` |
| One row per street: category, sub-kind, namesake, evidence tier, source | `build/output/streets_classified.csv` |
| One row per buurt: its naming theme | `build/output/buurt_themes.csv` |
| Do naming themes cluster by wijk? (permutation tests) | `build/output/wijk_theme_clustering.json` |

Serve the map locally with `python3 -m http.server --directory build/output 8765` and open `http://localhost:8765/streets_map.html`.
Opened straight from disk it still works but loads the larger uncompressed files.

## How certain is each street? Evidence tiers

Every street carries an `evidence_tier` (defined in `src/tiers.py`, shown in the map tooltips and the CSV):

| Tier | Meaning |
|---|---|
| 1 | Identified, external evidence (Wikidata or a web source) |
| 2 | Identified from general knowledge, not verified |
| 3 | Kind known from the name (a title, a species word, a trade term...) but no individual |
| 4 | Kind inferred from the neighbourhood's naming theme, or a weak match |
| 5 | Not identified: where the streets have no (known) name (generic or local names, anything unresolved); [help name them](https://github.com/straatwijsheid/knowledge#know-your-neighbourhood-help-us-name-the-streets) |

Only tier 1 has a source behind it; the rest is as good as the rules and reviewers behind it, and says so. Refinement should only ever move streets toward tier 1. `pipeline.py rebuild` prints the tier counts of a build; [docs/method.md](docs/method.md) explains the tiers.

## How it works

Full walkthrough: [docs/pipeline.md](docs/pipeline.md).

1. **Acquire** street names (OpenStreetMap via Overpass) and buurt/wijk boundaries (CBS via PDOK) for a gemeente.
2. **Look up** each street's core name (the name without "straat", "laan"...) on Wikidata.
3. **Reconcile** the per-street Wikidata guesses with each buurt's naming theme. A confident individual match is trusted; a weak one
   gives way to a strongly themed buurt; surname-only matches without support are rejected.
4. **Rules and hand classification** (`src/rules/`, `knowledge/`, the override layers under `knowledge/gemeenten/<province>/<gemeente>/overrides/`) add what Wikidata
   cannot: species, composers, saints, directional roads (`Eindhovensedijk`), titles, local names, and consistency audits.
5. **Analyse** whether themes cluster by wijk, **build the map**, **export CSVs**.

Guiding principles: the same name can mean different people in different places, so a namesake is only asserted where the street's
own buurt supports that kind of person; and a label resting on the buurt theme alone must also be backed by the name itself.

## Running it

Requirements: Python 3 in a virtualenv (`.venv/`); install with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. Run from the
repository root.

```bash
# any gemeente(s), end to end (acquire -> Wikidata -> reconcile -> themes -> rules check -> outputs)
# a contact for polite, fast Wikidata access goes in config.local.toml (git-ignored; copy config.example.toml) or in the WIKIDATA_CONTACT environment variable
.venv/bin/python src/config.py                      # shows where everything lives and which settings are in effect
.venv/bin/python src/pipeline.py add Tilburg Breda
.venv/bin/python src/pipeline.py status             # what is missing at each stage
.venv/bin/python src/pipeline.py rebuild            # after rules/overrides/knowledge changed: reconcile, analyze, map, CSVs, tier statistics

# or stage by stage (each is also what pipeline.py runs)
.venv/bin/python src/acquire.py "Tilburg"           # street network from the CBS buurten outline + buurten; exceptions in knowledge/global/gemeenten.json
                                                    # a gemeente is identified by its CBS code (GM0855); names work unless two gemeenten share one (Bergen): then pass the code
.venv/bin/python src/enrich_wikidata.py --missing   # every street name in streets.geojson not cached yet (resumable)
.venv/bin/python src/reconcile.py                   # Wikidata + themes + overrides -> build/enriched/streets_final.json
.venv/bin/python src/themes.py                      # buurt themes for buurten without one; then reconcile again
.venv/bin/python src/rules/run.py --check           # review what each rule proposes; --apply RULE to write it
.venv/bin/python src/analyze.py && .venv/bin/python src/build_map.py && .venv/bin/python src/export_csv.py

# tests
for t in tests/test_*.py; do .venv/bin/python $t | tail -1; done
```

Network notes: Overpass can refuse connections from busy IPs (a VPN endpoint change has fixed it), and Wikidata lookups run at
roughly 100 names a minute only when `WIKIDATA_CONTACT` is set.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md): setup, tests, and how to add a gemeente, a correction, an exclusion or a rule. Knowledge changes go to the [knowledge repository](https://github.com/straatwijsheid/knowledge).

## Repository layout

```
src/                 pipeline.py (orchestrator), acquire.py, enrich_wikidata.py, reconcile.py, themes.py, analyze.py, build_map.py, export_csv.py, tiers.py,
                     osm_etymology.py / osm_places.py (OpenStreetMap evidence), names/ (candidate table + resolver)
src/rules/           tested classification rules (see src/rules/README.md); run.py is the CLI
knowledge/      curated knowledge (the knowledge repository checks out here): global/ (species, vocabularies, famous people, place corrections, the gemeente registry `gemeenten_index.json`)
                     and gemeenten/<province>/<gemeente>/ (corrections, review sheet and notes, the override layers)
build/raw/ enriched/ names/ output/ cache/   the build directory: rebuildable, never in git (set `build_dir` in config.local.toml to put it elsewhere)
tests/               unit tests and a golden fixture with an end-to-end test (tiers, rules, overrides, snapshots, knowledge sharding, gemeente identity, schema, the data dictionary)
docs/                method, pipeline, map, repository model, limitations and the generated data dictionary
```

## Data and licences

Code is MIT. The data comes from OpenStreetMap (ODbL), CBS/PDOK (CC-BY 4.0) and Wikidata (CC0); our own classifications are CC-BY 4.0 in the [knowledge repository](https://github.com/straatwijsheid/knowledge). [NOTICE.md](NOTICE.md) explains what you can reuse and how to credit it.

## Known limits

* Classification depth varies by gemeente: the early ones were classified more thoroughly, in waves, before the rules existed.
* Most identified namesakes come from general knowledge and have not been verified against Wikidata or the web (tier 2); only tier 1 has a source.
* Labels that rest on a buurt's theme are weaker than ones the name supports, and the themes are partly derived from earlier classifications.
* A street is a named OpenStreetMap way: it is as complete and as current as OpenStreetMap, and all ways with one name in a gemeente are one street.

The full list is in [docs/limitations.md](docs/limitations.md).
